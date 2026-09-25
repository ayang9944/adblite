import sys
import unittest

from adblite.ui.main_window import split_local_process_arguments


@unittest.skipUnless(sys.platform == "win32", "Windows command-line parsing only")
class WindowsCommandLineTests(unittest.TestCase):
    def test_chrome_proxy_arguments_do_not_keep_shell_quotes(self):
        arguments = split_local_process_arguments(
            '--proxy-server="127.0.0.1:8888" '
            '--user-data-dir="C:\\temp\\charles-profile"'
        )

        self.assertEqual(
            arguments,
            [
                "--proxy-server=127.0.0.1:8888",
                "--user-data-dir=C:\\temp\\charles-profile",
            ],
        )

    def test_quoted_option_value_can_contain_spaces(self):
        arguments = split_local_process_arguments(
            '--user-data-dir="C:\\temp\\charles profile"'
        )

        self.assertEqual(arguments, ["--user-data-dir=C:\\temp\\charles profile"])


if __name__ == "__main__":
    unittest.main()
