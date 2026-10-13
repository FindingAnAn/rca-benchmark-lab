"""Build a local deployment archive without modifying original data or docs."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "README.md",
    ".gitignore",
    ".gitattributes",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "config/internal.json",
    "config/rcaeval_local.json",
    "config/feature_mapping.json",
    "config/log_parser.json",
    "docs/files.md",
    "docs/matching.md",
    "docs/analysis.md",
    "docs/conventions.md",
    "docs/matching/internal_metrics.csv",
    "docs/matching/rcaeval_metrics.csv",
    "docs/matching/rcaeval_raw_metrics.csv",
    "docs/matching/rcaeval_logs.csv",
    "docs/matching/cdr_fields.csv",
    "scripts/run_rcaeval_local.sh",
    "scripts/run_internal_local.sh",
    "scripts/package_repo.py",
    ".vscode/settings.json",
    ".vscode/extensions.json",
    ".vscode/launch.json",
)


def build_archive(output: Path) -> None:
    """Package an explicit source allowlist and SHA256 manifest; never overwrite."""
    paths = {ROOT / name for name in FILES}
    for pattern in ("src/**/*.py", "src/**/*.json", "tests/test_*.py"):
        paths.update(ROOT.glob(pattern))
    paths.discard(ROOT / "src/data/ingestion/rcaeval.py")
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing file or symbolic link: {path}")
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"File outside project: {path}")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            relative = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            manifest[relative] = hashlib.sha256(content).hexdigest()
            archive.writestr("rca-benchmark-lab/" + relative, content)
        archive.writestr(
            "rca-benchmark-lab/package_manifest.json",
            json.dumps(manifest, indent=2) + "\n",
        )
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC validation failed")
    print(f"Packaged {len(paths)} files: {output.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/rca-benchmark-lab.zip"
    )
    build_archive(parser.parse_args().output)
