"""Synthetic executable fixtures: no Claude Code binary/source is redistributed."""

import struct
import unittest
from png_to_claude_code.engine import build, art


def executable(version="2.1.318", cpu=0x100000C):
    name = b"/$bunfs/root/example.js\0"
    source = (
        (
            f"// Version: {version}\nfunction ul(m){{/* fullscreen */let E={'ot' if version=='2.1.319' else 'rt'}();".encode()
        )
        + b" " * 1500
        + (
            b"return null;}function Gd(m){return m;}"
            if version == "2.1.319"
            else b"return null;}function Yd(m){return m;}"
        )
    )
    body = name + source + b"\0" + b"cache"
    source_offset = len(name)
    table_offset = len(body)
    table = struct.pack(
        "<12I4B",
        0,
        len(name) - 1,
        source_offset,
        len(source),
        0,
        0,
        len(body) - 5,
        5,
        0,
        0,
        0,
        0,
        1,
        1,
        1,
        0,
    )
    body += table + struct.pack("<I", 123456)
    offsets = struct.pack("<QIIIIII", len(body), table_offset, len(table), 0, 0, 0, 32)
    header = bytearray(32)
    header[:4] = b"\xcf\xfa\xed\xfe"
    struct.pack_into("<I", header, 4, cpu)
    return bytes(header) + body + offsets + b"\n---- Bun! ----\n"


class PatchTests(unittest.TestCase):
    def test_only_header_and_its_cache_change(self):
        original = executable()
        stub = b'function ul(m){/*DEEPSEEK_PIXEL_HEADER_V1*/return "fish";}'
        patched = build(original, stub)
        self.assertEqual(len(patched), len(original))
        start = original.index(b"function ul(m){")
        end = original.index(b"function Yd(m)", start)
        trailer = original.index(b"\n---- Bun! ----\n")
        count, mo, ml, *_ = struct.unpack_from("<QIIIIII", original, trailer - 32)
        base = trailer - 32 - count
        permitted = (
            set(range(start, end))
            | set(range(base + mo + 24, base + mo + 32))
            | set(range(base + mo + ml, base + mo + ml + 4))
        )
        self.assertTrue(
            all(
                i in permitted
                for i, (a, b) in enumerate(zip(original, patched))
                if a != b
            )
        )
        self.assertIn(b"fish", patched)
        self.assertEqual(patched[base + mo + 24 : base + mo + 32], b"\0" * 8)
        with self.assertRaises(ValueError):
            build(patched, stub)

    def test_wrong_architecture_is_rejected(self):
        with self.assertRaises(ValueError):
            build(executable(cpu=0x1000007), b"function ul(m){}")

    def test_wrong_version_is_rejected(self):
        with self.assertRaises(ValueError):
            build(executable("2.1.320"), b"function ul(m){}")

    def test_oversize_art_is_rejected(self):
        with self.assertRaises(ValueError):
            build(executable(), b"x" * 4000)

    def test_invalid_module_bounds_are_rejected(self):
        data = bytearray(executable())
        trailer = data.index(b"\n---- Bun! ----\n")
        struct.pack_into("<I", data, trailer - 24, 0xFFFFFFFF)
        with self.assertRaises(ValueError):
            build(bytes(data), b"function ul(m){}")

    def test_319_uses_its_own_guard_and_function_boundary(self):
        stub = b'function ul(m){/*DEEPSEEK_PIXEL_HEADER_V1*/if(rt())return null;return "fish";}'
        original = executable("2.1.319")
        patched = build(original, stub)
        self.assertEqual(len(patched), len(original))
        self.assertIn(b"if(ot())return null;", patched)
        self.assertIn(b"function Gd(m){return m;}", patched)
        self.assertNotIn(b"if(rt())", patched)

    def test_319_rejects_unexpected_guard(self):
        original = executable("2.1.319").replace(b"=ot()", b"=zz()")
        with self.assertRaises(ValueError):
            build(original, b"function ul(m){}")

    def test_duplicate_boundary_in_other_module_is_allowed(self):
        original = executable("2.1.319") + b"function Gd(m){}"
        patched = build(original, b"function ul(m){}")
        self.assertEqual(len(original), len(patched))
        self.assertTrue(patched.endswith(b"function Gd(m){}"))
