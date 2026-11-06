"""Command-line interface for PNG previews and native header patches."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from . import __version__, engine


def default_target():
    return Path.home() / ".local/bin/claude"


def preview(image, width, svg=None):
    _, pixels = engine.art(image, width)
    if svg:
        dest = Path(svg).expanduser()
        if dest.exists():
            raise ValueError("SVG output already exists; choose a new path")
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{pixels.width*16}" height="{pixels.height*16}" viewBox="0 0 {pixels.width} {pixels.height}" shape-rendering="crispEdges">'
        ]
        for y in range(pixels.height):
            for x in range(pixels.width):
                r, g, b, a = pixels.getpixel((x, y))
                if a:
                    parts.append(
                        f'<rect x="{x}" y="{y}" width="1" height="1" fill="#{r:02x}{g:02x}{b:02x}"/>'
                    )
        parts.append("</svg>")
        with dest.open("x", encoding="utf-8") as stream:
            stream.write("\n".join(parts))
        print(dest)
        return
    for row in engine.cells(pixels):
        output = []
        for fg, bg, char in row:
            output.append("\x1b[0m")
            for color, code in ((fg, 38), (bg, 48)):
                if color:
                    rgb = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
                    output.append(f"\x1b[{code};2;" + ";".join(map(str, rgb)) + "m")
            output.append(char)
        print("".join(output) + "\x1b[0m")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Turn a PNG into a pixel-art Claude Code welcome icon (2.1.318 / 2.1.319, macOS arm64)."
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "build", "install"):
        sub = commands.add_parser(name)
        sub.add_argument(
            "image", type=Path, help="PNG or another Pillow-supported image"
        )
        sub.add_argument(
            "--width",
            type=int,
            choices=range(12, 33, 2),
            default=28,
            metavar="12..32",
            help="Even column count; default: 28",
        )
        if name == "preview":
            sub.add_argument(
                "--svg",
                type=Path,
                help="Write a transparent SVG instead of terminal output",
            )
        else:
            sub.add_argument(
                "--target",
                type=Path,
                default=default_target(),
                help="Installed native Claude executable or its symlink",
            )
        if name == "build":
            sub.add_argument(
                "--output",
                type=Path,
                required=True,
                help="New executable path; never overwrites an existing file",
            )
        if name == "install":
            sub.add_argument(
                "--state",
                type=Path,
                default=Path.home() / ".config/png-to-claude-code/installation.json",
            )
    sub = commands.add_parser("restore")
    sub.add_argument(
        "--state",
        type=Path,
        default=Path.home() / ".config/png-to-claude-code/installation.json",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "preview":
            preview(args.image.expanduser(), args.width, args.svg)
            return 0
        from .manage import build_to, activate, restore

        if args.command == "build":
            result = build_to(
                args.target, args.image.expanduser(), args.output, args.width
            )
        elif args.command == "restore":
            result = restore(args.state)
        else:
            with tempfile.TemporaryDirectory(prefix="png-to-claude-") as td:
                candidate = Path(td) / "claude"
                built = build_to(
                    args.target, args.image.expanduser(), candidate, args.width
                )
                result = activate(
                    candidate, args.target, args.state, built["source_sha256"]
                )
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
