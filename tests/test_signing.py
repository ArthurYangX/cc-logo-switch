"""Verify XML entitlement preservation without Apple signing tools."""

import plistlib
import struct
import unittest
from test_patch import executable
from png_to_claude_code.engine import embedded_entitlements


def signed_fixture():
    original = bytearray(executable("2.1.319"))
    struct.pack_into("<I", original, 16, 1)
    payload = plistlib.dumps({"com.apple.security.cs.allow-jit": True})
    slot = struct.pack(">II", 0xFADE7171, 8 + len(payload)) + payload
    signature = struct.pack(">IIIII", 0xFADE0CC0, 20 + len(slot), 1, 5, 20) + slot
    command = struct.pack("<IIII", 0x1D, 16, len(original) + 16, len(signature))
    return bytes(original[:32]) + command + bytes(original[32:]) + signature


class EntitlementTests(unittest.TestCase):
    def test_retains_jit_entitlements(self):
        blob = embedded_entitlements(signed_fixture())
        self.assertEqual(
            plistlib.loads(blob), {"com.apple.security.cs.allow-jit": True}
        )

    def test_rejects_truncated_signature(self):
        with self.assertRaises(ValueError):
            embedded_entitlements(signed_fixture()[:-1])

    def test_no_signature_has_no_entitlements(self):
        self.assertIsNone(embedded_entitlements(executable()))
