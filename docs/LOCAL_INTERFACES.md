# Local Interfaces & Optional Companion Services

Context Gate works out of the box with **Python 3.9+ standard library only** (`python3 console/app.py`).
All companion services below are **optional**: when not configured or offline, the console degrades gracefully and never blocks core features.

---

## 1. Core State & Local API

- Default state directory: `~/.local/state/context-gate` (override via `--state-dir` or `CONTEXT_GATE_STATE`).
- All local HTTP servers bind strictly to `127.0.0.1`, reject cross-origin browser requests (`Origin` header), and store connection/token files with `0600` permissions.
- `gate_service.py` endpoints (Bearer token from `<state_dir>/access-token`):
  - `GET /health`
  - `POST /v1/pack` — build a Context Pack
  - `POST /v1/turn` — prepare an API payload (`responses`, `chat`, `anthropic`)
  - `POST /v1/warm` — warm up reviewer credentials
  - `POST /v1/evidence`, `GET /v1/evidence`, `GET /v1/evidence/verify`

---

## 2. Optional Local Model Router

The **Model Router** tab and capability table connect to an optional local router service (OpenAI-compatible proxy + SQLite request log + authenticated management bridge). Configure via environment variables or place the default files in place:

| Environment Variable | Default | Purpose |
| :--- | :--- | :--- |
| `LMR_CONSOLE_CONNECTION` | `~/Library/Application Support/com.localmodelrouter.desktop/console-bridge.json` | JSON file (`0600`) with `{"version": 1, "port": <int>, "token": "<alnum 32-128>"}` for the router management bridge (`POST http://127.0.0.1:<port>/call`) |
| `LMR_ROUTER_URL` | `http://127.0.0.1:8787` | Base URL of the local OpenAI-compatible router |
| `ROUTER_DB` | `~/Library/Application Support/com.localmodelrouter.desktop/router.db` | Read-only SQLite database (`requests`, `providers`, `provider_keys`, `models` tables) used by `usage_import.py` and `console_capability.py` |

When not configured, the console shows an unconfigured state and all other tabs continue working normally.

---

## 3. Optional External Memory Service (MemoryOS Interface)

Context Gate supports injecting weighted project memory into Context Packs and browsing human-readable memory snapshots from an optional loopback memory service. **No private memory models or datasets are bundled in this repository.**

When not configured, Context Pack generation automatically falls back to local markdown core memory (`[CORE_MEMORY_START] ... [CORE_MEMORY_END]`).

| Environment Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MEMORY_OS_DIR` | `~/Library/Application Support/MemoryOS` | Optional base directory containing `client.json` / `ReaderDocuments` |
| `MEMORY_OS_HTTP_URL` | *(from `client.json`)* | Loopback HTTP endpoint exposing `GET /v1/context` and `GET /v1/state` |
| `MEMORY_OS_API_TOKEN` | *(from `client.json`)* | Bearer token for the loopback memory HTTP API |
| `MEMORY_OS_HUMAN_DIR` | `<MEMORY_OS_DIR>/ReaderDocuments` | Directory containing exported `catalog.json` (schema v2) and Markdown reading files |
| `MEMORY_OS_LIVE_URL` | `http://127.0.0.1:18766` | Optional loopback live-event listener (`GET /api/state`) |
| `MEMORY_OS_CLI` | `~/.local/bin/memory-os` | Optional CLI for project bootstrap indexing |
| `MEMORY_OS_GALAXY_DIR` | `<MEMORY_OS_DIR>/GalaxyResources` | Optional directory containing local Galaxy visualization resources |

Loopback-only enforcement is always active: non-loopback URLs are rejected and HTTP redirects are disabled.

---

## 4. Optional Decision Reviewers (Jev / Laya)

Context Gate uses deterministic local retrieval first, and can optionally call a primary/secondary decision reviewer:

- **Primary reviewer (Jev-compatible decision API)**:
  - `JEV_MCP_API_KEY`: API key (or `JEV_KEYCHAIN_HELPER` script supporting `get`)
  - `JEV_MCP_BASE_URL`: default `https://api.typesafe.ai/v1` (HTTPS or loopback required)
  - `JEV_MCP_DECISIONS_PATH`: default `/systemone`
  - `JEV_MCP_MODEL`: default `jev-latest`
  - `JEV_MCP_AUTH_HEADER` / `JEV_MCP_AUTH_SCHEME`: default `Authorization` / `Bearer`
- **Secondary / local reviewer (Laya-compatible loopback service or CLI)**:
  - Configure `laya_url` or `laya_command` in your config JSON (see `config.example.json`), or set `LAYA_URL` (must be loopback) and optional `LAYA_API_TOKEN`.
  - Protocol: `POST` JSON `{"state": {...}, "questions": {...}}` -> `{"answers": {<id>: {"choice": "yes"|"no", "confidence": 0..1}}}`.

If neither reviewer is configured or reachable, Context Pack falls back safely to full context and console search falls back to local literal search.

---

## 5. Optional Butler / Local Open-Source Models (Ollama / OpenAI-Compatible)

The console Butler can use a local [Ollama](https://ollama.com/) model or any OpenAI/Anthropic-compatible API (configurable in the console UI or via env vars):

| Environment Variable | Default | Purpose |
| :--- | :--- | :--- |
| `CONTEXT_GATE_OLLAMA_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `CONTEXT_GATE_OLLAMA_MODEL` | *(auto-detects Qwen 14B or first installed model)* | Explicit Ollama model tag (e.g. `qwen2.5:14b`, `qwen3:14b`) |
| `CONTEXT_GATE_BUTLER_API_URL` | `https://integrate.api.nvidia.com/v1/chat/completions` | Default OpenAI-compatible chat completions endpoint |
| `CONTEXT_GATE_BUTLER_API_KEY` | *(or `NVIDIA_API_KEY`)* | API key for the default endpoint |
| `CONTEXT_GATE_BUTLER_MODEL` | `moonshotai/kimi-k3` | Default model ID |

---

## 6. Optional Single-Machine Git Sync (`tools/git_sync_engine.py`)

Single-machine GitHub sync UI (`console/git_ui.py`) reads logs and `registry.json` from `GITSYNC_HOME` (default `~/.local/state/context-gate/git-sync`). Multi-device state replication is not included in this release.

| Environment Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GITSYNC_HOME` | `~/.local/state/context-gate/git-sync` | Registry, state, and log directory |
| `GITSYNC_GITHUB_OWNER` | *(empty)* | Your GitHub username/org for distinguishing own repos vs third-party repos |
| `GITSYNC_DISCOVER_ROOTS` | `~/Projects` | Colon-separated roots scanned by `discover` |
| `GITSYNC_AUTHOR_NAME` / `GITSYNC_AUTHOR_EMAIL` | *(uses repo/global `git config`)* | Optional fallback commit author |
| `GITSYNC_NOTIFY` | `osascript` | `osascript`, `file:<path>`, or `none` |
