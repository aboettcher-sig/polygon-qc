#!/usr/bin/env python3
"""Build one deterministic ZIP, overwriting the previous build (no staging tree)."""

from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "dist" / "polygon_qc.zip"
    destination.parent.mkdir(exist_ok=True)
    sources = sorted((ROOT / "polygon_qc").glob("*.py"))
    sources.append(ROOT / "polygon_qc" / "metadata.txt")
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sources:
            info = ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    print(destination)


if __name__ == "__main__":
    main()

