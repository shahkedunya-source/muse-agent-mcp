#!/usr/bin/env python3
"""
Muse Agent MCP — minimal Streamable HTTP MCP server (local / deployment template).

Transport: POST /mcp with JSON-RPC 2.0, as used by Claude remote MCP connectors.
This is NOT a public endpoint by itself. To be reachable by Claude you must
deploy it behind TLS on a host with a public domain, and front it with a
real OAuth 2.1 authorization server (see README.md). Do NOT put credentials
in URL query parameters, and do NOT invent a custom OAuth implementation.

Tools:
  - generate_image(prompt: str) -> queues a job, returns job_id
  - generate_video(prompt: str) -> queues a job, returns job_id
  - check_job(job_id: str) -> returns the job record

Jobs are persisted to jobs.json next to this file. Actual media generation
is done by a separate worker that calls a real generation API with its own
API key from the environment. This server alone does not generate media.

Auth for local testing:
  If MCP_BEARER_TOKEN is set, /mcp requires:
    Authorization: Bearer <token>
  If it is not set, /mcp is unauthenticated (local testing only — never
  deploy unauthenticated).

Run locally:
  MCP_BEARER_TOKEN=test-only-token python3 server.py
  # listens on 127.0.0.1:8000 by default; set PORT to change it.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
JOBS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.json")
BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "")

SERVER_INFO = {"name": "Muse Agent MCP", "version": "0.1.0"}

TOOLS = [
    {
        "name": "generate_image",
        "description": "Queue an image generation job for the given prompt.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "generate_video",
        "description": "Queue a video generation job for the given prompt.",
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "check_job",
        "description": "Check the status of a queued job by job_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
]


def load_jobs():
    if not os.path.exists(JOBS_FILE):
        return {}
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_jobs(jobs):
    tmp = JOBS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)
    os.replace(tmp, JOBS_FILE)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        # Keep logs free of prompts and tokens.
        pass

    def _send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self):
        if not BEARER_TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {BEARER_TOKEN}":
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Bearer realm="Muse Agent MCP"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"ok": True, "server": SERVER_INFO["name"]})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/mcp":
            self._send_json(404, {"error": "not_found"})
            return
        if not self._check_auth():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            msg = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {}) or {}

        # Notifications have no id and need no response body in MCP over
        # Streamable HTTP; return 202.
        if msg_id is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        def ok(result):
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}

        def err(code, message):
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

        if method == "initialize":
            self._send_json(200, ok({
                "protocolVersion": params.get("protocolVersion", "2025-03-26"),
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }))
            return
        if method == "ping":
            self._send_json(200, ok({}))
            return
        if method == "tools/list":
            self._send_json(200, ok({"tools": TOOLS}))
            return
        if method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {}) or {}
            if name in ("generate_image", "generate_video"):
                prompt = args.get("prompt", "")
                if not isinstance(prompt, str) or not prompt.strip():
                    self._send_json(200, err(-32602, "prompt must be a non-empty string"))
                    return
                jobs = load_jobs()
                job_id = str(uuid.uuid4())
                jobs[job_id] = {
                    "job_id": job_id,
                    "type": name,
                    "prompt": prompt,
                    "status": "queued",
                    "created_at": now_iso(),
                    "download_url": None,
                }
                save_jobs(jobs)
                self._send_json(200, ok({
                    "content": [{"type": "text", "text": json.dumps({"job_id": job_id, "status": "queued"})}],
                }))
                return
            if name == "check_job":
                job_id = args.get("job_id", "")
                jobs = load_jobs()
                job = jobs.get(job_id)
                if job is None:
                    self._send_json(200, err(-32602, "unknown job_id"))
                    return
                self._send_json(200, ok({
                    "content": [{"type": "text", "text": json.dumps(job)}],
                }))
                return
            self._send_json(200, err(-32601, f"unknown tool {name!r}"))
            return
        self._send_json(200, err(-32601, f"unknown method {method!r}"))


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Muse Agent MCP listening on http://{HOST}:{PORT}/mcp (health: /health)")
    print("Auth: " + ("Bearer token required (from MCP_BEARER_TOKEN)" if BEARER_TOKEN else "none — local testing only"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
