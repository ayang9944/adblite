import unittest

from adblite.domain import Device, merge_device_statuses, sort_devices_by_status


class DeviceStatusMergeTests(unittest.TestCase):
    def test_missing_device_is_retained_as_offline(self):
        known = [
            Device(serial="usb-1", state="device", model="USB Phone"),
            Device(serial="192.168.1.20:5555", state="device", model="WiFi Phone"),
        ]
        detected = [Device(serial="usb-1", state="device", model="USB Phone")]

        merged = merge_device_statuses(known, detected)

        self.assertEqual([device.serial for device in merged], ["usb-1", "192.168.1.20:5555"])
        self.assertEqual(merged[1].state, "offline")
        self.assertEqual(merged[1].model, "WiFi Phone")

    def test_reconnected_device_replaces_offline_entry_in_place(self):
        known = [Device(serial="192.168.1.20:5555", state="offline", model="Old Name")]
        detected = [Device(serial="192.168.1.20:5555", state="device", model="Current Name")]

        merged = merge_device_statuses(known, detected)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].state, "device")
        self.assertEqual(merged[0].model, "Current Name")

    def test_devices_are_sorted_connected_first_and_offline_last(self):
        devices = [
            Device(serial="offline", state="offline"),
            Device(serial="unauthorized", state="unauthorized"),
            Device(serial="connected-2", state="device"),
            Device(serial="connected-1", state="device"),
        ]

        ordered = sort_devices_by_status(devices)

        self.assertEqual(
            [device.serial for device in ordered],
            ["connected-2", "connected-1", "unauthorized", "offline"],
        )


if __name__ == "__main__":
    unittest.main()
