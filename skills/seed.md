---
name: seed
description: Generate with BytePlus Seed models from Claude Code — Seed Audio 1.0 (text-to-speech, voice presets, voice cloning, multi-speaker drama) and Seed LLM text generation (seed-2-0-pro-260328 / dola-seed-2-1-turbo-260628) with remote-MCP tool use via the Ark Responses API.
version: 0.2.0
---

# Seed (Audio + LLM)

Use this skill to generate with **BytePlus Seed** models directly from Claude Code. Two
capabilities, independent credentials:

- **Seed Audio 1.0** — turn text (plus optional reference audio or an image) into natural,
  high-quality speech and sound. Needs `BYTEPLUS_SEED_API_KEY` (or `FAL_KEY`).
- **Seed LLM** — text generation with tool use and remote-MCP passthrough, via the Ark
  Responses API. Needs `ARK_API_KEY`. See [`references/llm.md`](references/llm.md).

Pick by task: audio out → **Seed Audio** (`seed_audio_generate`); text out / reasoning /
letting a model call other MCP servers → **Seed LLM** (`seed_llm_generate`).

> **Audio provider note:** Seed Audio runs through two interchangeable backends, selected with
> `SEED_PROVIDER`: **BytePlus** (default, synchronous — `seed_audio_generate` returns the
> `audio_url` in one call, no polling) or **fal.ai** (`SEED_PROVIDER=fal`, async — submit
> then poll). The tools behave the same either way; just check whether the submit result
> already carries `audio_url`. Voice ids differ between providers. See
> [`references/platform.md`](references/platform.md).

---

## 🚦 Pre-flight (audio)

1. **Craft the prompt first.** Before calling `seed_audio_generate`, shape the user's request
   into an effective audio prompt — see [`references/voice-prompting.md`](references/voice-prompting.md).
2. **Pick a voice path.** Either a **preset voice** (`seed_list_voices`) or **voice cloning**
   from reference audio — see [`references/voice-presets.md`](references/voice-presets.md) and
   [`references/reference-audio.md`](references/reference-audio.md).
3. **Confirm before submitting** when the request is ambiguous (which voice? which language?
   one speaker or several?).

---

## Core rules (audio)

1. **Check the submit result first.** `seed_audio_generate` returns a `TaskResult`. With
   **BytePlus** (synchronous) it already has `status == "completed"` and `audio_url` — you're
   done. With **fal** (async) it returns `status == "queued"`; then poll
   `seed_check_task(request_id)` every **5–10 seconds** until `status == "completed"`. Don't
   poll if the audio_url is already present.
2. **One voice path at a time.** `voice` (preset) and `audio_urls` (cloning) can be combined,
   but `audio_urls` and `image_url` are **mutually exclusive** — pass one or the other.
3. **Reference inputs must be PUBLIC URLs.** `audio_urls` (≤3, ≤30s & ≤10MB each) and
   `image_url` (≤10MB) must be URLs reachable by fal. Local file paths are **not supported
   yet** — ask the user for a public URL or to host the file.
4. **Reference clones by order.** In the prompt, refer to reference audio as `@Audio1`,
   `@Audio2`, `@Audio3`, matching the order of `audio_urls`. See
   [`references/reference-audio.md`](references/reference-audio.md).
5. **Multi-speaker / dialogue** (radio drama, conversations): see
   [`references/multi-speaker.md`](references/multi-speaker.md).
6. **Defaults:** `output_format=mp3`, `sample_rate=24000`, `speed=1.0`, `volume=1.0`. Only
   change these when the user asks (e.g. `wav` for editing, `48000` for high fidelity).
7. **Voice cloning needs consent.** Only clone voices the user is authorised to use. See
   [`references/safety.md`](references/safety.md).
8. **Hand back the `audio_url`** when complete. The URL is the deliverable — share it, or
   download it if the user wants a local file.

---

## MCP tools

| Tool | Purpose |
|---|---|
| `seed_audio_generate` | Submit an audio job (prompt + voice/audio_urls/image_url + format/rate/speed/volume/pitch). Returns `request_id`. |
| `seed_check_task` | Poll a job; returns `audio_url` when `status == "completed"`. |
| `seed_llm_generate` | Generate text with a Seed LLM (synchronous). Optional remote-MCP tool use. See [`references/llm.md`](references/llm.md). |
| `seed_list_voices` | List the preset voice ids. |
| `seed_list_models` | List Seed **Audio** models + capabilities. |
| `seed_list_llm_models` | List Seed **LLM** models + capabilities. |
| `seed_ping` | Check liveness, active provider, and credentials. |

### Parameters for `seed_audio_generate`

- `prompt` (required) — text to speak, or a description of the audio. Reference clones as `@Audio1…`.
- `voice` — preset voice id (omit when cloning only).
- `audio_urls` — up to 3 public reference audio URLs (voice cloning).
- `image_url` — one public reference image URL (mutually exclusive with `audio_urls`).
- `output_format` — `mp3` | `wav` | `pcm` | `ogg_opus` (default `mp3`).
- `sample_rate` — `8000` | `16000` | `24000` | `32000` | `44100` | `48000` (default `24000`).
- `speed` — `0.5`–`2.0` (default `1.0`). `volume` — `0.5`–`2.0` (default `1.0`).
- `pitch` — semitones, `-12`…`12` (`0` = normal).

---

## Typical audio flow

1. Clarify intent (voice, language, single vs multi-speaker).
2. (Optional) `seed_list_voices` to pick a preset.
3. Craft the prompt ([`references/voice-prompting.md`](references/voice-prompting.md)).
4. `seed_audio_generate(...)` → get `request_id`.
5. Poll `seed_check_task(request_id)` every 5–10s until `completed`.
6. Return the `audio_url`.

---

## 🧠 Seed LLM (text generation)

Text generation via the BytePlus **Ark Responses API** — synchronous (`seed_llm_generate`
returns the text directly, no polling). Full details in [`references/llm.md`](references/llm.md).

### Core rules (LLM)

1. **Synchronous — no polling.** `seed_llm_generate` returns the answer in the `text` field.
   Never call `seed_check_task` on an LLM result (that's audio-only).
2. **Model is switchable, default is `seed-2-0-pro-260328`.** Pass `model` as a full id or a
   short alias: `pro` → `seed-2-0-pro-260328`, `turbo` → `dola-seed-2-1-turbo-260628`. Omit to
   use the default (or the `SEED_LLM_MODEL` env override). Prefer **`pro`** for quality/depth,
   **`turbo`** for speed/cost. Confirm `seed_list_llm_models` if unsure which exist.
3. **Remote MCP tool use.** To let the model call another MCP server, pass `mcp_servers` — a
   list of `{"server_label", "server_url", "require_approval": "never"}`. The `ark-beta-mcp`
   header is set for you. Example: give it `https://mcp.deepwiki.com/mcp` to answer questions
   about a GitHub repo. Only attach servers the user trusts.
4. **`ARK_API_KEY` is separate** from the audio key. If it's missing, the tool errors with
   `ARK_API_KEY is not configured` — tell the user to set it (`export ARK_API_KEY=...` or
   `seed auth login`), don't fall back to audio.
5. **Report tool activity.** When `mcp_servers` are used, the result may include `tool_calls`;
   mention what the model called if relevant, and hand back the `text` as the deliverable.

### Parameters for `seed_llm_generate`

- `prompt` (required) — the user message / task.
- `model` — id or alias (`pro` | `turbo` | full id). Empty = default.
- `system` — optional system instruction.
- `mcp_servers` — optional `[{"server_label", "server_url", "require_approval", "allowed_tools"?}]`.
- `tools` — optional raw Ark tool specs (advanced; merged with `mcp_servers`).
- `temperature` — `0.0`–`2.0` (optional). `max_output_tokens` — cap on output (optional).

### Typical LLM flow

1. Decide the model (`pro` vs `turbo`); default is fine when unspecified.
2. If the task needs external data/tools, attach `mcp_servers`.
3. `seed_llm_generate(prompt=..., model=..., mcp_servers=...)`.
4. Return the `text`; surface `tool_calls`/`usage` when useful.

---

## Troubleshooting

- **`FAL_KEY is not configured`** → run `seed auth login` or `export FAL_KEY=...`. See
  [`references/platform.md`](references/platform.md).
- **`audio_urls and image_url are mutually exclusive`** → pass only one.
- **`Too many audio_urls`** → max 3 reference clips.
- **Reference URL rejected / 4xx** → the URL must be publicly fetchable (not localhost, not a
  signed URL that expires); re-host on a public bucket.
- **`BytePlus Seed Audio credentials are not configured`** → `SEED_PROVIDER=byteplus` but no
  key set; `export BYTEPLUS_SEED_API_KEY=...` (or the legacy app-id/access-key pair), or switch
  back with `SEED_PROVIDER=fal`.
- **`BytePlus Seed Audio is synchronous … no task to poll`** → you called `seed_check_task` on a
  BytePlus result; the audio_url was already returned by `seed_audio_generate`.
- **`ARK_API_KEY is not configured`** (LLM) → the Seed LLM key is unset; `export ARK_API_KEY=...`
  or `seed auth login`. It's independent of the audio credentials.
- **LLM returns empty `text` but has `tool_calls`** → the model only invoked tools without a
  final answer; re-ask with a clearer instruction to summarise, or check the MCP server URL.
- **Unknown model id** → ids pass through to Ark unchanged, so a typo surfaces as an Ark 4xx.
  Confirm the id with `seed_list_llm_models`, or use the `pro`/`turbo` aliases.
