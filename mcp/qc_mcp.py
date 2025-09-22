import os, json, asyncio, httpx
from typing import List
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

API = os.getenv("QC_API", "http://127.0.0.1:8000").rstrip("/")
OPS_TOKEN = os.getenv("OPS_TOKEN", "")

server = Server("quantum-commander")

def T(text: str) -> List[TextContent]:
    return [TextContent(type="text", text=text)]

async def _get(path: str, **kw):
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{API}{path}", **kw)
        r.raise_for_status()
        return r

async def _post(path: str, **kw):
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(f"{API}{path}", **kw)
        r.raise_for_status()
        return r

@server.tool(description="Return QC /health JSON")
async def health() -> List[TextContent]:
    r = await _get("/health")
    return T(json.dumps(r.json(), indent=2))

@server.tool(description="List available bots (first 20)")
async def bots_list() -> List[TextContent]:
    r = await _get("/bots")
    data = r.json()
    items = data if isinstance(data, list) else data.get("bots", [])
    out = "\n".join(f"- {b.get('name')} {b.get('emoji','')}" for b in items[:20])
    return T(out or "(no bots)")

@server.tool(description="Search KB for a query")
async def kb_search(q: str, k: int = 5) -> List[TextContent]:
    r = await _get("/kb/search", params={"q": q, "k": k})
    return T(json.dumps(r.json(), indent=2))

@server.tool(description="Upload a local file into QC files store")
async def files_upload(path: str) -> List[TextContent]:
    p = os.path.expanduser(path)
    if not os.path.isfile(p):
        return T(f"File not found: {p}")
    async with httpx.AsyncClient(timeout=120.0) as c:
        with open(p, "rb") as fp:
            r = await c.post(f"{API}/files/upload", files={"file": (os.path.basename(p), fp)})
    try:
        j = r.json()
    except Exception:
        j = {"status": r.status_code, "text": r.text}
    return T(json.dumps(j, indent=2))

@server.tool(description="List stored files")
async def files_list() -> List[TextContent]:
    r = await _get("/files")
    return T(json.dumps(r.json(), indent=2))

@server.tool(description="Save a chat transcript payload to QC")
async def chats_save(title: str, transcript_json: str) -> List[TextContent]:
    try:
        transcript = json.loads(transcript_json)
    except Exception as e:
        return T(f"transcript_json is not valid JSON: {e}")
    # Accept either a list of {role,text} or an envelope {transcript:[...]}
    if isinstance(transcript, dict) and "transcript" in transcript:
        transcript = transcript.get("transcript")
    if not isinstance(transcript, list):
        return T("transcript should be a JSON list of messages: [{\"role\":\"user|assistant\",\"text\":\"...\"}]")
    r = await _post("/chats", json={"title": title, "transcript": transcript})
    try:
        j = r.json()
    except Exception:
        j = {"status": r.status_code, "text": r.text}
    return T(json.dumps(j, indent=2))

DANGER = [
    r"\brm\s+-rf\s+/(?!home/[^ ]+)", r"\bmkfs\w*\b", r"\bwipefs\b",
    r"\bdd\s+(if|of)=/dev/", r"\bdnf\s+remove(\s+|-y\s+)\*", r"\buserdel\b",
    r"\bchmod\s+-R\s+7[0-7][0-7]\s+/\b", r"\bchown\s+-R\s+root:root\s+/\b"
]

@server.tool(description="Run a guarded ops shell one-liner via QC")
async def ops_shell(cmd: str, confirm: bool = False) -> List[TextContent]:
    if not OPS_TOKEN:
        return T("OPS_TOKEN not set in environment for MCP server.")
    # Always send to QC (QC also enforces its own guard/policy)
    r = await _post(
        "/ops/shell",
        headers={"x-ops-token": OPS_TOKEN},
        json={"cmd": cmd, "confirm": confirm},
    )
    try:
        j = r.json()
    except Exception:
        j = {"status": r.status_code, "text": r.text}
    return T(json.dumps(j, indent=2))

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write)

if __name__ == "__main__":
    asyncio.run(main())
