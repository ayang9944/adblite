from __future__ import annotations

from dataclasses import dataclass
import re


PROMPT_RE = re.compile(r"[\w.-]+:/[^\r\n]*?[#$] $")


@dataclass
class TerminalLogState:
    """State needed to turn a terminal byte stream into readable scrollback."""

    line: str = ""
    cursor_pos: int = 0
    skip_lf_after_cr: bool = False
    escape_buffer: str = ""


def _strip_escape_sequences(text: str, state: TerminalLogState) -> str:
    """Strip complete ANSI sequences while retaining a split trailing sequence."""

    source = state.escape_buffer + text
    state.escape_buffer = ""
    plain: list[str] = []
    index = 0
    while index < len(source):
        if source[index] != "\x1b":
            plain.append(source[index])
            index += 1
            continue

        start = index
        if index + 1 >= len(source):
            state.escape_buffer = source[start:]
            break

        kind = source[index + 1]
        if kind == "[":  # CSI: ESC [ ... final-byte
            index += 2
            while index < len(source) and not ("@" <= source[index] <= "~"):
                index += 1
            if index >= len(source):
                state.escape_buffer = source[start:]
                break
            index += 1
        elif kind == "]":  # OSC: ESC ] ... BEL or ST
            index += 2
            while index < len(source):
                if source[index] == "\x07":
                    index += 1
                    break
                if source[index] == "\x1b" and index + 1 < len(source) and source[index + 1] == "\\":
                    index += 2
                    break
                index += 1
            else:
                state.escape_buffer = source[start:]
                break
        else:
            # Other ESC controls are two-byte sequences.
            index += 2
    return "".join(plain)


def render_terminal_log(text: str, state: TerminalLogState) -> str:
    """Render terminal output as stable text suitable for an append-only log.

    A bare carriage return normally redraws the current terminal row. Keeping
    both versions as separate log rows avoids joining the tail of an old row
    with the head of its replacement, which is especially visible for long
    shell commands and progress output.
    """

    text = _strip_escape_sequences(text, state)
    emitted: list[str] = []

    for char in text:
        if char == "\r":
            emitted.append(state.line + "\n")
            state.line = ""
            state.cursor_pos = 0
            state.skip_lf_after_cr = True
            continue

        if char == "\n":
            if state.skip_lf_after_cr:
                state.skip_lf_after_cr = False
                continue
            emitted.append(state.line + "\n")
            state.line = ""
            state.cursor_pos = 0
            continue

        state.skip_lf_after_cr = False
        if char in {"\b", "\x7f"}:
            state.cursor_pos = max(0, state.cursor_pos - 1)
            continue
        if char == "\t":
            spaces = 8 - (state.cursor_pos % 8)
            for _ in range(spaces):
                if state.cursor_pos < len(state.line):
                    state.line = state.line[:state.cursor_pos] + " " + state.line[state.cursor_pos + 1:]
                else:
                    state.line += " "
                state.cursor_pos += 1
            continue
        if ord(char) < 32:
            # Bells and other C0 controls have no useful representation in a
            # plain-text log.
            continue

        if state.cursor_pos < len(state.line):
            state.line = state.line[:state.cursor_pos] + char + state.line[state.cursor_pos + 1:]
        else:
            state.line += char
        state.cursor_pos += 1

        match = PROMPT_RE.search(state.line)
        if match and match.end() == len(state.line):
            if match.start() > 0:
                emitted.append(state.line[:match.start()] + "\n")
            emitted.append(state.line[match.start():] + "\n")
            state.line = ""
            state.cursor_pos = 0

    return "".join(emitted)


def flush_terminal_log(state: TerminalLogState) -> str:
    """Return the final unterminated row when a terminal session closes."""

    final_line = state.line
    state.line = ""
    state.cursor_pos = 0
    state.skip_lf_after_cr = False
    state.escape_buffer = ""
    return final_line + "\n" if final_line else ""
