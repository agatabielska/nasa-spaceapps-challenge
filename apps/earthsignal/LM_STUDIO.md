# LM Studio setup for Orbit

Model requests originate from the app's local API. No external inference service, tunnel, public endpoint or API subscription is required.

## Model for this laptop

This machine has an Apple M4 Pro and 48 GB unified memory. **`google/gemma-4-26b-a4b-qat`** was already loaded and is the initial configuration tested against the real catalog/tool workflow. No model weights were downloaded or trained during this integration.

A `gpt-oss-20b-MLX-8bit` variant is also downloaded and is a reasonable alternative to test. The live checks here use Gemma. The API may expose similar names for different variants: copy the exact identifier from `/v1/models`. Avoid loading a large F16 variant by mistake.

Orbit does not need fine-tuning on the catalog or HDF5 files in its context. The model queries current records through tools.

## LM Studio interface settings

1. Load **Gemma 4 26B A4B QAT** from downloaded models.
2. Start with context length **8192**. Keep the default Apple Silicon GPU placement.
3. Preserve the default model-specific chat template, including tool formatting.
4. Open **Developer → Local Server**.
5. Select port **1234**, binding **127.0.0.1**. Keep **Serve on Local Network** off.
6. Keep **CORS off**: the app backend connects to the model, not the browser.
7. Start the server: `http://127.0.0.1:1234/v1`.

The app supplies temperature **0.1**, an output token budget, conversation context and tools. Do not paste the database into LM Studio's chat or configure an MCP server. Initial loading/prefill may be slower than later questions. Test when changing models or context settings; no local model guarantees flawless interpretation.

## Authentication and model ID

A personal loopback-only setup can use LM Studio's default local API. If **Require Authentication** is enabled, create a token and put it in `LMSTUDIO_API_KEY` inside `.env.local`. It is not a paid OpenAI cloud API key. The token stays on the backend and is ignored by Git.

```sh
curl http://127.0.0.1:1234/v1/models
```

For the tested setup:

```dotenv
LMSTUDIO_MODEL=google/gemma-4-26b-a4b-qat
```

The models list can include downloaded models available for just-in-time loading. Presence is not a guarantee that inference is loaded or that tool tests passed. `lms ps` lists loaded models. With authentication enabled, use the local bearer token when checking the endpoint; keep it outside source/committed commands.

## CLI alternative

```sh
lms ps
lms server start --bind 127.0.0.1 --port 1234
```

Standard macOS CLI location: `~/.lmstudio/bin/lms`. For model load keys/settings use `lms ls` and `lms load --help`. Keep LAN sharing disabled; the application accepts only loopback model endpoints.

## Troubleshooting

- **LM Studio nie odpowiada:** start the server and check port 1234.
- **Model not configured:** copy the exact ID into `.env.local` and restart the app. Auto-selection works only when exactly one model is advertised.
- **HTTP 401:** set the local API token.
- **HTTP error/no tools:** check model support, chat template and LM Studio logs.
- **Session expired:** resend the question. Restarting the backend clears conversations but preserves event data.
- **No matching events:** the search covers this project's database, not the internet.
- **Map changed while waiting:** text remains, but stale navigation is skipped deliberately.

References: https://lmstudio.ai/docs/developer/openai-compat/tools , https://lmstudio.ai/docs/developer/core/authentication , https://lmstudio.ai/docs/developer/core/server/serve-on-network .
