# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Automated pipeline: Taiwan pre-market briefing email → parsed into JSON → rendered as a 1080x1350 IG card image (HTML/CSS via Playwright screenshot) → committed to repo → served via jsDelivr CDN → posted to Instagram via Meta Graph API. Triggered daily by a Claude Project scheduled task, which reads Gmail and fires a `repository_dispatch` GitHub Actions event.

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

1. **Claude Project scheduled task** (`project-scheduled-task-prompt.md`, not code that runs in this repo) — reads Gmail for today's briefing email, parses it into the exact JSON schema documented there, and calls the GitHub `dispatches` API with `event_type: post_briefing`. It must NOT call Instagram/Meta APIs itself — that's the workflow's job. If it can't find today's email, it stops rather than reusing stale data.

2. **GitHub Actions workflow** (`.github/workflows/post-to-ig.yml`) — the only thing that touches Meta/Instagram. Triggered by `repository_dispatch` (real) or `workflow_dispatch` (manual test, payload pasted as a JSON string). Pipeline inside one job:
   - write `payload.json` from the event payload
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
- The GitHub token used by the Claude Project scheduled task (for `repository_dispatch`) is a separate fine-grained PAT scoped to `Contents: Read/write` + `Actions: Read/write` on this repo only — it is NOT one of the repo's `IG_ACCESS_TOKEN`/`IG_BUSINESS_ACCOUNT_ID` secrets and is configured on the Claude Project side, not in this repo.
