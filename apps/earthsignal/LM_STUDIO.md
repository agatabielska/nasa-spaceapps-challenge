# LM Studio setup for Orbit — Qwen3.6

Orbit uses **mlx-community/Qwen3.6-35B-A3B-4bit** through a local LM Studio profile named **earthsignal/orbit-qwen3.6**. The profile reuses the downloaded weights; it does not train, modify or duplicate them. No paid API or hosting is needed. Tested hardware: Apple M4 Pro, 48 GB unified memory; LM Studio 0.4.26+4.

## One-time setup

Download the model in LM Studio, then from `apps/earthsignal` run:

```sh
npm run lmstudio:setup
```

The script creates `~/.lmstudio/hub/models/earthsignal/orbit-qwen3.6/model.yaml`. It refuses to overwrite an independently edited profile. This is a model-specific preset, not a global LM Studio configuration change.

Load **earthsignal/orbit-qwen3.6** in LM Studio, with:

- Context length: **8192** initially; increase to 16384 for unusually long conversations/input if needed.
- Parallel predictions: **1** for interactive single-user use.
- Thinking: **off** (the profile default).
- Preserve the model-specific Jinja template and tool formatting.
- Leave the usual Apple Silicon GPU placement enabled.
- Unload other large models if they are not in use. Their downloaded files remain available.

CLI equivalent (standard macOS path: `~/.lmstudio/bin/lms`):

```sh
lms load earthsignal/orbit-qwen3.6 --context-length 8192 --parallel 1 --yes
lms server start --bind 127.0.0.1 --port 1234
```

The server must bind to **127.0.0.1:1234**. LAN sharing and CORS are unnecessary: the browser connects to EarthSignal's backend, and that backend connects to LM Studio.

`.env.local` (ignored by Git):

```dotenv
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
LMSTUDIO_MODEL=earthsignal/orbit-qwen3.6
LMSTUDIO_API_KEY=
API_PORT=8787
EARTHSIGNAL_DB_PATH=.local/earthsignal.sqlite
```

Restart `npm run dev` after changing `.env.local`. If LM Studio requires authentication, put its local token in `LMSTUDIO_API_KEY`; do not commit it or put it in browser code.

## Why a profile is necessary

The directly downloaded model appears as `qwen3.6-35b-a3b` in this installation. It did not advertise a reasoning switch. A real API test with `chat_template_kwargs.enable_thinking=false` and another with `reasoning_effort=none` still spent the output budget on reasoning, leaving the user's answer empty.

The profile exposes `enableThinking` as a model-specific field whose effect sets the Jinja variable `enable_thinking`. Its default is false, and the backend also requests `reasoning_effort=none`. A direct API check confirmed zero reasoning tokens. Backend validation rejects unexpected reasoning or raw tool markup rather than displaying it to the user. If you select the original raw model instead, these profile settings do not automatically apply.

The backend supplies temperature **0.2**, top_p **0.8**, top_k **20**, a **900-token** output limit and a **60-second** per-call timeout. These are tested application settings, not a reproduction of the producer's general benchmarks. A complete answer can require multiple model calls; the loop is bounded to four. Initial loading/prefill can take longer than a warm request.

## Multilingual conversations and long questions

Orbit is instructed to answer in the latest message's language, or a language explicitly requested. Event titles stay as stored; explanations and no-result messages use the user's language. Country/category expressions are translated into structured tool filters. The live suite covers Polish, English, German, French and Spanish, including switching languages within a conversation. This is verification of those scenarios, not a guarantee for all possible languages/questions.

The chat supports **8000 characters**, multiline input and pasting long questions. Enter sends; Shift+Enter inserts a line break. Recent history is bounded by turns and size. Once tools have selected the facts, previous assistant prose is removed from the current generation context to avoid anchoring the answer to an earlier language. Follow-up planning retains recent conversation, map selection and the ordered result list.

Tools: `search_events`, `get_event`, `focus_event`, `start_guide`, `reset_map`, `catalog_help`. The last tool provides help/scope and clarification context without claiming that a database search occurred. A successful tool cycle is required before committing an answer. Some local runtimes do not enforce `tool_choice=required`, so the backend also detects an ungrounded answer and requests a tool call again. Malformed arguments, invented IDs and unknown tools cannot cause navigation.

No matches are returned as an explicit zero-result tool response. Orbit explains that nothing matching the constraints was found **in the local catalog**, not that no such real-world event occurred. It must not silently broaden the search or invent a substitute. Missing analysis/measurements must be disclosed; this system does not infer damage or ice volume from text.

## Verification

```sh
npm test
npm run build
# With EarthSignal API and the profile loaded in LM Studio:
npm run test:live
```

The live suite checks exact result IDs, conversation refinement, language cues, ordered navigation, empty results, unavailable analysis, a long question and greetings against the actual local model. It prints answer text for manual language review and saves timing/transcript in ignored `.local/orbit-live-report.json`. Test fixtures currently expect the existing 13-entry catalog; update expectations deliberately after catalog changes. Unit tests verify orchestration and validation without invoking a model.

## Troubleshooting

- **Model not available:** load the profile, check `lms ps`, verify the exact ID in `/v1/models`. Advertised models may include downloaded-but-unloaded JIT models.
- **Fast profile not active / MODEL_THINKING:** reload the profile with Thinking off. Selecting the raw download bypasses its defaults.
- **Model output empty/truncated:** check the loaded profile, output budget and actual model context length.
- **No completed analyses found:** inspect SQLite. Landing case studies in `cases.ts` are not automatically imported into the event database.
- **Session expired:** resend the question; API restart clears conversations but preserves SQLite.
- **Long wait:** check for another large model or active prediction; use one parallel slot and avoid memory pressure. Cancel remains available in chat.
- **Map changed while answering:** the answer remains visible but stale navigation is skipped; ask again to apply it.

References: [LM Studio model.yaml](https://lmstudio.ai/docs/app/modelyaml), [LM Studio tool use](https://lmstudio.ai/docs/developer/openai-compat/tools), [Qwen3.6 model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B), [downloaded variant](https://huggingface.co/mlx-community/Qwen3.6-35B-A3B-4bit).
