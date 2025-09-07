from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os, time, uuid, json

router = APIRouter()
ROOT = Path(os.environ.get("QC_UPLOAD_DIR","uploads"))
ROOT.mkdir(parents=True, exist_ok=True)

META = ROOT / "_meta.json"

def _load_meta():
    if not META.exists():
        return []
    try:
        return json.loads(META.read_text("utf-8"))
    except Exception:
        return []

def _save_meta(rows):
    tmp = META.with_suffix('.tmp.json')
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(META)

@router.post("/files/upload")
async def upload(file: UploadFile = File(...)):
    max_size = int(os.environ.get("QC_MAX_UPLOAD","10485760"))
    # Some servers may not set size; enforce a best-effort stream limit
    fid = uuid.uuid4().hex
    safe_name = Path(file.filename).name
    dest = ROOT / f"{fid}_{safe_name}"
    size = 0
    with dest.open("wb") as w:
        while True:
            chunk = await file.read(1024*1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_size:
                try:
                    dest.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(413, "file too large")
            w.write(chunk)
    rows = _load_meta()
    rows.insert(0, {"id": fid, "name": safe_name, "path": dest.name, "size": size, "ts": time.time()})
    _save_meta(rows)
    return {"ok": True, "file": rows[0]}

@router.get("/files")
def list_files():
    return {"ok": True, "files": _load_meta()}

@router.get("/files/{fid}")
def get_file(fid: str):
    for row in _load_meta():
        if row["id"] == fid:
            return FileResponse((ROOT / row["path"]).as_posix(), filename=row["name"])
    raise HTTPException(404, "not found")

