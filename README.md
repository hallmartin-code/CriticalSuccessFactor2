# Deck → Investor One-Pager

Upload an investor pitch deck (`.pdf`, `.pptx`, `.docx`); the Claude API extracts and
analyses it, and the app returns a single-page investor summary PDF in the TEN Capital
Network format — including the deck's **critical variable to success** and the **#1
priority activity** for moving it.

Runs two ways from the same pipeline: a CLI, and a FastAPI web app deployable to Railway.

---

## The document template

`template.py` is the single source of truth for what a generated document contains and
how it looks. It holds no company data — only structure and format:

| Block | What it declares |
|---|---|
| `PALETTE` | Colour tokens (page, card, hairline, coral/amber/teal accents, text tiers) |
| `FONT_ROLES` | `display` / `body` / `body_bold` / `mono` / `mono_bold` and their fallbacks |
| `TYPE_SCALE` | Size, leading, and letter tracking per text role |
| `LAYOUT` | Page margins, card radius/padding, column split, callout geometry |
| `SECTIONS` | The prose blocks and which column each sits in |
| `CALLOUTS` | The two accent panels (headline field, body field, label, accent colour) |
| `FIELD_GUIDANCE` | **The fields analyzed in every deck**, and the instruction for each |
| `ANALYSIS_RULES` | The standing rules applied to every analysis |
| `DISCLOSURE` | The fine print printed at the foot of the card |

Both halves of the app read from it: `analyzer.py` builds the JSON schema and prompt from
`FIELD_GUIDANCE` + `ANALYSIS_RULES`, and `renderer.py` draws from `SECTIONS` + `CALLOUTS`.

**Adding a field is one edit.** Append to `FIELD_GUIDANCE`, then reference the key from a
`Section` or `Callout`. It flows into the model's schema, the prompt, and the page with no
other changes. `template.field_keys()` raises at import time if a referenced field has no
guidance entry, so the two can't drift apart.

### Document structure produced

```
  ◐ TEN CAPITAL / NETWORK                     brand lockup
┌──────────────────────────────────────────┐
│ ══════════ coral → amber → teal ═════════ │  accent rule
│ ● INVESTOR ONE-PAGER                      │  eyebrow
│ Company Name                              │  title      ← company_name
│ One-line description of the company.      │  subtitle   ← tagline
│ ───────────────────────────────────────── │
│ PROBLEM              │ TEAM               │
│ SOLUTION             │ THE ASK            │  sections
│ TRACTION & KEY …     │ ┌────────────────┐ │
│ MARKET OPPORTUNITY   │ │ ⚡ CRITICAL VAR │ │  amber callout
│ BUSINESS MODEL       │ └────────────────┘ │
│                      │ ┌────────────────┐ │
│                      │ │ 🎯 TOP PRIORITY│ │  teal callout
│                      │ └────────────────┘ │
│ ───────────────────────────────────────── │
│ disclosure                                │
└──────────────────────────────────────────┘
   Deck Analysis  1  Compiled on … by TEN Capital Network  ◐
```

The card is measured before it is drawn: it wraps its content rather than stretching, and
the whole stack is centred vertically. If an analysis runs long, each column shrinks to fit
— the output is always exactly one page.

---

## Files

| File | Role |
|---|---|
| `template.py` | Document structure, format tokens, and analyzed fields |
| `extractor.py` | PDF / PPTX / DOCX text extraction, one entry per page or slide |
| `analyzer.py` | Claude API call, schema-enforced JSON, one retry on bad JSON |
| `renderer.py` | ReportLab rendering; `render_onepager_bytes()` for the web path |
| `notifier.py` | Emails each finished analysis (summary + PDF) via the Resend API |
| `pitch_to_onepager.py` | CLI entry point |
| `webapp.py` | FastAPI app: upload page, `/api/generate`, `/healthz`, brand icons |
| `web/index.html` | Upload page (matches the PDF's design system) |
| `web/favicon.svg` | Brand mark — the primary favicon, and the source of the raster icons |
| `make_favicon.py` | Regenerates `web/favicon.ico` and `web/apple-touch-icon.png` |
| `make_sample_deck.py` | Generates `sample_deck.pdf` for smoke testing |
| `fonts/` | Optional drop-in brand fonts — see `fonts/README.md` |

---

## Local use

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your key into .env
```

**CLI:**

```bash
python make_sample_deck.py            # optional: creates sample_deck.pdf
python pitch_to_onepager.py sample_deck.pdf
```

**Web app:**

```bash
uvicorn webapp:app --reload --port 8000
# open http://127.0.0.1:8000
```

---

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | — | Key from [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `ANTHROPIC_MODEL` | no | `claude-opus-5` | Any current model ID, e.g. `claude-sonnet-5` for lower cost |
| `MAX_UPLOAD_MB` | no | `25` | Upload size cap |
| `APP_USERNAME` / `APP_PASSWORD` | no | unset | Set **both** to put the site behind HTTP basic auth |
| `LOG_LEVEL` | no | `INFO` | Standard logging level |
| `RESEND_API_KEY` | no | unset | [Resend](https://resend.com/api-keys) key. **Unset = results emails off.** |
| `NOTIFY_EMAIL_TO` | no | `Info@tencapital.group` | Recipient(s); comma-separate for several |
| `NOTIFY_EMAIL_FROM` | no | `TEN Capital Network Analyzer <onepager@tencapital.group>` | Must be on a domain verified at [resend.com/domains](https://resend.com/domains) |
| `NOTIFY_EMAIL_REPLY_TO` | no | unset | Optional reply-to address |

---

## Deploying to Railway

1. **Push this folder to a GitHub repo.** `.gitignore` already excludes `.env`, so your key
   will not be committed.
2. In Railway: **New Project → Deploy from GitHub repo**, and pick the repo. Nixpacks
   detects Python, installs `requirements.txt`, and uses the start command in
   `railway.json`. No Dockerfile needed.
3. **Variables** tab → add `ANTHROPIC_API_KEY` and `RESEND_API_KEY`. Add `APP_USERNAME` and
   `APP_PASSWORD` too unless you intend the URL to be public (see the warning below). `PORT`
   is injected by Railway; don't set it.
4. **Settings → Networking → Generate Domain** to get a public URL.
5. Railway health-checks `/healthz`, which also reports **which commit is live** —
   hit it first if a change seems to be missing (see below).

### Deploying without the GitHub connection

Railway's repo connection is a single point of failure: if it is missing or broken, Railway
keeps serving the last successful build and pushes silently have no effect. `.github/workflows/deploy.yml`
removes that dependency by deploying *from* GitHub Actions with a Railway token, so the push
itself drives the deploy.

One-time setup:

1. Railway → **Project Settings → Tokens** → create a project token scoped to the
   `production` environment.
2. GitHub → repo **Settings → Secrets and variables → Actions**:
   - **Secret** `RAILWAY_TOKEN` — the token from step 1.
   - **Variable** `RAILWAY_SERVICE` — the service name as it appears in Railway.
   - **Variable** `APP_URL` — e.g. `https://criticalsuccessfactor2-production.up.railway.app`
     (optional; enables the post-deploy check).

Every push to `main` then deploys, and the workflow polls `/healthz` until the live `commit`
matches the pushed SHA — so a deploy that silently leaves an old build running **fails the
workflow** instead of going unnoticed. Run it by hand from the Actions tab with
**Run workflow**.

Manual fallback, from a checkout of `main`:

```bash
npm i -g @railway/cli
railway login
railway link          # pick the project and service
railway up
```

### Which build is live?

```bash
curl -s https://<your-app>/healthz
```

```json
{"status":"ok","commit":"a996f11...","commit_short":"a996f11","environment":"production", ...}
```

`commit` comes from Railway's injected `RAILWAY_GIT_COMMIT_SHA`, or from `APP_COMMIT_SHA` if
you set it explicitly (CLI uploads do not get the injected value). Compare it against
`git rev-parse HEAD` — if they differ, the deploy did not take, and nothing you pushed is live.

Config already in the repo: `railway.json` (start command + health check), `Procfile`
(same command, for any Procfile-based host), `.python-version` pinning 3.12.

> ⚠️ **An open URL spends your Anthropic credits.** Anyone who finds the domain can run
> analyses on your key. Set `APP_USERNAME` + `APP_PASSWORD` — the browser handles the
> login prompt, and `/healthz` stays open so Railway's health check still passes.

**Notes on the deployed environment**

- Uploads live in memory and a temp file for the duration of the request, and are deleted
  in a `finally` block. Nothing is persisted — Railway's filesystem is ephemeral anyway.
- A run takes roughly 15–60s depending on deck length. That is well inside Railway's
  request timeout, but it does mean one worker is busy for that time; raise replicas if
  you expect concurrent users.
- Brand fonts and the emoji font are not installed on the Railway image. Without them the
  PDF falls back to Helvetica/Courier and drops the ⚡/🎯 markers. To get exact brand type,
  commit the TTFs into `fonts/` — see `fonts/README.md`.

---

## Brand icons

`web/` is the served public directory. The favicon is the TEN Capital mark — the same three
arcs and dots the upload page draws inline, in the same coral/amber/teal palette.

| File | Used for |
|---|---|
| `web/favicon.svg` | Primary favicon; scales to any tab or bookmark size |
| `web/favicon.ico` | 16/32/48/64 px fallback, and the bare `/favicon.ico` browsers request |
| `web/apple-touch-icon.png` | 180 px iOS home-screen icon, on white (iOS flattens transparency) |

All three are served from the site root, and the whole directory is also mounted at
`/static`. They are exempt from HTTP basic auth so the tab icon still appears on the login
prompt. The `.ico` and `.png` are checked in; regenerate them only if the mark changes:

```bash
python make_favicon.py
```

---

## Results emails

Every completed generation is emailed to `NOTIFY_EMAIL_TO` (default `Info@tencapital.group`)
with the full analysis in the body and the rendered one-pager attached. It fires from both
the CLI and the web app.

- **Off by default.** No `RESEND_API_KEY` means no email, and nothing else changes.
- **Never blocks a generation.** In the web app the send runs as a FastAPI background task
  *after* the PDF response is returned; any Resend failure is logged as a warning and the
  download is unaffected. Rejected uploads (wrong type, too large, unreadable) send nothing.
- **Sender domain must be verified.** `NOTIFY_EMAIL_FROM` has to sit on a domain verified at
  [resend.com/domains](https://resend.com/domains), or Resend returns 403.
- **Body follows `template.py`.** Adding a section or callout there adds it to the email too —
  no second field list to maintain.
- `GET /healthz` reports `results_email_configured` so you can confirm the key reached the
  deployment.

Attachments over 25 MB are dropped and the summary is sent on its own, keeping the request
under Resend's 40 MB limit.

---

## Model choice

Defaults to `claude-opus-5`. The response is constrained by a JSON schema
(`output_config.format`), so malformed JSON is close to impossible; the single retry on a
parse failure is a backstop. Refusals, rate limits, auth failures, and token-limit
truncation each surface as a distinct message rather than a generic parse error.

Set `ANTHROPIC_MODEL=claude-sonnet-5` to cut cost per run at some loss of analytical depth
on the critical-variable judgement, which is the part of the output that benefits most from
the stronger model.
