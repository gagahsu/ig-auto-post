# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Automated pipeline: Taiwan pre-market briefing email → parsed into JSON → rendered as a 1080x1350 IG card image (HTML/CSS via Playwright screenshot) → committed to repo → served via jsDelivr CDN → posted to Instagram via Meta Graph API. A Claude Project scheduled task reads Gmail, parses the briefing, and emails the JSON to the user's own inbox — it does not call any external API. A GitHub Actions `schedule` cron then pulls that email itself via the Gmail API and drives the rest of the pipeline. This "GitHub pulls" design (rather than "Claude pushes") exists because the Claude scheduled task's outbound network access is unreliable.

## Commands

```bash
pip install -r requirements.txt
playwright install --with-deps chromium

# Render a card locally from payload JSON
python3 scripts/render_card.py --payload payload.example.json --out output/card.png

# Publish to Instagram (requires IG_ACCESS_TOKEN, IG_BUSINESS_ACCOUNT_ID env vars,
# and image must already be at a public URL)
python3 scripts/publish_ig.py --image-url <public-url> --caption "text"
```

No test suite, linter, or build step exists in this repo.

To test the full pipeline without waiting for the schedule: GitHub Actions →
"Post daily briefing to Instagram" → Run workflow → paste `payload.example.json`
contents into `payload_json` input.

## Architecture

Three separate execution contexts, each owning one stage — do not blur these boundaries:

1. **Claude Project scheduled task** (`project-scheduled-task-prompt.md`, not code that runs in this repo) — reads Gmail for today's briefing email, parses it into the exact JSON schema documented there, and emails that JSON back to the user's own inbox with subject `IG_BRIEFING_PAYLOAD {YYYY-MM-DD}`, plain text body, nothing but the raw JSON. It must NOT call the GitHub API or Instagram/Meta APIs itself — no outbound API calls at all, only Gmail read + Gmail send. If it can't find today's source email, it stops rather than reusing stale data.

2. **GitHub Actions workflow** (`.github/workflows/post-to-ig.yml`) — the only thing that touches Meta/Instagram, and now also the thing that pulls from Gmail. Triggered by `schedule` (real, daily cron at 17:10 UTC / 01:10 Taipei), `repository_dispatch` (kept as an emergency/manual fallback), or `workflow_dispatch` (manual test — payload pasted as a JSON string, or left blank to exercise the Gmail-fetch path). Pipeline inside one job:
   - on `schedule` (or `workflow_dispatch` with no pasted payload): `fetch_briefing_email.py` uses a Gmail OAuth2 refresh token to find and parse today's `IG_BRIEFING_PAYLOAD` email into `payload.json`; on `repository_dispatch`/`workflow_dispatch` with a pasted payload: write `payload.json` from the event payload directly
   - `render_card.py` → `output/card.png`
   - commit the PNG into `assets/` on the repo (this is how the image gets a public URL — there's no separate image host)
   - build a jsDelivr CDN URL for that committed file and force-purge jsDelivr's cache, then sleep 15s for propagation
   - extract `caption` from the payload
   - `publish_ig.py` creates a media container, polls until `FINISHED`, then publishes

3. **Rendering** (`scripts/render_card.py` + `templates/card_template.html`) — Jinja2 renders the template, Playwright loads the resulting HTML as a local `file://` URL and screenshots it at exactly 1080x1350 (viewport size must stay in sync with the CSS `width`/`height` in the template). `render_card.py` also auto-infers `up`/`down` CSS classes for `us_indices`/`adr` entries from the `+`/`-` sign of `value` when `cls` isn't explicitly set in the payload — see `payload.example.json` for the full expected schema.

## Key constraints

- Images are committed straight into `assets/` in the main branch history — this is the public-hosting mechanism (via jsDelivr/raw.githubusercontent), not a side effect. Growing repo size is a known tradeoff (see README's "已知限制").
- `IG_ACCESS_TOKEN` is a long-lived Meta token (~60 day expiry) with `instagram_content_publish` scope, stored as a GitHub Actions secret and manually rotated — no auto-refresh.
- Instagram has no edit endpoint; a bad post can only be deleted and redone. Test workflow changes via manual `workflow_dispatch` before trusting them on the real schedule.
- `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` / `GMAIL_SELF_ADDRESS` are GitHub Actions secrets used only by `fetch_briefing_email.py` to read the briefing email via the Gmail API — obtained once locally via `scripts/gmail_get_refresh_token.py` (OAuth2 installed-app flow; personal Gmail has no service-account/domain-wide-delegation option). Unrelated to the Claude Project scheduled task, which only needs ordinary Gmail read/send access through its own Gmail connection.
- The Claude Project scheduled task no longer holds or uses any GitHub token — it was removed from this design when the trigger direction flipped from "Claude pushes" to "GitHub pulls".
