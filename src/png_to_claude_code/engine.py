"""Version-specific native header adapter for Claude Code 2.1.318 (macOS arm64)."""

import base64, json, struct, subprocess, tempfile
from pathlib import Path
from PIL import Image

MARKER = b"DEEPSEEK_PIXEL_HEADER_V1"
START = b"function ul(m){"
END = b"function Yd(m)"


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


def build(data, stub):
    base, mo, ml, flags = graph(data)
    if MARKER in data:
        raise ValueError("Already patched; restore the saved backup before rebuilding")
    if data.count(START) != 1 or data.count(END) != 1:
        raise ValueError("Header entry is missing or ambiguous")
    start = data.index(START)
    end = data.index(END, start)
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
    if b"// Version: 2.1.318\n" not in chunk[:250]:
        raise ValueError("This adapter only supports 2.1.318")
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


def sign(path, original):
    with tempfile.TemporaryDirectory() as td:
        ent = Path(td) / "entitlements.plist"
        subprocess.run(
            ["codesign", "-d", "--entitlements", str(ent), "--xml", str(original)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "codesign",
                "--force",
                "--sign",
                "-",
                "--options",
                "runtime",
                "--entitlements",
                str(ent),
                str(path),
            ],
            check=True,
        )
        subprocess.run(["codesign", "--verify", str(path)], check=True)
