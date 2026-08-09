# BytePlus Seed

Generate natural speech/audio with **Seed Audio 1.0** and text with the **Seed LLM**
(`seed-2-0-pro-260328`, `dola-seed-2-1-turbo-260628`) — from Claude, the terminal, or your
own code. Three surfaces over one zero-dependency SDK:

| I want to… | Use |
|---|---|
| Talk to Claude / Claude Code | **MCP server** (`seed-mcp`) |
| Generate from the terminal | **CLI** (`seed`) |
| Claude Code skill | **Skill** (`skills/seed.md`) |
| Build my own integration | **SDK** (`seed-sdk`) |

> **Two model families, one toolkit.** *Seed Audio* (speech/TTS + voice cloning) and *Seed
> LLM* (text generation, tool use, and remote-MCP passthrough via the BytePlus **Ark
> Responses API**). Audio needs `BYTEPLUS_SEED_API_KEY`; the LLM needs `ARK_API_KEY` — they
> are independent, set whichever you need.

> **Audio providers:** Seed Audio runs on **two interchangeable backends**, chosen with
> `SEED_PROVIDER`: **BytePlus** (default — the native `voice.ap-southeast-1.bytepluses.com`
> API, synchronous; also works against the Volcengine host via `SEED_BYTEPLUS_TTS_URL`) or
> **fal.ai** (`SEED_PROVIDER=fal`, `bytedance/seed-audio-1.0`, async). The SDK hides the
> wire-format differences behind one interface — the MCP tools, CLI, and skill are identical
> either way. See [`seed/providers/`](packages/seed-sdk/seed/providers/).

## Prerequisites

- **Python 3.10+** and a local clone of this repo.
- Credentials for whatever you want to use:
  - **Audio — BytePlus** (default): `BYTEPLUS_SEED_API_KEY` (or the legacy `BYTEPLUS_SEED_APP_ID` +
    `BYTEPLUS_SEED_ACCESS_KEY`) — from the BytePlus console (<https://console.byteplus.com/voice/>).
  - **Audio — fal.ai** (optional): a `FAL_KEY` (<https://fal.ai/dashboard/keys>), then `SEED_PROVIDER=fal`.
  - **LLM — Ark**: `ARK_API_KEY` from the Ark console (<https://console.byteplus.com/ark/>).

## Install

```bash
git clone https://github.com/mittulmadaan/byteplus-seed-mcp
cd byteplus-seed-mcp

# Install the three packages
pip install ./packages/seed-sdk ./packages/seed-mcp ./packages/seed-cli

# Or, for development (uv workspace):
uv sync --all-packages --dev
```

> Not on PyPI yet — install from the repo. PyPI publishing kicks in on the first
> `sdk/v*` | `mcp/v*` | `cli/v*` release tag (see [Release](#release)).

---

## 🖥 MCP Server

Expose Seed Audio to Claude Desktop / Claude Code.

### Local (stdio)

After installing (above):

```bash
export BYTEPLUS_SEED_API_KEY=<your-byteplus-key>   # default provider
# (or use fal: export FAL_KEY=<key> && export SEED_PROVIDER=fal)
python -m seed_mcp                  # stdio transport (default)
```

Register it with `seed skill install` (below), or add it manually:

```json
{
  "mcpServers": {
    "seed": { "command": "python", "args": ["-m", "seed_mcp"] }
  }
}
```

### Hosted (Docker / SSE)

```bash
docker build -t byteplus-seed-mcp .
docker run -p 8000:8000 \
  -e MCP_TRANSPORT=sse \
  -e SEED_PROVIDER=byteplus \
  -e BYTEPLUS_SEED_API_KEY=<key> \
  -e MCP_AUTH_TOKEN=<strong-random-token> \
  byteplus-seed-mcp
# health: GET http://localhost:8000/health
```

A `render.yaml` is included for one-click Render deployment. Point your MCP client at
`https://<host>/mcp` (streamable HTTP) with a bearer token — credentials stay server-side,
clients authenticate with `MCP_AUTH_TOKEN` only:

```json
{
  "mcpServers": {
    "seed": {
      "type": "http",
      "url": "https://<host>/mcp",
      "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
    }
  }
}
```

### Tools

| Tool | Purpose |
|---|---|
| `seed_audio_generate` | Submit an audio job → returns `request_id` (or the `audio_url` directly on synchronous providers like BytePlus) |
| `seed_check_task` | Poll until `completed`; returns `audio_url` (fal/async) |
| `seed_llm_generate` | Generate text with a Seed LLM (synchronous); optional remote-MCP tool use |
| `seed_list_voices` | List preset voice ids |
| `seed_list_models` | List Seed Audio models + capabilities |
| `seed_list_llm_models` | List Seed LLM models + capabilities |
| `seed_ping` | Liveness, active provider, credential check |

---

## 💻 CLI

```bash
seed auth login                      # stores provider keys in ~/.seed/credentials (BytePlus by default)

# Generate
seed generate \
  --prompt "A short suspense radio drama in a late-night convenience store." \
  --watch

# With a preset voice
seed voices                          # list presets
seed generate -p "Welcome back to the late show." -v sophie_en_zh --watch

# Voice cloning from reference audio
seed generate -p "In @Audio1's voice: 'Once upon a time…'" \
  --audio-ref https://cdn.example.com/narrator.mp3 --watch

# Track a job
seed status <request_id>
seed watch  <request_id>

# Skill management (Claude Desktop + Claude Code)
seed skill install
seed skill check
```

Run `seed --help` for the full command reference.

---

## 🧠 Seed LLM (text generation)

Text generation over the BytePlus **Ark Responses API**. Two models today, switchable per
call (`--model` / the `model` arg) or globally via `SEED_LLM_MODEL`:

| Model id | Alias |
|---|---|
| `seed-2-0-pro-260328` | `pro` (default) |
| `dola-seed-2-1-turbo-260628` | `turbo` |

```bash
export ARK_API_KEY=<your-ark-key>            # https://console.byteplus.com/ark/

# Plain text
seed chat -p "Explain the CAP theorem in two sentences." --model turbo

# Let the model call a remote MCP server (deepwiki) on your behalf
seed chat -p "check the repo structure expressjs/express" \
  --mcp-url https://mcp.deepwiki.com/mcp --mcp-label deepwiki
```

From the **MCP server**, the `seed_llm_generate` tool exposes the same thing to Claude —
including MCP-tool passthrough:

```jsonc
seed_llm_generate(
  prompt="check the repo structure expressjs/express",
  model="seed-2-0-pro-260328",               // or "turbo", or omit for the default
  mcp_servers=[{ "server_label": "deepwiki",
                 "server_url": "https://mcp.deepwiki.com/mcp",
                 "require_approval": "never" }]
)
```

From the **SDK**:

```python
from seed import SeedClient

client = SeedClient()
result = client.generate_text(
    "check the repo structure expressjs/express",
    model="seed-2-0-pro-260328",             # id or alias ("pro" / "turbo")
    mcp_servers=[{"server_label": "deepwiki",
                  "server_url": "https://mcp.deepwiki.com/mcp"}],
)
print(result.text)

# or stream tokens live
for delta in client.stream_text("Write a haiku about latency.", model="turbo"):
    print(delta, end="")
```

The SDK maps directly onto the Ark request shape (`model`, `stream`, `tools`, `input`) and
sets the `ark-beta-mcp: true` header automatically when MCP tools are attached.

---

## 🧠 Claude Code Skill

`skills/seed.md` (+ `skills/references/`) teaches Claude Code how to use Seed Audio well —
prompting, voice presets, cloning, multi-speaker scenes, and safety.

```bash
seed skill install                   # copies the skill + registers the MCP server
# restart Claude Code, then just ask it to "generate a 20s upbeat intro voiceover"
```

---

## 📦 SDK

```python
from seed import SeedClient

client = SeedClient()                                  # provider from SEED_PROVIDER (default: byteplus)
result = client.submit_audio(
    "A short suspense radio drama in a late-night convenience store.",
    output_format="mp3",
)
# BytePlus is synchronous — `result` is already completed. fal is async, so poll.
import time
while not result.terminal:
    time.sleep(5)
    result = client.check_task(result.request_id)
print(result.audio_url)
```

`seed-sdk` has **zero runtime dependencies** (stdlib `urllib` only).

---

## Repo structure

```
byteplus-seed-mcp/
├── packages/
│   ├── seed-sdk/      # core: client, types, credentials, llm, providers/{fal,byteplus}
│   ├── seed-mcp/      # FastMCP server (audio + LLM tools, stdio + SSE)
│   └── seed-cli/      # Typer + Rich CLI (generate + chat), skill installer
├── skills/            # seed.md + references/
├── Dockerfile         # SSE server image
├── render.yaml        # Render.com deployment
└── pyproject.toml     # uv workspace
```

## Credentials

Resolution order (first non-empty wins): explicit arg → env var → `~/.seed/credentials`
`[default]` → `.env`.

| Capability / provider | Env var(s) |
|---|---|
| Audio — BytePlus (default, new console) | `BYTEPLUS_SEED_API_KEY` |
| Audio — BytePlus (legacy console) | `BYTEPLUS_SEED_APP_ID` + `BYTEPLUS_SEED_ACCESS_KEY` |
| Audio — fal (`SEED_PROVIDER=fal`) | `FAL_KEY` |
| LLM — BytePlus Ark Responses API | `ARK_API_KEY` (or `BYTEPLUS_ARK_API_KEY`) |

> Never commit credentials or bake them into images. Protect hosted SSE endpoints with
> `MCP_AUTH_TOKEN`.

## Release

Independent per-package PyPI publishes via tags:

```bash
git tag sdk/v0.1.0 && git push --tags   # → seed-sdk
git tag mcp/v0.1.0 && git push --tags   # → seed-mcp
git tag cli/v0.1.0 && git push --tags   # → seed-cli
```

## Providers

```bash
# BytePlus (default, synchronous — submit returns the audio directly)
export BYTEPLUS_SEED_API_KEY=<key>   # or BYTEPLUS_SEED_APP_ID + BYTEPLUS_SEED_ACCESS_KEY

# fal (opt-in, async)
export FAL_KEY=<key> && export SEED_PROVIDER=fal
```

Voice ids differ between providers (fal presets vs BytePlus `speaker` ids). `seed ping` shows
the active provider and which credentials are configured.

## Roadmap

- [x] Native BytePlus Seed Audio provider (`SEED_PROVIDER=byteplus`)
- [x] Seed LLM text generation via the Ark Responses API (`seed_llm_generate` / `seed chat`)
- [x] Remote-MCP tool passthrough for the LLM (`ark-beta-mcp`)
- [ ] Local-file upload helper (host local audio/images → public URL)
- [ ] Additional Seed models as they ship

## Support

- Repo: <https://github.com/mittulmadaan/byteplus-seed-mcp>
- Seed Audio on fal: <https://fal.ai/models/bytedance/seed-audio-1.0>
- fal queue API: <https://docs.fal.ai/model-endpoints/queue>
- Volcano Engine (BytePlus) Audio Generation API: <https://www.volcengine.com/docs/6561/2550782>
