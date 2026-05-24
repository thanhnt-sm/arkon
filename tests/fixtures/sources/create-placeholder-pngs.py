"""
Helper script — run once to materialise the 1×1 transparent PNG stubs that
git cannot store as binary literals in a Python source file.

Usage (from repo root):
    python3 tests/fixtures/sources/create-placeholder-pngs.py

These stubs satisfy the e2e fixture loader which checks file existence.
Replace the outputs with real chart / screenshot PNGs before running the
live e2e test (see README.md in this directory).
"""
import base64
import pathlib

# Minimal valid 1×1 transparent PNG — 67-byte IDAT stream, no ancillary chunks.
# Verified with `python -c "import PIL.Image; PIL.Image.open('...').verify()"`.
PNG_1X1_TRANSPARENT = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

HERE = pathlib.Path(__file__).parent

targets = [
    HERE / "sample-chart.png",
    HERE / "sample-vi-screenshot.png",
]

for path in targets:
    path.write_bytes(PNG_1X1_TRANSPARENT)
    print(f"Written: {path}  ({path.stat().st_size} bytes)")

print("Done. Replace with real images before running e2e tests.")
