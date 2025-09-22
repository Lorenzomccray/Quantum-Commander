from __future__ import annotations
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
import subprocess, os, shutil, platform, time, json

router = APIRouter()


def _run(cmd: list[str]) -> str:
    try:
        cp = subprocess.run(cmd, text=True, capture_output=True, check=False)
        out = cp.stdout.strip()
        if not out:
            out = cp.stderr.strip()
        return out
    except Exception as e:
        return f"error running {' '.join(cmd)}: {e}"


@router.get("/diagnostics/logs", response_class=PlainTextResponse)
def get_logs(lines: int = Query(default=300, ge=10, le=2000)):
    """Return recent user journal for the service."""
    return _run(["journalctl", "--user", "-u", "quantum-commander.service", "-n", str(lines), "--no-pager"]) or "(no logs)"


@router.get("/diagnostics/service")
def service_status():
    status = _run(["systemctl", "--user", "--no-pager", "status", "quantum-commander.service"])
    socket = _run(["systemctl", "--user", "--no-pager", "status", "quantum-commander.socket"])
    active = _run(["systemctl", "--user", "is-active", "quantum-commander.service"]).strip()
    enabled = _run(["systemctl", "--user", "is-enabled", "quantum-commander.service"]).strip()
    return {"active": active, "enabled": enabled, "status": status, "socket": socket}


def _meminfo():
    info = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()
    except Exception:
        pass
    return info


def _uptime_seconds() -> float:
    try:
        with open("/proc/uptime", "r") as f:
            return float(f.read().split()[0])
    except Exception:
        return 0.0


@router.get("/diagnostics/sysinfo")
def sysinfo():
    home = os.path.expanduser("~")
    root_disk = shutil.disk_usage("/")
    home_disk = shutil.disk_usage(home)
    cpu_count = os.cpu_count() or 0
    mem = _meminfo()
    try:
        import importlib.metadata as md  # py3.8+
    except Exception:
        md = None  # type: ignore

    def _pkg(name: str):
        try:
            if md:
                return md.version(name)
        except Exception:
            return None
        return None

    # Keys presence only (no secrets)
    keys = {}
    try:
        from app.settings import settings  # type: ignore
        keys = {
            "openai": bool(getattr(settings, "OPENAI_API_KEY", None)),
            "anthropic": bool(getattr(settings, "ANTHROPIC_API_KEY", None)),
            "groq": bool(getattr(settings, "GROQ_API_KEY", None)),
            "deepseek": bool(getattr(settings, "DEEPSEEK_API_KEY", None)),
        }
    except Exception:
        pass

    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "uptime_s": int(_uptime_seconds()),
        },
        "cpu": {"logical": cpu_count},
        "mem": {"MemTotal": mem.get("MemTotal"), "MemFree": mem.get("MemFree"), "MemAvailable": mem.get("MemAvailable")},
        "disk": {
            "/": {"total": root_disk.total, "used": root_disk.used, "free": root_disk.free},
            home: {"total": home_disk.total, "used": home_disk.used, "free": home_disk.free},
        },
        "packages": {
            "fastapi": _pkg("fastapi"),
            "uvicorn": _pkg("uvicorn"),
            "httpx": _pkg("httpx"),
            "openai": _pkg("openai"),
            "anthropic": _pkg("anthropic"),
            "groq": _pkg("groq"),
        },
        "keys_set": keys,
        "env_sample": [k for k in os.environ.keys() if k.upper().endswith("_URL") or k.upper().endswith("_MODEL")][:20],
    }