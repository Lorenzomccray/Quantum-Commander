from pathlib import Path
import json
import os
import tempfile


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        # Do not leak details; return empty on parse error
        return {}


def write_json_atomic(path: Path, data: dict) -> None:
    ensure_dir(path.parent)
    # Write to a temporary file in the same directory, then atomically replace
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent)) as tmp:
        json.dump(data, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
