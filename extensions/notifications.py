import subprocess

def notify(message: str):
    try:
        subprocess.run(["notify-send", message], check=False)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

