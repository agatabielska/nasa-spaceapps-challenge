# EarthSignal — local catalog and Orbit

React/TypeScript/MapLibre frontend, local Node.js API, SQLite and a local LM Studio model. No hosted database, paid inference provider or cloud API key is required. Map geometry, fonts and worker are served from this project.

## Start

Requirements: Node.js **22.18+** (tested with 26.13.1) and LM Studio with a downloaded tool-capable model.

```sh
cd apps/earthsignal
npm ci
cp .env.example .env.local   # first setup only; preserve an existing config
```

Set the exact LM Studio model identifier in `.env.local`. Tested local configuration:

```dotenv
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
LMSTUDIO_MODEL=google/gemma-4-26b-a4b-qat
LMSTUDIO_API_KEY=
API_PORT=8787
EARTHSIGNAL_DB_PATH=.local/earthsignal.sqlite
```

Start LM Studio's API on `127.0.0.1:1234`, then:

```sh
npm run dev
```

Open **http://127.0.0.1:5173/**. This starts API and Vite, watches code changes and stops both with Ctrl+C. Restart after editing `.env.local`. LM Studio CORS and LAN sharing are unnecessary: the browser uses the app's local API, which connects to LM Studio.

Local production mode:

```sh
npm run build
npm start
```

Open **http://127.0.0.1:8787/**. The API serves the built frontend. A standalone static `dist/` upload is no longer a complete app. Internet is needed only for initial dependency/model downloads and optional reference links; normal catalog search and inference stay local.

Model setup: [LM_STUDIO.md](LM_STUDIO.md).

## Persistent events

First startup creates `.local/earthsignal.sqlite` from `data/events.seed.json`. Subsequent starts preserve database edits and do not overwrite records from the seed. Schema version: `PRAGMA user_version`; full-text index: FTS5. The frontend no longer embeds event records.

Add/update records with a JSON array matching the seed schema:

```sh
npm run db:import -- /absolute/path/to/events.json
```

The entire import is validated, rejects duplicate IDs and runs as a transactional upsert. Missing records are not deleted. Explicitly restore/update seed records with `npm run db:import`. Refresh the sidebar catalog after importing. Import is preferable to direct SQL edits because payloads and indexed fields stay consistent.

SQLite files, journals and `.env.local` are ignored by Git. The seed and schema are versioned. Back up a live WAL database with SQLite's backup facility, not just a copy of its main file during writes.

## Orbit

The local model receives the message, recent conversation and map context. It requests typed tools; the backend validates arguments and queries SQLite. UI actions use existing event IDs. No arbitrary SQL or code execution is exposed.

Tools: `search_events`, `get_event`, `focus_event`, `start_guide`, `reset_map`. Search supports category, country/ISO2, continent, dates, text, provenance, available analysis and viewport bounds. A single result opens its card; multiple results remain on the map.

Examples are suggestions, not a fixed list of supported prompts:

- „Wskaż pożary w Hiszpanii”.
- „A teraz pokaż takie zdarzenia w Kanadzie”.
- „Znajdź powodzie w Afryce”.
- „Pokaż tylko wydarzenia z gotową analizą NISAR”.
- „Otwórz drugie wydarzenie z ostatniej listy”.

Conversation state is in API memory, expires after an hour of inactivity, and resets on server restart. Expiration is explicit. Delayed navigation is skipped if the user changes the map/filters while waiting; the browser sends the ordered list it actually shows, so follow-ups such as "the second one" never refer to results that were not displayed. A pending answer shows its elapsed time and can be cancelled, which also stops the model call on the API (including through the Vite dev proxy). Orbit answers in the language of the latest message and keeps catalog titles unchanged. When LM Studio is unavailable, the catalog still works and chat shows an error; no keyword or cloud fallback is used.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | API and SQLite status |
| GET | `/api/events` | Catalog |
| POST | `/api/events/search` | Validated database search |
| GET | `/api/events/:id` | Event record |
| GET | `/api/orbit/status` | Local endpoint/model availability |
| POST | `/api/orbit/chat` | Model/tool cycle, sources and navigation |

## Checks

```sh
npm test
npm run build
# With API and LM Studio running:
npm run test:live
```

Unit tests cover persistence, atomic imports, filters, validation, fabricated IDs, partial model failures and sessions. The live test calls the configured real model and checks Polish search, conversational refinement, IDs/navigation and no-result behavior. Re-run it after changing models or their chat templates.

## Data and licenses

Four documented candidate studies and nine fictional scenarios are seeded. Scenarios do not establish that a disaster occurred. No case study has been processed; no measured NISAR impact, computed rasters or live alerts are shown. The bottom chart represents catalog entries.

Natural Earth borders: public domain, 1:110m, source https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson . Borders are illustrative. Event references are stored in the database. Astronaut: original SVG. Bundled DM Sans/Manrope fonts include SIL Open Font License texts in `public/fonts/`. MapLibre: BSD-3-Clause; dependencies retain their licenses.
