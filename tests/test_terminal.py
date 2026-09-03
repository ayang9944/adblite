import codecs
import unittest

from adblite.terminal import TerminalLogState, flush_terminal_log, render_terminal_log


class TerminalLogRendererTests(unittest.TestCase):
    def test_crlf_is_emitted_once(self):
        state = TerminalLogState()
        self.assertEqual(render_terminal_log("first\r\nsecond\n", state), "first\nsecond\n")

    def test_bare_carriage_return_does_not_merge_redrawn_text(self):
        state = TerminalLogState()
        rendered = render_terminal_log(
            'curl -x "http://proxy-user:password@gateway:12905" ipinfo.io\r'
            'proxy-user:password@gateway:12905" ipinfo.io\r\n',
            state,
        )
        self.assertEqual(
            rendered,
            'curl -x "http://proxy-user:password@gateway:12905" ipinfo.io\n'
            'proxy-user:password@gateway:12905" ipinfo.io\n',
        )

    def test_backspace_edits_the_current_line(self):
        state = TerminalLogState()
        self.assertEqual(render_terminal_log("abc\b\bXY\r\n", state), "aXY\n")

    def test_ansi_sequence_can_be_split_across_reads(self):
        state = TerminalLogState()
        self.assertEqual(render_terminal_log("\x1b[31", state), "")
        self.assertEqual(render_terminal_log("merror\x1b[0m\r\n", state), "error\n")

    def test_prompt_is_split_from_output_without_newline(self):
        state = TerminalLogState()
        rendered = render_terminal_log("curl: (97) Connection closed\r\nacp-device:/ # ", state)
        self.assertEqual(rendered, "curl: (97) Connection closed\nacp-device:/ # \n")

    def test_incremental_utf8_decoder_preserves_split_chinese_character(self):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        encoded = "日志正常".encode("utf-8")
        decoded = decoder.decode(encoded[:2]) + decoder.decode(encoded[2:], final=True)
        self.assertEqual(decoded, "日志正常")

    def test_unterminated_final_line_is_flushed(self):
        state = TerminalLogState()
        self.assertEqual(render_terminal_log("last message", state), "")
        self.assertEqual(flush_terminal_log(state), "last message\n")



if __name__ == "__main__":
    unittest.main()
