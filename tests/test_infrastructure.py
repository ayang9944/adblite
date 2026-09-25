import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from adblite.infrastructure import SettingsRepository, parse_adb_devices_output, parse_mdns_services_output


class AdbOutputParserTests(unittest.TestCase):
    def test_devices_output_preserves_non_ready_states(self):
        output = """List of devices attached
R58M1234 device product:foo model:SM_F900F device:foo transport_id:1
192.168.1.20:5555 unauthorized transport_id:2
emulator-5554 offline transport_id:3
"""
        devices = parse_adb_devices_output(output)

        self.assertEqual([item.serial for item in devices], ["R58M1234", "192.168.1.20:5555", "emulator-5554"])
        self.assertEqual(devices[0].model, "SM F900F")
        self.assertEqual(devices[1].state, "unauthorized")

    def test_mdns_parser_returns_connect_services_once(self):
        output = """List of discovered mdns services
adb-R58M-abc._adb-tls-connect._tcp 192.168.1.20:37123
adb-R58M-abc._adb-tls-connect._tcp 192.168.1.20:37123
adb-R58M-pair._adb-tls-pairing._tcp 192.168.1.20:40111
adb-phone._adb._tcp phone.local:5555
"""
        self.assertEqual(parse_mdns_services_output(output), ["192.168.1.20:37123", "phone.local:5555"])


class ConnectionHistoryTests(unittest.TestCase):
    def test_remembering_edited_address_preserves_original_record(self):
        with TemporaryDirectory() as directory:
            repository = SettingsRepository.__new__(SettingsRepository)
            repository.path = Path(directory) / "settings.json"
            repository.data = {"history": []}

            repository.remember("192.168.1.20:5555")
            repository.remember("192.168.1.21:5555")

            self.assertEqual(
                [item.address for item in repository.histories()],
                ["192.168.1.21:5555", "192.168.1.20:5555"],
            )


if __name__ == "__main__":
    unittest.main()
