"""Version-specific native header adapter for Claude Code 2.1.318/2.1.319 (macOS arm64)."""

import base64, json, struct, subprocess, tempfile, re, plistlib
from pathlib import Path
from PIL import Image

MARKER = b"DEEPSEEK_PIXEL_HEADER_V1"
START = b"function ul(m){"
END = b"function Yd(m)"
ADAPTERS = {"2.1.318": (END, b"rt"), "2.1.319": (b"function Gd(m)", b"ot")}


def cells(im):
    im = im.convert("RGBA")

    def color(x, y):
        if y >= im.height:
            return None
        r, g, b, a = im.getpixel((x, y))
        return f"#{r:02x}{g:02x}{b:02x}" if a >= 128 else None

    rows = []
    for y in range(0, im.height, 2):
        row = []
        for x in range(im.width):
            a, b = color(x, y), color(x, y + 1)
            row.append(
                (a or b, b if a and b else None, "▀" if a else "▄" if b else " ")
            )
        rows.append(row)
    return rows


def art(image, width=28):
    if not isinstance(width, int) or width < 2 or width > 32 or width % 2:
        raise ValueError("Width must be an even integer between 2 and 32")
    with Image.open(image) as source:
        im = source.convert("RGBA")
    h = max(2, round(im.height * width / im.width))
    h += h % 2
    if h > 64:
        raise ValueError(
            "Image is too tall for the welcome header; crop it or reduce width"
        )
    small = im.resize((width, h), Image.Resampling.NEAREST)
    quant = small.convert("RGB").quantize(
        colors=15, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    pal = quant.getpalette()
    pal += [0] * (45 - len(pal))
    palette = [None] + [
        "#%02x%02x%02x" % tuple(pal[i * 3 : i * 3 + 3]) for i in range(15)
    ]
    indices = [
        0 if a < 128 else k + 1 for k, (*_, a) in zip(quant.getdata(), small.getdata())
    ]
    packed = bytes(
        (indices[i] << 4) | indices[i + 1] for i in range(0, len(indices), 2)
    )
    encoded = base64.b64encode(packed).decode()
    stub = (
        "function ul(m){/*"
        + MARKER.decode()
        + "*/if(rt())return null;const P="
        + json.dumps(palette, separators=(",", ":"))
        + ",G=Buffer.from("
        + json.dumps(encoded)
        + ',"base64"),W='
        + str(width)
        + ",H="
        + str(h)
        + ";"
        "const C=i=>P[(G[i>>1]>>(i%2?0:4))&15];"
        'return e(s,{width:W,height:H/2,flexShrink:0,flexDirection:"column",children:Array.from({length:H/2},(_,r)=>'
        'e(n,{wrap:"truncate",children:Array.from({length:W},(_,x)=>{let a=C(2*r*W+x),b=C((2*r+1)*W+x);'
        'return e(n,{color:a||b||void 0,backgroundColor:a&&b?b:void 0,children:a?"\\u2580":b?"\\u2584":" "},x)})},r))})}'
    ).encode()
    rendered = Image.new("RGBA", small.size)
    rendered.putdata(
        [
            (
                (0, 0, 0, 0)
                if k == 0
                else tuple(int(palette[k][j : j + 2], 16) for j in (1, 3, 5)) + (255,)
            )
            for k in indices
        ]
    )
    return stub, rendered


def graph(data):
    if (
        len(data) < 32
        or data[:4] != b"\xcf\xfa\xed\xfe"
        or struct.unpack_from("<I", data, 4)[0] != 0x100000C
    ):
        raise ValueError(
            "Only the inspected macOS arm64 native executable is supported"
        )
    trailer = data.rfind(b"\n---- Bun! ----\n")
    if trailer < 32:
        raise ValueError("Missing Bun module graph")
    count, mo, ml, ep, ao, al, flags = struct.unpack_from(
        "<QIIIIII", data, trailer - 32
    )
    base = trailer - 32 - count
    if (
        base < 32
        or ml == 0
        or ml % 52
        or ep >= ml // 52
        or base + mo + ml > trailer - 32
        or (flags & 32 and base + mo + ml + ml // 52 * 4 > trailer - 32)
    ):
        raise ValueError("Unrecognized Bun module table")
    return base, mo, ml, flags


def version(data):
    """Read the version from the unique source module containing the header."""
    base, mo, ml, _ = graph(data)
    if data.count(START) != 1:
        raise ValueError("Header entry is missing or ambiguous")
    start = data.index(START)
    matches = []
    for i in range(ml // 52):
        v = struct.unpack_from("<12I4B", data, base + mo + 52 * i)
        if v[2] + v[3] > mo:
            raise ValueError("Invalid source module bounds")
        if base + v[2] <= start < base + v[2] + v[3]:
            chunk = data[base + v[2] : base + v[2] + v[3]]
            match = re.search(rb"// Version: ([0-9.]+)\n", chunk[:250])
            if match:
                matches.append(match.group(1).decode("ascii"))
    if len(matches) != 1 or matches[0] not in ADAPTERS:
        raise ValueError(
            "This adapter only supports inspected versions: " + ", ".join(ADAPTERS)
        )
    return matches[0]


def build(data, stub):
    base, mo, ml, flags = graph(data)
    if MARKER in data:
        raise ValueError("Already patched; restore the saved backup before rebuilding")
    release = version(data)
    end_marker, guard = ADAPTERS[release]
    if end_marker not in data:
        raise ValueError("Header entry is missing or ambiguous")
    start = data.index(START)
    end = data.index(end_marker, start)
    if b"=" + guard + b"()" not in data[start:end]:
        raise ValueError("Unexpected header visibility guard")
    stub = stub.replace(b"if(rt())", b"if(" + guard + b"())")
    if end - start > 5000 or b"fullscreen" not in data[start:end]:
        raise ValueError("Unexpected header implementation")
    if len(stub) > end - start:
        raise ValueError(
            f"Image code needs {len(stub)} bytes; header has {end-start}; use a smaller width"
        )
    found = []
    for i in range(ml // 52):
        at = base + mo + 52 * i
        v = struct.unpack_from("<12I4B", data, at)
        if v[2] + v[3] > mo:
            raise ValueError("Invalid source module bounds")
        if base + v[2] <= start < end <= base + v[2] + v[3]:
            found.append((i, at, v))
    if len(found) != 1:
        raise ValueError("Header module is not uniquely identified")
    i, at, v = found[0]
    chunk = data[base + v[2] : base + v[2] + v[3]]
    if chunk.count(end_marker) != 1:
        raise ValueError("Header boundary is ambiguous within its module")
    if ("// Version: " + release + "\n").encode() not in chunk[:250]:
        raise ValueError("Header version mismatch")
    result = bytearray(data)
    result[start:end] = stub.ljust(end - start, b" ")
    # Recompile only the changed source module; keep other modules cached.
    struct.pack_into("<II", result, at + 24, 0, 0)
    if flags & 32:
        struct.pack_into("<I", result, base + mo + ml + 4 * i, 0)
    chunk = result[base + v[2] : base + v[2] + v[3]]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "header.mjs"
        p.write_bytes(chunk)
        subprocess.run(["node", "--check", str(p)], check=True, capture_output=True)
    return bytes(result)


def embedded_entitlements(data):
    """Read the XML entitlement slot when older codesign cannot export it."""
    graph(data)  # validates the supported thin arm64 container
    count = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    for _ in range(count):
        if offset + 8 > len(data):
            raise ValueError("Truncated Mach-O load command")
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > len(data):
            raise ValueError("Invalid Mach-O load command")
        if command == 0x1D:  # LC_CODE_SIGNATURE
            if size < 16:
                raise ValueError("Invalid signature command")
            start, length = struct.unpack_from("<II", data, offset + 8)
            signature = data[start : start + length]
            if len(signature) != length or length < 12:
                raise ValueError("Truncated signature")
            magic, total, slots = struct.unpack_from(">III", signature)
            if magic != 0xFADE0CC0 or total > length or 12 + slots * 8 > total:
                raise ValueError("Invalid signature superblob")
            for i in range(slots):
                kind, at = struct.unpack_from(">II", signature, 12 + i * 8)
                if kind != 5:
                    continue
                if at + 8 > total:
                    raise ValueError("Invalid entitlement offset")
                magic, size = struct.unpack_from(">II", signature, at)
                if magic != 0xFADE7171 or size < 8 or at + size > total:
                    raise ValueError("Invalid XML entitlement slot")
                blob = signature[at + 8 : at + size]
                if not isinstance(plistlib.loads(blob), dict):
                    raise ValueError("Invalid entitlement plist")
                return blob
            return None
        offset += size
    return None


def sign(path, original):
    with tempfile.TemporaryDirectory() as td:
        ent = Path(td) / "entitlements.plist"
        subprocess.run(
            ["codesign", "-d", "--entitlements", str(ent), "--xml", str(original)],
            check=True,
            capture_output=True,
        )
        if not ent.exists() or not ent.stat().st_size:
            blob = embedded_entitlements(Path(original).read_bytes())
            if blob is not None:
                ent.write_bytes(blob)
        command = ["codesign", "--force", "--sign", "-", "--options", "runtime"]
        if ent.exists() and ent.stat().st_size:
            # Preserve the source XML entitlements, including JIT permissions.
            plistlib.loads(ent.read_bytes())
            command.extend(["--entitlements", str(ent)])
        command.append(str(path))
        subprocess.run(command, check=True)
        subprocess.run(["codesign", "--verify", str(path)], check=True)
