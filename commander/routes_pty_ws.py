from __future__ import annotations
import asyncio
import json
import os
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pathlib import Path
import shlex

router = APIRouter()
log = logging.getLogger("qc")

# Accept token via header or query param; compare to OPS_TOKEN
async def _verify_token(ws: WebSocket) -> bool:
    expected = os.getenv("OPS_TOKEN") or ""
    tok = ws.headers.get("x-ops-token") or ws.query_params.get("token") or ""
    return bool(expected and tok == expected)

@router.get("/terminal")
async def terminal_page():
    tpl = Path("templates/terminal.html")
    if tpl.exists():
        try:
            return HTMLResponse(tpl.read_text("utf-8"))
        except Exception as e:
            return PlainTextResponse(f"template read error: {e}", status_code=500)
    # Minimal fallback page
    html = """
    <!doctype html><html><head><meta charset='utf-8'><title>Terminal</title></head>
    <body><pre>templates/terminal.html not found. Create it, then refresh.\n\nWS endpoint: ws://127.0.0.1:8000/ops/pty?token=OPS_TOKEN</pre></body></html>
    """
    return HTMLResponse(html)

@router.get("/user-terminal")
async def user_terminal_page():
    tpl = Path("templates/user_terminal.html")
    if tpl.exists():
        try:
            return HTMLResponse(tpl.read_text("utf-8"))
        except Exception as e:
            return PlainTextResponse(f"template read error: {e}", status_code=500)
    html = """
    <!doctype html><html><head><meta charset='utf-8'><title>User Terminal</title></head>
    <body><pre>templates/user_terminal.html not found. Create it, then refresh.\n\nWS endpoint: ws://127.0.0.1:8000/pty</pre></body></html>
    """
    return HTMLResponse(html)

@router.websocket("/ops/pty")
async def ops_pty(ws: WebSocket):
    # Expect OPS_TOKEN in header or token= query param
    expected = os.getenv("OPS_TOKEN") or ""
    tok = ws.headers.get("x-ops-token") or ws.query_params.get("token") or ""
    if not expected:
        try:
            log.warning("ops_pty: OPS_TOKEN not set")
        except Exception:
            pass
    if not tok:
        try:
            log.warning("ops_pty: token missing in request")
        except Exception:
            pass
    elif expected and tok != expected:
        try:
            log.warning("ops_pty: token mismatch")
        except Exception:
            pass
    if not (expected and tok == expected):
        await ws.close(code=4401)
        return
    await ws.accept()

    # Spawn root PTY helper via sudo -n /usr/local/bin/qc-ptysh
    # Start with a sensible default size; frontend will send a resize event
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/sudo", "-n", "/usr/local/bin/qc-ptysh", "--cols", "100", "--rows", "28",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        await ws.send_text(f"[server-error] failed to start pty: {e}")
        await ws.close(code=1011)
        return

    CTRL_PREFIX = b"\x00\xff\x00"

    async def pump_out():
        try:
            while True:
                if proc.stdout.at_eof():
                    break
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                try:
                    await ws.send_bytes(chunk)
                except Exception:
                    break
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    async def pump_err():
        try:
            while True:
                if proc.stderr.at_eof():
                    break
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    break
                # send stderr bytes as well
                try:
                    await ws.send_bytes(chunk)
                except Exception:
                    break
        except Exception:
            pass

    async def pump_in():
        try:
            while True:
                try:
                    msg = await ws.receive()
                except WebSocketDisconnect:
                    break
                t = msg.get("type")
                if t == "websocket.disconnect":
                    break
                if "bytes" in msg and msg["bytes"] is not None:
                    data: bytes = msg["bytes"]
                    try:
                        proc.stdin.write(data)
                        await proc.stdin.drain()
                    except Exception:
                        break
                elif "text" in msg and msg["text"] is not None:
                    try:
                        j = json.loads(msg["text"]) if isinstance(msg["text"], str) else {}
                    except Exception:
                        j = {}
                    if isinstance(j, dict) and j.get("type") == "resize":
                        cols = int(j.get("cols") or 100)
                        rows = int(j.get("rows") or 28)
                        frame = CTRL_PREFIX + f"{cols} {rows}\n".encode()
                        try:
                            proc.stdin.write(frame)
                            await proc.stdin.drain()
                        except Exception:
                            break
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

    t_out = asyncio.create_task(pump_out())
    t_err = asyncio.create_task(pump_err())
    t_in = asyncio.create_task(pump_in())

    done, pending = await asyncio.wait({t_out, t_err, t_in}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    try:
        await asyncio.wait(pending)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass

@router.websocket("/pty")
async def user_pty(ws: WebSocket):
    await ws.accept()
    # Spawn a user shell with a PTY via `script` for compatibility
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/script", "-qfec", "bash -i", "/dev/null",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        await ws.send_text(f"[server-error] failed to start user pty: {e}")
        await ws.close(code=1011)
        return

    async def pump_out():
        try:
            while True:
                if proc.stdout.at_eof():
                    break
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                try:
                    await ws.send_bytes(chunk)
                except Exception:
                    break
        finally:
            try:
                await ws.close()
            except Exception:
                pass

    async def pump_err():
        try:
            while True:
                if proc.stderr.at_eof():
                    break
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    break
                try:
                    await ws.send_bytes(chunk)
                except Exception:
                    break
        except Exception:
            pass

    async def pump_in():
        try:
            while True:
                try:
                    msg = await ws.receive()
                except WebSocketDisconnect:
                    break
                t = msg.get("type")
                if t == "websocket.disconnect":
                    break
                if "bytes" in msg and msg["bytes"] is not None:
                    data: bytes = msg["bytes"]
                    try:
                        proc.stdin.write(data)
                        await proc.stdin.drain()
                    except Exception:
                        break
                elif "text" in msg and msg["text"] is not None:
                    # Support a simple resize/control protocol if needed later; ignore for user shell
                    try:
                        j = json.loads(msg["text"]) if isinstance(msg["text"], str) else {}
                    except Exception:
                        j = {}
                    if isinstance(j, dict) and j.get("type") == "resize":
                        # Not implemented for user shell
                        pass
        finally:
            try:
                proc.terminate()
            except Exception:
                pass

    t_out = asyncio.create_task(pump_out())
    t_err = asyncio.create_task(pump_err())
    t_in = asyncio.create_task(pump_in())

    done, pending = await asyncio.wait({t_out, t_err, t_in}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    try:
        await asyncio.wait(pending)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass

