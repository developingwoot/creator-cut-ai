# ADR-007 — Ollama as Local LLM/VLM Runtime; Cloud Fallback Config-Gated

**Status:** Accepted  
**Date:** 2026-04-24

---

## Context

CreatorCutAI v0.1.0-alpha was built with Anthropic (Claude) as the sole AI inference
backend. Three call sites existed:

- Pass 1 — per-clip VLM analysis (`claude-sonnet-4-6`, base64 frames + transcript)
- Pass 2 — edit plan director LLM (`claude-opus-4-7`, all analyses + story brief)
- Rename suggestions — short clip naming LLM (`claude-sonnet-4-6`, transcript)

The product is a Tauri desktop app targeting YouTube creators and documentary filmmakers.
The hard requirements driving this decision:

1. Raw video (up to 4K, hundreds of GB) must never leave the machine.
2. The app must be usable offline.
3. Creators should not need an API key or a subscription to a third-party LLM service
   to use the core editing features.
4. The existing Tauri/Python/FFmpeg/faster-whisper stack should be preserved — a rewrite
   in another language would discard ~1200 LOC and 163 tests for a partial distribution win.

---

## Decision

Replace all three Anthropic call sites with **Ollama** (`http://127.0.0.1:11434`) as the
default inference runtime. Anthropic is retained as an opt-in cloud fallback, activated
by setting `CREATORCUT_CLOUD_FALLBACK=1`.

### Model selection

Auto-detect host RAM at startup via `psutil`. Two tiers:

| Tier | Condition | VLM (Pass 1) | LLM (Pass 2 + renames) | Total size |
|---|---|---|---|---|
| `default` | ≥ 16 GB RAM | `qwen2.5vl:7b` | `qwen2.5:7b-instruct` | ~10 GB |
| `low_spec` | < 16 GB RAM | `moondream:1.8b` | `llama3.2:3b-instruct` | ~4 GB |

Tier detection is surfaced to the user on the `ModelDownloadStep` first-run screen.
Users can override with `CREATORCUT_OLLAMA_VLM_MODEL` / `CREATORCUT_OLLAMA_LLM_MODEL`
env vars.

### Self-critique pass (Pass 2)

Because 7B-class models produce less reliable structured JSON than Opus/Sonnet, Pass 2
adds a second Ollama generate call that feeds the draft edit plan back with a critique
prompt (`PASS2_CRITIQUE_PROMPT`). The revised plan is used unless it fails validation,
in which case the draft is used as-is. The cloud fallback path skips self-critique
(Claude is reliable enough without it).

### Ollama lifecycle

The backend (`ollama_lifecycle.py`) probes `:11434` at startup and attempts to
auto-spawn `ollama serve` if not found. If the binary is absent entirely, the backend
still starts and serves a setup/install screen; the frontend gates workflow entry
until models are confirmed installed.

The Tauri `lib.rs` spawns the Python backend process on app launch via
`std::process::Command` and kills it via `RunEvent::ExitRequested`.

---

## Alternatives considered

### Keep Anthropic, add BYOK model

The simplest path. Rejected because it still requires an API key and network access,
which conflicts with the offline/local-first requirement.

### Use llama.cpp or whisper.cpp directly (no Ollama)

More control over quantisation and model loading. Rejected because Ollama provides
a stable, self-updating HTTP API with model management (pull, list, progress), which
saves a significant amount of glue code. faster-whisper (already local) handles
transcription, so whisper.cpp is not needed.

### Rewrite Python backend in Rust for distribution

Would eliminate the `uv` / PyInstaller dependency for the sidecar. Rejected because
it discards ~1200 LOC, 163 passing tests, and the `ffmpeg-python` / `faster-whisper`
integrations, which do not have Rust equivalents of the same maturity. The distribution
win is also partial — FFmpeg and Ollama remain external binaries regardless.

---

## Consequences

### Positive

- No network egress by default. No API key required for core features.
- Lower marginal cost per edit (local inference is free).
- Offline operation fully supported.
- Prompt cache (Anthropic `cache_control`) is no longer needed — local inference is free,
  so the cost lever it provided is irrelevant.

### Negative

- Quality gap vs. Sonnet/Opus. 7B-class VLMs produce noisier clip analysis; the
  self-critique pass and schema-first prompts mitigate but do not eliminate this.
- First-run disk footprint: ~4 GB (low_spec) or ~10 GB (default). Surfaced explicitly
  in `ModelDownloadStep` before any pull begins.
- Llama 3.2 has a Meta Community License with an MAU threshold. **Verify before any
  commercial release.** The `low_spec` LLM may need to change if the license is
  incompatible with the subscription model.

---

## Revisit if

- A 7B VLM/LLM produces structurally invalid edit plans too often in production
  (>10% of runs after self-critique). Consider moving to the 14B tier or adding a
  second-chance retry with a stricter prompt.
- Ollama's HTTP API changes in a way that breaks `ollama_client.py` — it is an
  unofficial API with no stability guarantee.
- Qwen2.5 or Llama 3.2 licenses change in a way that is incompatible with commercial
  distribution — re-evaluate model selection at that point.
- A WebGPU or WASM inference runtime matures enough to run 7B models in-process
  inside the Tauri webview, which would eliminate the Ollama binary dependency entirely.
