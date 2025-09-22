from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field
import os, re, json, subprocess
from typing import Optional

router = APIRouter()

# One-warning patterns (proceed only if confirm=true)
DANGER = [
    r"\brm\s+-rf\s+/(?!tmp|var/tmp)", r"\bmkfs\.", r"\bfdisk\b", r"\bparted\b",
    r"\bdd\s+if=", r"\bmount\s+-o\s+remount,ro\b",
    r"\bdnf\s+(-y\s+)?(remove|erase|autoremove|upgrade)\b",
    r"\byum\s+(-y\s+)?(remove|erase|autoremove)\b",
    r"\bapt(-get)?\s+(-y\s+)?(remove|purge|autoremove)\b",
    r"\bsystemctl\s+(disable|mask|stop)\s+(sshd|network|systemd|dbus)",
    r"\bchmod\s+-R\s+7[0-7]{2}\s+/(?!tmp|var/tmp)",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};\s*:",
    r"\bpoweroff\b", r"\bhalt\b", r"\breboot\b", r"\bshutdown\b",
]

class ShellReq(BaseModel):
    cmd: str = Field(..., description="Command to run as root (bash -lc)")
    cwd: Optional[str] = Field("/", description="Working directory")
    env: dict = Field(default_factory=dict)
    confirm: bool = Field(False, description="Set true to proceed if command is destructive")

def looks_dangerous(cmd: str) -> str | None:
    for pat in DANGER:
        if re.search(pat, cmd, flags=re.IGNORECASE):
            return pat
    return None

def verify_ops_token(x_ops_token: str = Header(default="")):
    """Dependency to verify OPS token - reads env per request for compatibility"""
    ops_token = os.getenv("OPS_TOKEN")
    if not ops_token or x_ops_token != ops_token:
        raise HTTPException(status_code=401, detail="unauthorized")
    return True

@router.post("/shell", dependencies=[Depends(verify_ops_token)])
def ops_shell(req: ShellReq):
    """Execute shell commands as root with destructive command protection"""
    pat = looks_dangerous(req.cmd)
    if pat and not req.confirm:
        # Single warning step - the only roadblock
        raise HTTPException(status_code=412, detail={
            "confirmation_required": True,
            "pattern": pat,
            "preview": f"About to run as root in {req.cwd or '/'}: {req.cmd}"
        })
    
    args = [
        "/usr/bin/sudo", "-n", "/usr/local/bin/qc-rootsh",
        "--cwd", req.cwd or "/",
        "--env-json", json.dumps(req.env or {}),
        req.cmd,
    ]
    
    cp = subprocess.run(args, text=True, capture_output=True)
    
    # Helper returns JSON on stdout
    try:
        payload = json.loads(cp.stdout.strip() or "{}")
    except Exception:
        payload = {"ok": False, "stdout": cp.stdout, "stderr": cp.stderr, "rc": cp.returncode}
    
    if cp.returncode != 0 or not payload.get("ok", False):
        raise HTTPException(status_code=500, detail=payload)
    
    return payload

@router.get("/health", dependencies=[Depends(verify_ops_token)])
def ops_health():
    """Simple health check for ops endpoints"""
    return {"status": "operational", "helper": "/usr/local/bin/qc-rootsh"}
