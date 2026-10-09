"""Write local artifacts and verify their source provenance"""

import hashlib
import json
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    """Hash a file incrementally without loading it into memory"""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    """Write a strict JSON artifact atomically"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def seal_run(output: Path, project_root: Path, metadata: dict[str, Any]) -> None:
    """Save input metadata and hashes of outputs and executing source code"""
    files = {
        path.relative_to(output).as_posix(): file_sha256(path)
        for path in output.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    code = {
        path.relative_to(project_root).as_posix(): file_sha256(path)
        for path in (project_root / "src").rglob("*.py")
    }
    write_json(output / "manifest.json", {**metadata, "files": files, "code": code})
