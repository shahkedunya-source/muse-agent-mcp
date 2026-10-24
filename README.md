# Muse Agent MCP — deployment template

## What this is

A minimal MCP server named **Muse Agent MCP** with three tools:

- `generate_image(prompt)` — queues a job, returns `job_id`
- `generate_video(prompt)` — queues a job, returns `job_id`
- `check_job(job_id)` — returns the job record

Transport is Streamable HTTP: `POST /mcp` with JSON-RPC 2.0, plus `GET /health`.
This matches what Claude remote MCP connectors expect. It does **not** by itself
make the server reachable by Claude.

## Capability check in this environment (verified 2026-10-24)

| Capability | Result |
|---|---|
| Create files in the workspace | Yes — this folder is writable and persists |
| Run a Python server locally | Yes — Python 3.12, tested on 127.0.0.1 |
| Execute image/video generation from inside the server process | No — this server only queues jobs. Generation must be done by a separate worker that calls a real generation API with its own key, or by an agent that polls the queue |
| Expose a stable public HTTPS endpoint reachable by Claude | **No — this is the missing capability** |
| Persistent service across VM replacement | No — processes on this VM do not survive replacement; a deployed host with a supervisor is required |

**Conclusion: the connector is NOT connected, and no public URL is provided below,
because none was verified.** Do not add a URL to Claude until you have deployed
this code to a host you control and verified it from the public internet.

## Local test (verified steps)

```bash
cd muse-agent-mcp
MCP_BEARER_TOKEN=<your-test-token> python3 server.py
# in another terminal:
curl -s http://127.0.0.1:8000/health
curl -s -H "Authorization: Bearer <your-test-token>" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
  http://127.0.0.1:8000/mcp
curl -s -H "Authorization: Bearer <your-test-token>" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
  http://127.0.0.1:8000/mcp
```

Expected: `initialize` returns `serverInfo.name = "Muse Agent MCP"`,
`tools/list` returns the 3 tools above. A request without the token must get 401.

## What is still missing for Claude

1. **A public host with TLS.** Deploy this code to a VPS, Fly.io, Render,
   Railway, or similar, behind HTTPS on a domain you control, e.g.
   `https://mcp.example.com/mcp`. This VM cannot provide that.
2. **A real OAuth 2.1 authorization server.** Claude remote connectors require
   OAuth discovery and authorization. Do not invent a custom OAuth flow and
   do not put credentials in the URL. Use an established provider (for
   example Auth0, Okta, Keycloak, or your cloud provider's identity service),
   configure it to protect `/mcp`, and publish its standard discovery
   documents. The Bearer-token check in `server.py` is for local testing only
   and is not a substitute for that OAuth setup.
3. **A generation worker.** Write a worker that polls `jobs.json` (or a real
   queue/database in production), calls your chosen generation API with a key
   stored in an environment variable (never in code or in a URL), writes the
   output file, and updates the job to `done` with a `download_url`. Keep
   secrets in environment variables / a secrets manager only.
4. **Public verification.** From outside your network, test:
   `initialize` → `tools/list` → `tools/call generate_image` → `check_job`,
   all over the public HTTPS URL with a valid OAuth token. Only after that
   passes should you add the connector in Claude.

## Adding it in Claude (only after public verification)

1. In Claude: Customize → Connectors → Add custom connector
2. Name: `Muse Agent MCP`
3. MCP server URL: your verified public URL, e.g. `https://mcp.example.com/mcp`
   — replace this with your real deployed URL; there is no verified URL yet.
4. Complete the OAuth sign-in shown by Claude using your real authorization
   server. If Claude cannot discover the server or sign-in fails, the
   connector is not connected — do not work around it with query-string keys.

## Secrets

- Never commit `MCP_BEARER_TOKEN` or any API key to the repo.
- Set them as environment variables on the deployed host.
- Never print them in chat, logs, or job records. Job records in this template
  store only the prompt and status, not credentials.
