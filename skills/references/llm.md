# Seed LLM — text generation (Ark Responses API)

Seed LLM generates text via the BytePlus **Ark Responses API**
(`POST /api/v3/responses`). It is **synchronous**: `seed_llm_generate` returns the
assistant's text in one call — there is nothing to poll.

## Models

| Model id | Alias | Use it for |
|---|---|---|
| `seed-2-0-pro-260328` | `pro` (default) | Quality, depth, harder reasoning |
| `dola-seed-2-1-turbo-260628` | `turbo` | Speed and lower cost |

- Select per call with `model` (full id **or** alias).
- Global default: `SEED_LLM_MODEL` env var (falls back to `seed-2-0-pro-260328`).
- Unknown ids are passed through to Ark unchanged, so new models work without a code
  change — but a typo shows up as an Ark 4xx. `seed_list_llm_models` lists what's known.

## Credentials

Needs `ARK_API_KEY` (or `BYTEPLUS_ARK_API_KEY`), **independent** of the audio keys.
Get one at <https://console.byteplus.com/ark/>. Resolution order: explicit arg → env →
`~/.seed/credentials` `ark_api_key` → `.env`.

## Basic usage

```jsonc
seed_llm_generate(
  prompt="Explain the CAP theorem in two sentences.",
  model="turbo"            // or "pro", or omit for the default
)
// → { "model": "...", "text": "...", "usage": {...} }
```

Optional knobs: `system` (system instruction), `temperature` (0.0–2.0),
`max_output_tokens`.

## Remote MCP tool use

The model can call **other MCP servers** on your behalf. Pass `mcp_servers`; the SDK adds
the required `ark-beta-mcp: true` header automatically.

```jsonc
seed_llm_generate(
  prompt="check the repo structure expressjs/express",
  model="seed-2-0-pro-260328",
  mcp_servers=[
    {
      "server_label": "deepwiki",
      "server_url": "https://mcp.deepwiki.com/mcp",
      "require_approval": "never"      // "never" runs tools without prompting
    }
  ]
)
```

Each server entry accepts:

- `server_url` (**required**) — the remote MCP endpoint.
- `server_label` — a short name (defaults to `mcp`).
- `require_approval` — `"never"` (default here) or a stricter policy.
- `allowed_tools` — optional allowlist of tool names on that server.
- `headers` — optional per-server auth headers.

When tools run, the result may include a `tool_calls` summary (type, name,
`server_label`, status). The `text` field is still the deliverable — surface the tool
activity only when it helps the user understand the answer.

**Trust:** only attach MCP servers the user trusts. A server with `require_approval:
"never"` will execute its tools autonomously during the generation.

## Wire shape (for reference)

`seed_llm_generate` maps directly onto the Ark request the console documents:

```json
{
  "model": "seed-2-0-pro-260328",
  "stream": true,
  "tools": [
    { "type": "mcp", "server_label": "deepwiki",
      "server_url": "https://mcp.deepwiki.com/mcp", "require_approval": "never" }
  ],
  "input": [
    { "role": "user", "content": [{ "type": "input_text", "text": "..." }] }
  ]
}
```

The MCP tool aggregates streamed output into a single response; the CLI (`seed chat`)
streams tokens live by default. Override the endpoint with `SEED_ARK_RESPONSES_URL` and
the timeout with `SEED_ARK_TIMEOUT` if needed.

## CLI equivalents

```bash
seed chat -p "Write a haiku about latency." --model turbo
seed chat -p "check the repo structure expressjs/express" \
  --mcp-url https://mcp.deepwiki.com/mcp --mcp-label deepwiki
seed models            # lists both audio and LLM models
```

## Troubleshooting

- `ARK_API_KEY is not configured` → set the key; it's separate from the audio credentials.
- Empty `text` with `tool_calls` present → the model only called tools; re-ask with a clear
  instruction to produce a final written answer, or verify the MCP `server_url`.
- Ark 4xx on submit → usually an unknown/misspelled `model` id; confirm with
  `seed_list_llm_models` or use the `pro`/`turbo` aliases.
