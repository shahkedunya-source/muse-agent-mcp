# Deploy Muse Agent MCP on a proper host

## Status: NOT deployed yet

No host account, domain, OAuth provider, or generation API key is connected
to this workspace, so I cannot deploy it myself from here. What is ready
below is the complete deployment package. The final deploy needs one of
these from you: a host account you control.

## What is ready

- `server.py` — MCP server, tested locally (initialize, tools/list,
  tools/call, check_job, 401 without token)
- `Dockerfile` — Python 3.12-slim, stdlib only, listens on $PORT
- `fly.toml` — Fly.io config (HTTPS forced, /health check)
- `render.yaml` — Render blueprint (HTTPS automatic, /health check)

## Option A — Render (simplest, no CLI needed)

1. Create a free Render account, then New -> Web Service.
2. Upload/connect the `muse-agent-mcp` folder.
3. Set environment variables in Render only (never in code or chat):
   - `HOST=0.0.0.0`
   - `MCP_BEARER_TOKEN=<a long random token you generate>`
4. Deploy. Render gives you a URL like `https://muse-agent-mcp.onrender.com`.
5. Test from outside:
   - `GET https://<your-url>/health` should return `{"ok": true}`
   - `POST https://<your-url>/mcp` with `Authorization: Bearer <token>`
     and an `initialize` body should return `serverInfo.name = "Muse Agent MCP"`.

## Option B — Fly.io (CLI)

```bash
fly auth login
cd muse-agent-mcp
fly launch --no-deploy
fly secrets set MCP_BEARER_TOKEN=<your-token>
fly deploy
fly open
```

Your URL will be `https://<your-app-name>.fly.dev`.

## What deployment alone does NOT solve

1. **Claude OAuth.** Claude remote connectors require a real OAuth 2.1
   authorization server with standard discovery. The Bearer token in this
   template is for local testing only. You must put an established
   provider (for example Auth0, Okta, or Keycloak) in front of `/mcp`
   before Claude sign-in will succeed. Do not invent a custom OAuth flow
   and do not put credentials in the MCP URL.
2. **Generation worker.** This server only queues jobs. `check_job` will
   stay `queued` until a worker calls a real generation API with its own
   API key (from environment variables) and marks jobs `done` with a
   `download_url`.
3. **Persistence.** `jobs.json` on a host without a persistent disk will
   be lost on redeploy. For production, attach a disk (Fly volume /
   Render disk) or move jobs to a database.

## Do not do this

- Do not paste the placeholder `https://mcp.example.com/mcp` into Claude.
  That domain is an example only and points to no server.
- Do not add any URL to Claude until steps 1-2 above are verified from
  the public internet. Until then, the connector is NOT connected.
