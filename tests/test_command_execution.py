import sys
import unittest

from adblite.infrastructure import ProcessRunner


@unittest.skipUnless(sys.platform == "win32", "Windows command-line parsing only")
class WindowsCommandLineTests(unittest.TestCase):
    def test_cmd_preserves_quotes_around_url_arguments(self):
        result = ProcessRunner.run_cmd(
            f'"{sys.executable}" -c "import sys;print(chr(124).join(sys.argv[1:]))" '
            '-x "https://user:password~3@gate.example.com:10001" '
            '"https://ip.example.com/json"'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "-x|https://user:password~3@gate.example.com:10001|https://ip.example.com/json",
        )

    def test_cmd_supports_native_shell_operators_without_special_cases(self):
        result = ProcessRunner.run_cmd("echo first&&echo second")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["first", "second"])

if __name__ == "__main__":
    unittest.main()
