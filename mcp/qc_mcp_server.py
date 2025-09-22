#!/usr/bin/env python3
# Quantum Commander MCP server (stdio)
# Features:
# - Health and readiness checks
# - Generic HTTP request tool (safe, base-URL constrained)
# - Local file upload to QC HTTP endpoints
# - Runtime configuration of base URL, timeouts, retries, and optional API key
# - Echo tool for quick validation
#
# Compatibility goals:
# - Works with the "mcp" Python package API (Server, stdio_server, types)
# - Uses only httpx + stdlib; no breaking changes to your assistant
# - Defensive error handling, SSRF-resistant (only relative paths allowed)

from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import httpx
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# -----------------------
# Configuration & Client
# -----------------------

def _to_float(value: Optional[str], default: float) -> float:
    try:
        return float(value) if value is not None else default
    except Exception:
        return default


def _to_int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


DEFAULT_BASE_URL = os.getenv("QC_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_TIMEOUT = _to_float(os.getenv("QC_TIMEOUT"), 30.0)
DEFAULT_RETRIES = _to_int(os.getenv("QC_RETRIES"), 2)
DEFAULT_API_KEY = os.getenv("QC_API_KEY")

# httpx retry configuration (best-effort; older httpx may not have Retry)
try:  # httpx >= 0.27
    from httpx import Retry  # type: ignore

    _RETRY_CONFIG = Retry(total=DEFAULT_RETRIES, backoff_factor=0.5)
except Exception:  # pragma: no cover - fallback if Retry isn't available
    _RETRY_CONFIG = None


class QCClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        api_key: Optional[str] = DEFAULT_API_KEY,
    ) -> None:
        self.base_url = base_url.rstrip("/") or "http://127.0.0.1:8000"
        self.timeout = timeout
        self.retries = max(0, retries)
        self.api_key = api_key
        self._client = self._build_client()

    def _build_client(self) -> httpx.Client:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        transport_kwargs: Dict[str, Any] = {}
        if _RETRY_CONFIG is not None:
            transport_kwargs["retries"] = _RETRY_CONFIG
        transport = httpx.HTTPTransport(**transport_kwargs)

        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            transport=transport,
            http2=True,
        )

    def reconfigure(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update runtime config and rebuild the underlying client."""
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        if timeout is not None:
            self.timeout = float(timeout)
        if retries is not None:
            self.retries = int(retries)
        if api_key is not None:
            self.api_key = api_key

        try:
            self._client.close()
        except Exception:
            pass
        self._client = self._build_client()
        return self.get_config()

    def get_config(self) -> Dict[str, Any]:
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "retries": self.retries,
            "api_key_present": bool(self.api_key),
        }

    # ------------------
    # Convenience calls
    # ------------------
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        return self._client.get(_normalize_path(path), params=params)

    def post(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        return self._client.post(
            _normalize_path(path),
            json=json_body,
            data=data,
            files=files,
            params=params,
            headers=headers,
        )

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        method = method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError(f"Unsupported method: {method}")
        return self._client.request(
            method,
            _normalize_path(path),
            params=params,
            json=json_body,
            data=data,
            headers=headers,
        )


def _normalize_path(path: str) -> str:
    # Prevent SSRF: only allow relative paths on the configured base URL.
    if not path.startswith("/"):
        raise ValueError("Path must be relative (start with '/')")
    return path


CLIENT = QCClient()

# ---------
# MCP Server
# ---------
server = Server("qc-mcp")


def _json_text(payload: Any) -> List[types.TextContent]:
    try:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        body = str(payload)
    return [types.TextContent(type="text", text=body)]


@server.list_tools()
def list_tools() -> List[types.Tool]:
    return [
        types.Tool(
            name="echo",
            description="Echo back the provided text.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="health",
            description="GET /health on Quantum Commander.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="ready",
            description="GET /ready on Quantum Commander.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="server_info",
            description="GET / (root) to fetch basic server information.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="request",
            description=(
                "Generic HTTP request constrained to the configured base URL. "
                "Supports GET/POST/PUT/PATCH/DELETE with params/json/data/headers."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                    "path": {"type": "string", "description": "Relative path starting with '/'"},
                    "params": {"type": "object", "additionalProperties": True},
                    "json": {"type": "object", "additionalProperties": True},
                    "data": {"type": "object", "additionalProperties": True},
                    "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                },
                "required": ["method", "path"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="upload_file",
            description=(
                "Upload a local file to a QC endpoint (multipart/form-data). "
                "Provide the relative API path (e.g. '/files/upload') and local file_path."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path starting with '/'"},
                    "file_path": {"type": "string"},
                    "field_name": {"type": "string", "default": "file"},
                    "params": {"type": "object", "additionalProperties": True},
                    "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                },
                "required": ["path", "file_path"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="configure",
            description=(
                "Update runtime config: base_url, timeout, retries, api_key. "
                "Does not persist across restarts by default."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "base_url": {"type": "string"},
                    "timeout": {"type": "number"},
                    "retries": {"type": "integer"},
                    "api_key": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="get_config",
            description="Return current MCP server configuration.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
    ]


@server.call_tool()
def call_tool(name: str, arguments: Dict[str, Any]):
    try:
        if name == "echo":
            text = str(arguments.get("text", ""))
            return [types.TextContent(type="text", text=text)]

        if name == "health":
            try:
                r = CLIENT.get("/health")
                payload: Dict[str, Any] = {
                    "status_code": r.status_code,
                    "ok": r.is_success,
                    "body": _try_parse(r),
                }
            except httpx.RequestError as e:
                payload = {"error": f"RequestError: {e.__class__.__name__}: {e}"}
            return _json_text(payload)

        if name == "ready":
            try:
                r = CLIENT.get("/ready")
                payload = {"status_code": r.status_code, "ok": r.is_success, "body": _try_parse(r)}
            except httpx.RequestError as e:
                payload = {"error": f"RequestError: {e.__class__.__name__}: {e}"}
            return _json_text(payload)

        if name == "server_info":
            try:
                r = CLIENT.get("/")
                payload = {"status_code": r.status_code, "ok": r.is_success, "body": _try_parse(r)}
            except httpx.RequestError as e:
                payload = {"error": f"RequestError: {e.__class__.__name__}: {e}"}
            return _json_text(payload)

        if name == "request":
            method = str(arguments.get("method", "GET")).upper()
            path = str(arguments.get("path", "/"))
            params = arguments.get("params") or None
            json_body = arguments.get("json") or None
            data = arguments.get("data") or None
            headers = arguments.get("headers") or None

            try:
                r = CLIENT.request(method=method, path=path, params=params, json_body=json_body, data=data, headers=headers)
                payload = {"status_code": r.status_code, "ok": r.is_success, "body": _try_parse(r)}
            except (ValueError, httpx.RequestError) as e:
                payload = {"error": f"{e.__class__.__name__}: {e}"}
            return _json_text(payload)

        if name == "upload_file":
            path = str(arguments.get("path", "/"))
            file_path = str(arguments.get("file_path", ""))
            field_name = str(arguments.get("field_name", "file"))
            params = arguments.get("params") or None
            headers = arguments.get("headers") or None

            if not file_path:
                return _json_text({"error": "file_path is required"})
            if not os.path.isfile(file_path):
                return _json_text({"error": f"File not found: {file_path}"})

            mime, _ = mimetypes.guess_type(file_path)
            mime = mime or "application/octet-stream"

            try:
                with open(file_path, "rb") as fh:
                    files = {field_name: (os.path.basename(file_path), fh, mime)}
                    r = CLIENT.post(path, files=files, params=params, headers=headers)
                payload = {"status_code": r.status_code, "ok": r.is_success, "body": _try_parse(r)}
            except (ValueError, httpx.RequestError, OSError) as e:
                payload = {"error": f"{e.__class__.__name__}: {e}"}
            return _json_text(payload)

        if name == "configure":
            cfg = {}
            if "base_url" in arguments:
                cfg["base_url"] = str(arguments["base_url"]).rstrip("/")
            if "timeout" in arguments:
                cfg["timeout"] = float(arguments["timeout"])  # type: ignore[arg-type]
            if "retries" in arguments:
                cfg["retries"] = int(arguments["retries"])  # type: ignore[arg-type]
            if "api_key" in arguments:
                cfg["api_key"] = str(arguments["api_key"]) if arguments["api_key"] else None

            new_cfg = CLIENT.reconfigure(**cfg)
            return _json_text({"updated_config": new_cfg})

        if name == "get_config":
            return _json_text(CLIENT.get_config())

        return _json_text({"error": f"Unknown tool: {name}"})

    except Exception as e:
        # Top-level safety net: never crash the MCP server on tool errors
        return _json_text({"error": f"Unhandled {e.__class__.__name__}: {e}"})


# ---------------
# Helper functions
# ---------------

def _try_parse(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        text = None
        try:
            text = response.text
        except Exception:
            pass
        return {"text": text}


if __name__ == "__main__":
    stdio_server.run(server)
