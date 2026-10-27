#!/usr/bin/env python3
"""Build one deterministic ZIP, overwriting the previous build (no staging tree)."""

import argparse
import configparser
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versioned", action="store_true", help="Use the metadata version in the ZIP filename")
    args = parser.parse_args()
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.read(ROOT / "polygon_qc" / "metadata.txt")
    version = metadata["general"]["version"]
    filename = f"polygon_qc-{version}.zip" if args.versioned else "polygon_qc.zip"
    destination = ROOT / "dist" / filename
    destination.parent.mkdir(exist_ok=True)
    sources = sorted((ROOT / "polygon_qc").glob("*.py"))
    sources.append(ROOT / "polygon_qc" / "metadata.txt")
    sources.append(ROOT / "polygon_qc" / "icon.svg")
    sources.extend(ROOT / name for name in ("LICENSE", "README.md", "CHANGELOG.md"))
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sources:
            name = path.relative_to(ROOT).as_posix() if path.parent.name == "polygon_qc" else f"polygon_qc/{path.name}"
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    print(destination)


if __name__ == "__main__":
    main()

