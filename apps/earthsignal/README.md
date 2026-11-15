# EarthSignal — NISAR stories, local catalog and Orbit

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

Open **http://127.0.0.1:5173/** for the landing page or **http://127.0.0.1:5173/explore** for the event explorer. This starts API and Vite, watches code changes and stops both with Ctrl+C. Restart after editing `.env.local`. LM Studio CORS and LAN sharing are unnecessary: the browser uses the app's local API, which connects to LM Studio.

Local production mode:

```sh
npm run build
npm start
```

Open **http://127.0.0.1:8787/**. The API serves the built frontend. A standalone static `dist/` upload is no longer a complete app. Internet is needed only for initial dependency/model downloads and optional reference links; normal catalog search and inference stay local.

Model setup: [LM_STUDIO.md](LM_STUDIO.md).

## Landing and explorer

`/` is a camera journey, “Dancing with the SARs”. Each section is a scene floating in 3D space: scrolling flies one camera along a curved path, so headings and visualizations appear in the distance, grow as the camera approaches and fall behind it. The page still scrolls natively (scrollbar, keys, touch, links); a spacer gives the scroll length and the camera follows it with inertia, star streaks and parallax. Stars also shift with the pointer and move aside from the cursor. The About globe waits right behind the hero title, so the start screen shows the title centred over a turning, slightly dimmed Earth and its orbits, with the lead and button below the globe (Landing.tsx measures where the globe lands and enlarges it a little while it waits on wide screens); the camera pushes straight through the title, the globe grows to full size, and the heading, events, astronaut and panel fill in on arrival. The look follows the `Dancing_with_the_SARs.html` prototype: a floating header (logo, data status, dashboard button), a numbered chapter rail on the left, a thin frame with corner brackets, scanlines and a vignette, each scene centred between the header and the bottom HUD, and each visualization in an instrument frame (status line, caption, data tag). The bottom HUD shows the chapter counter, the camera-position track (drag it to seek) and the percentage, with square controls in the bottom-right corner: autopilot, background motion, previous and next stop. The play button starts the **autopilot**, a guided flight that rests on each content block, plays the drone flight and stops at the end. While it rests on a before/after comparison, the divider sweeps once to each side and back to the middle (about 7.5 s), so the audience sees both passes. A stop is a whole content block: a scene stops at its top and at each block marked `data-stop` (Etna's cloud comparison), and adds a stop only when a block is too tall for the screen; cases are sized to fit between the bars on 900 px and taller screens. Keys: ↓, →, Space or Page Down for the next stop (a presentation clicker works), ↑, ←, Shift+Space or Page Up for the previous one, Home/End for the ends, P for the autopilot. Scrolling, touching or clicking takes control back from the autopilot. The engine lives in `src/journey/` (`path.ts` is the camera maths, tested in `src/journey.test.ts`; `engine.ts` places the scenes):

1. **Home** — the challenge title and the way in.
2. **About** — a WebGL Earth with the five event types we detect orbiting it (forest wildfires, earthquakes, farming activities, glacier movement, volcanoes). Orbit the astronaut (`src/Astronaut.tsx`) drifts from one to the next; three of them link to a case study.
3. **Case studies** — Spain (Ávila wildfire), Etna (eruption, plus optical-versus-radar under cloud) and Nepal (Rasuwa glacier-collapse flood). Each has a before/after divider, switchable detection layers and the numbers from `case.json`. After the Nepal case, just before the final call to action, a 3D “drone flight” follows the detected flood trace from its origin to Syabrubesi; the journey camera rests on that scene for a few screens of scrolling, which plays the flight.
4. **Discover more yourself** — the way into the dashboard.

`/explore` opens the map, SQLite catalog and local LM Studio assistant. Its path is defined once in `src/routes.ts`. The two pages load separately, so MapLibre is not downloaded for the landing page. Sections have anchors (`/#about`, `/#work`, `/#spain`, `/#etna`, `/#nepal`, `/#flight`, `/#discover`).

**Media.** Everything is bundled; the page makes no third-party requests at runtime. Case-study images in `public/media/cases/<id>/` are WebP copies (longest side 1600 px) of `data/event_visualisation/` (that folder is not tracked in git); `src/cases.ts` lists each asset with its source file. If an asset is missing, the page shows a labelled placeholder naming the expected file and its source, so it can be dropped in later.

**Drone flight.** `public/media/cases/nepal/flight/` holds 132 frames (1280 × 720) rendered once from `data/event_visualisation/Nepal/map3d.html`, so the flight works offline. To re-record: serve a copy of `map3d.html` locally with `preserveDrawingBuffer: true`, move the camera along the centreline of `nepal_flood/mask_high_confidence.png` with `map.jumpTo`, wait for `idle`, save the canvas for each step, and convert with `cwebp -q 62`. The frames show Esri World Imagery and AWS Terrain Tiles; both are credited on the page.

**Readability and motion.** Text keeps at least 7:1 contrast (WCAG AAA) on the space background and on panels; the smallest label is 14 px and reading text starts at 17 px, scaling up on large screens. Dividers work with pointer, touch and a labelled range input; layers are toggle buttons with a text state. The bottom HUD has a background-motion control; with “reduce motion” set in the system there is no camera flight: the page becomes an ordinary scrolling page, the starfield is static and the drone flight becomes four still frames.

The coloured areas are detections by our model, not validated damage maps, and the colour images are radar composites rather than natural-colour photographs; the page says so. Earlier research notes on NASA material are in [LANDING_RESEARCH.md](LANDING_RESEARCH.md).

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

Four documented candidate studies and nine fictional scenarios are seeded. Scenarios do not establish that a disaster occurred. No EarthSignal case study has been processed; the explorer does not show measured NISAR impacts, computed change rasters or live alerts. The landing separately displays a credited, pre-existing NASA visualization. The bottom chart shows catalog entries per month for the selected date range, not satellite measurements. The statistics panel can be collapsed to a summary bar; that choice and the open filter groups are remembered per browser.

Explorer presentation: text and controls retain a projector-oriented scale (12px minimum labels, 15px reading text). Panels enlarge automatically on screens from 1680×940 (120%) and 2300×1250 (140%); the **Aa** button in the top bar forces Large (120%) or XL (140%) on any projector. Only the panels are scaled, so map pointer coordinates stay exact.

Natural Earth borders: public domain, 1:110m, source https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson . Borders are illustrative. Event references are stored in the database. Astronaut: original SVG. Bundled DM Sans/Manrope fonts include SIL Open Font License texts in `public/fonts/`. MapLibre: BSD-3-Clause; dependencies retain their licenses.
