# Render Free: map and analyses

This setup publishes the built website and its Node.js/SQLite API as one Web Service. Orbit is explicitly disabled; no LM Studio server or paid model key is needed. The interactive maps may still load third-party imagery and terrain.

## Before creating the service

Commit and push the deployment changes to the branch that Render will deploy. Render builds the GitHub version, not uncommitted local files. Do not upload `.env.local`, SQLite files or API keys.

Deploy directly from the existing project repository. Set Root Directory to `apps/earthsignal`: files outside it are not available to the service at build time or runtime. GitHub authorization still applies to the selected repository. No separate repository or manual export is needed. With auto-deploy enabled, changes under `apps/earthsignal` on the linked branch trigger a new deploy; changes only in research folders do not.

## Render settings

Create an account at https://dashboard.render.com/ and choose **New → Web Service**. Connect GitHub with access only to the intended repository, then select `agatabielska/nasa-spaceapps-challenge`.

| Field | Value |
| --- | --- |
| Name | An available name, e.g. `earthsignal-blue-trust` |
| Branch | `main` (commit and push these deployment changes first) |
| Language / Runtime | Node |
| Root Directory | `apps/earthsignal` |
| Build Command | `npm ci --include=dev && npm run build` |
| Start Command | `npm start` |
| Instance Type | **Free** |
| Health Check Path | `/api/health` |

Environment variables:

| Key | Value |
| --- | --- |
| `NODE_VERSION` | `24.22.1` |
| `NODE_ENV` | `production` |
| `ORBIT_ENABLED` | `true` (`false` for a map-only deployment) |
| `ORBIT_PROVIDER` | `gemini` |
| `GEMINI_API_KEY` | the Google AI Studio key (secret; never in the repo or a `VITE_` variable) |
| `GEMINI_MODEL` | `gemini-3.8-flash` |
| `EARTHSIGNAL_DB_PATH` | `.local/earthsignal.sqlite` |

Do not add a paid disk or database. The catalog is seeded from the versioned JSON on startup. Render supplies `PORT`, `RENDER=true` and `RENDER_EXTERNAL_URL` automatically. The server binds to `0.0.0.0` on Render and accepts its specific external hostname/origin. For a custom domain, set `PUBLIC_URL` to its HTTPS origin.

Choose **Create Web Service** and follow the build/deploy logs. Once the service is Live, open its assigned HTTPS URL.

## Verify

- `/api/health`: JSON with `ok: true`, database `sqlite` and an event count.
- `/`: landing page, globe, comparison and flight.
- `/explore`: event list, filters and a full analysis.
- `/show`: presentation.
- `/api/orbit/status`: `available: false` immediately; this is expected for this deployment.
- Open the URL in a private browser window to verify access without your account.

Refresh `/explore` directly as well: the Node server must serve the SPA route. The SQLite file and source files must not be put inside `public/`.

## Free-tier limitations

Render currently sleeps Free web services after 15 idle minutes, with startup taking about a minute. Filesystem changes disappear on sleep, restart or redeploy. The seed catalog returns automatically; manual database edits and in-memory chat sessions do not survive. To publish event changes, update the versioned seed rather than relying on a live database edit. Free Render Postgres expires after 30 days and is unnecessary for this setup.

## Troubleshooting

- **No open ports:** verify Start Command and that the deployed commit reads Render's `PORT` and binds to `0.0.0.0`.
- **403 HOST / ORIGIN:** verify that the deployed code supports `RENDER_EXTERNAL_URL`; for a custom domain set `PUBLIC_URL`.
- **`tsc` or Vite missing:** use `npm ci --include=dev && npm run build`.
- **Node / SQLite / TypeScript errors:** check `NODE_VERSION` and the first relevant error in Logs.
- **Old UI:** check the deployed commit and branch, then deploy the latest commit.
- **Orbit offline:** expected; changing a key alone will not enable cloud inference in the current local-only model adapter.

References: [Web Services](https://render.com/docs/web-services), [Node version](https://render.com/docs/node-version), [default environment variables](https://render.com/docs/environment-variables), [Free limitations](https://render.com/docs/free).
