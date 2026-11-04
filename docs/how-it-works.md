# How the 2.1.318 adapter works

## Image representation

The converter resizes an RGBA input with nearest-neighbor sampling, quantizes RGB to 15 colors, and reserves palette index zero for transparent pixels. It packs two four-bit indices per byte and embeds the base64 payload and palette in the replacement component.

Each terminal cell represents two vertically adjacent pixels. Upper pixels use `▀`; lower-only pixels use `▄`. A missing pixel leaves the terminal background visible. Unicode glyphs are emitted as JavaScript `\u2580` / `\u2584` escapes: this executable stores source as Latin-1, so writing literal UTF-8 glyph bytes into the bundle produces corrupted characters.

## Patch boundary

The adapter supports one inspected build layout: native macOS ARM64 Claude Code 2.1.318. It locates the welcome header component between the unique `function ul(m){` and `function Yd(m)` markers, verifies the containing module's version and expected `fullscreen` structure, and replaces only that component. It retains the existing JSX/text/layout symbols in that module. This skips the original mascot animation for the replacement header while retaining the surrounding version/model/directory display.

The new component is padded to the original byte length. The adapter checks the complete modified source module with `node --check` before writing an executable. Images that exceed the function's available byte budget are rejected.

## Bun's precompiled module cache

Changing embedded JavaScript alone is insufficient when its old precompiled module is still available. The adapter locates the containing module in Bun's serialized graph, clears that module's bytecode pointer/length, and clears its cached source hash when present. Other modules retain their caches.

The relevant public layout is documented by the [Bun 1.4.4 module-graph source](https://github.com/oven-sh/bun/blob/bun-v1.4.4/src/standalone_graph/StandaloneModuleGraph.rs): the graph trailer, 52-byte module records and optional source-hash table. This is an internal format, so version checks and synthetic boundary tests are intentional.

## Installation and restoration

A build writes a new file, applies an ad-hoc macOS signature with the source's entitlements, verifies the signature and runs `--version`. The installer then backs up the current executable, records SHA-256 hashes and atomically swaps the candidate into place. It checks for source changes before swapping.

Restoration is checksum guarded. It restores the saved file only while the installed file still matches the recorded patch; a newer or differently modified Claude installation is left untouched. The installation record is written atomically and the state path is locked during install/restore.

The public repository contains only the adapter, documentation, artwork and synthetic tests. Local extracted modules, binaries, credentials and installation records are excluded.

## Scope of validation

The initial implementation was tested locally on Claude Code 2.1.318 / macOS ARM64 and VS Code 1.144.1. A separate PTY integration run verified indexed-color output, text input, resize handling and clean exit. CI tests the image conversion, generated JavaScript, bounded binary changes and filesystem installation behavior; it does not download or redistribute Claude Code.

Supporting another Claude release requires inspecting its current component and module graph and repeating the native interaction tests. Changing the version string alone does not establish compatibility.
