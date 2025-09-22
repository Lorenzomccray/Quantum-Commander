from fastapi import APIRouter, Header, HTTPException, Request
from typing import Any, Dict, List, Optional
import os
import json
import re
import time
import shutil
import subprocess
import http.client
import pathlib
from urllib.parse import urlparse

router = APIRouter()

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INBOX = ROOT / "data" / "patches" / "staged"
APPLIED = ROOT / "data" / "patches" / "applied"
LOG = ROOT / "data" / "patch_log.json"
for d in (DATA, INBOX, APPLIED):
    d.mkdir(parents=True, exist_ok=True)


def _load_log() -> Dict[str, Any]:
    if LOG.exists():
        try:
            return json.loads(LOG.read_text("utf-8"))
        except Exception:
            pass
    return {"log": []}


def _push_log(entry: Dict[str, Any]) -> None:
    db = _load_log()
    entry["ts"] = time.time()
    db["log"].insert(0, entry)
    db["log"] = db["log"][:500]
    LOG.write_text(json.dumps(db, indent=2), "utf-8")


def _http_json(method: str, url: str, timeout: int = 8):
    u = urlparse(url)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
    path = u.path + (("?" + u.query) if u.query else "")
    conn.request(method, path, headers={"User-Agent": "qc-patch/1.0"})
    res = conn.getresponse()
    raw = res.read().decode("utf-8", "ignore")
    try:
        return res.status, json.loads(raw)
    except Exception:
        return res.status, {"_raw": raw}


@router.get("/patch/log")
def patch_log() -> Dict[str, Any]:
    return _load_log()


@router.post("/patch/propose")
async def patch_propose(bundle: Dict[str, Any], request: Request):
    # minimal validation
    if not isinstance(bundle, dict) or "actions" not in bundle:
        raise HTTPException(400, "bundle must have 'actions'")
    name = bundle.get("title") or f"bundle-{int(time.time())}"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or f"bundle-{int(time.time())}"
    fname = f"{int(time.time())}-{safe}.json"
    (INBOX / fname).write_text(json.dumps(bundle, indent=2), "utf-8")
    try:
        ip = request.client.host  # type: ignore[attr-defined]
    except Exception:
        ip = None
    _push_log({"event": "propose", "name": fname, "ip": ip})
    return {"ok": True, "stored": fname}


def _write_file(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, "utf-8")


def _replace_regex(path: pathlib.Path, pattern: str, repl: str) -> None:
    s = path.read_text("utf-8")
    ns, n = re.subn(pattern, repl, s, flags=re.DOTALL)
    if n == 0:
        raise RuntimeError(f"replace_regex: no matches in {path}")
    path.write_text(ns, "utf-8")


def _restart_unit(unit: str) -> None:
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "restart", unit], check=True)


def _verify_http(url: str, expect_json_keys: Optional[List[str]] = None, expect_status: int = 200) -> None:
    st, j = _http_json("GET", url)
    if st != expect_status:
        raise RuntimeError(f"verify_http {url} status {st} != {expect_status}")
    if expect_json_keys:
        for k in expect_json_keys:
            if k not in j:
                raise RuntimeError(f"verify_http {url} missing key {k}")


@router.post("/patch/apply")
def patch_apply(name: str, x_patch_token: Optional[str] = Header(None)):
    token = os.getenv("PATCH_TOKEN", "")
    if not token or x_patch_token != token:
        raise HTTPException(403, "invalid patch token")
    src = INBOX / name
    if not src.exists():
        raise HTTPException(404, f"not found: {name}")
    bundle = json.loads(src.read_text("utf-8"))
    actions = bundle.get("actions") or []
    try:
        for act in actions:
            t = act.get("type")
            if t == "write_file":
                _write_file((ROOT / act["path"]), act.get("content", ""))
            elif t == "replace_regex":
                _replace_regex((ROOT / act["path"]), act["pattern"], act["repl"]) 
            elif t == "restart_service":
                _restart_unit(act.get("unit", "quantum-commander"))
            elif t == "verify_http":
                _verify_http(act["url"], act.get("expect_json_keys"), act.get("expect_status", 200))
            else:
                raise RuntimeError(f"unknown action type: {t}")
        dst = APPLIED / name
        shutil.move(str(src), str(dst))
        _push_log({"event": "apply", "name": name, "ok": True})
        return {"ok": True, "applied": name}
    except Exception as e:
        _push_log({"event": "apply", "name": name, "ok": False, "error": str(e)})
        raise HTTPException(400, f"apply failed: {e}")
