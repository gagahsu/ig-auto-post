# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Automated pipeline, run twice a day as two parallel tracks sharing the same mechanics: a Taiwan pre-market briefing email and a post-market closing-summary email, each parsed into JSON → rendered as a 1080x1350 IG card image (HTML/CSS via Playwright screenshot) → committed to repo → served via jsDelivr CDN → posted to Instagram via Meta Graph API. A Claude Project scheduled task reads Gmail, parses the source email, and emails the JSON to the user's own inbox — it does not call any external API. An external cron service (cron-job.org) then fires a `repository_dispatch` at the fixed time, which pulls that email via the Gmail API and drives the rest of the pipeline. This "GitHub pulls" design (rather than "Claude pushes") exists because the Claude scheduled task's outbound network access is unreliable. GitHub Actions' own `schedule` trigger was tried first but dropped — it's known to be delayed by hours or skipped entirely, especially on low-activity repos, so timing-critical triggering was moved to cron-job.org hitting the GitHub API's dispatches endpoint instead.

The two tracks are distinguished only by email subject prefix, template, and trigger time — everything else (Gmail OAuth creds, `fetch_briefing_email.py`, `render_card.py`, `publish_ig.py`) is shared:

| | pre-market briefing | post-market closing summary |
|---|---|---|
| workflow | `.github/workflows/post-to-ig.yml` | `.github/workflows/post-closing-to-ig.yml` |
| email subject prefix | `IG_BRIEFING_PAYLOAD` | `IG_CLOSING_PAYLOAD` |
| templates (3-slide carousel) | `templates/card_template_1.html` + `_2.html` + `_3.html` | `templates/closing_card_template_1.html` + `_2.html` + `_3.html` |
| trigger time (Taipei) | 08:05 | 22:15 |

The closing-summary track currently has no documented Claude Project scheduled-task prompt in this repo (unlike `project-scheduled-task-prompt.md` for the briefing) — the user manages that prompt on the Claude Project side themselves; it must send subject `IG_CLOSING_PAYLOAD {YYYY-MM-DD}` with a plain-text body matching `payload_closing.example.json`'s schema exactly.

Each track posts a 3-image IG carousel, not a single image — cramming a variable amount of daily content into one or two cards made text unreadably small on mobile, so each pipeline always renders exactly 3 fixed-purpose slides (briefing: futures+US markets, then news, then groups+opening outlook; closing: indices+institutional flows, then leading/weak groups, then next-day notes) and publishes them as a carousel via `publish_ig.py`.

## Commands

```bash
pip install -r requirements.txt
playwright install --with-deps chromium

# Render the briefing track's 3-slide carousel locally from payload JSON
python3 scripts/render_card.py --payload payload.example.json --out-dir output \
  --template card_template_1.html --template card_template_2.html --template card_template_3.html

# Render the closing-summary track (different templates)
python3 scripts/render_card.py --payload payload_closing.example.json --out-dir output \
  --template closing_card_template_1.html --template closing_card_template_2.html --template closing_card_template_3.html

# Publish to Instagram (requires IG_ACCESS_TOKEN, IG_BUSINESS_ACCOUNT_ID env vars,
# and images must already be at public URLs). One --image-url publishes a single
# image; two or more automatically publishes a carousel.
python3 scripts/publish_ig.py --image-url <url-1> --image-url <url-2> --caption "text"
```

No test suite, linter, or build step exists in this repo.

To test either pipeline without waiting for the schedule: GitHub Actions →
"Post daily briefing to Instagram" (or "Post closing summary to Instagram") →
Run workflow → paste the matching example payload's contents into `payload_json`.

## Architecture

Three separate execution contexts, each owning one stage — do not blur these boundaries:

1. **Claude Project scheduled task** (`project-scheduled-task-prompt.md`, not code that runs in this repo) — reads Gmail for today's briefing email, parses it into the exact JSON schema documented there, and emails that JSON back to the user's own inbox with subject `IG_BRIEFING_PAYLOAD {YYYY-MM-DD}`, plain text body, nothing but the raw JSON. It must NOT call the GitHub API or Instagram/Meta APIs itself — no outbound API calls at all, only Gmail read + Gmail send. If it can't find today's source email, it stops rather than reusing stale data.

2. **GitHub Actions workflows** (`.github/workflows/post-to-ig.yml` and `.github/workflows/post-closing-to-ig.yml`) — the only things that touch Meta/Instagram, and also the thing that pulls from Gmail. Same structure, each triggered by `repository_dispatch` (`post_briefing` / `post_closing`) or `workflow_dispatch` (manual test — payload pasted as a JSON string, or left blank to exercise the Gmail-fetch path). The real daily trigger is an external cron-job.org job that POSTs to `repos/{owner}/{repo}/dispatches` with `{"event_type":"post_briefing"}` / `{"event_type":"post_closing"}` at the fixed Taipei time (see the table above) and no `client_payload` — GitHub Actions' own `schedule` trigger is intentionally not used here (see Key constraints). Pipeline inside one job:
   - on `repository_dispatch` with no `client_payload` (the real daily trigger), or `workflow_dispatch` with no pasted payload: `fetch_briefing_email.py --subject-prefix <prefix>` uses a Gmail OAuth2 refresh token to find and parse today's email into `payload.json`; on `repository_dispatch` with a `client_payload` or `workflow_dispatch` with a pasted payload: write `payload.json` from the event payload directly (legacy manual-payload path, rarely used now that the daily trigger carries no payload)
   - `render_card.py --template <slide-1> --template <slide-2> --template <slide-3>` → `output/slide-1.png`, `output/slide-2.png`, `output/slide-3.png` (3-image carousel; see below)
   - commit all three PNGs into `assets/` on the repo (this is how the images get public URLs — there's no separate image host)
   - build a jsDelivr CDN URL for each committed file, force-purge jsDelivr's cache for each, and poll each until it returns 200
   - extract `caption` from the payload
   - `publish_ig.py` with all three `--image-url` flags creates a carousel-item container per image, polls each until `FINISHED`, wraps them in a `media_type=CAROUSEL` container, polls that, then publishes

3. **Rendering** (`scripts/render_card.py` + `templates/card_template.html`) — Jinja2 renders the template, Playwright loads the resulting HTML as a local `file://` URL and screenshots it at exactly 1080x1350 (viewport size must stay in sync with the CSS `width`/`height` in the template). `render_card.py` also auto-infers `up`/`down` CSS classes for `us_indices`/`adr` entries from the `+`/`-` sign of `value` when `cls` isn't explicitly set in the payload — see `payload.example.json` for the full expected schema.

## Key constraints

- Images are committed straight into `assets/` in the main branch history — this is the public-hosting mechanism (via jsDelivr/raw.githubusercontent), not a side effect. Growing repo size is a known tradeoff (see README's "已知限制").
- `IG_ACCESS_TOKEN` is a long-lived Meta token (~60 day expiry) with `instagram_content_publish` scope, stored as a GitHub Actions secret and manually rotated — no auto-refresh.
- Instagram has no edit endpoint; a bad post can only be deleted and redone. Test workflow changes via manual `workflow_dispatch` before trusting them on the real daily trigger.
- Daily triggering lives outside this repo, on cron-job.org — two jobs POST to `repos/{owner}/{repo}/dispatches` (`post_briefing` at 00:05 UTC / 08:05 Taipei, `post_closing` at 14:15 UTC / 22:15 Taipei) using a fine-grained GitHub PAT scoped to only this repo (`Contents` + `Actions`: read/write), stored in cron-job.org's request headers. That PAT expires (~90 days) and needs manual renewal in both GitHub and cron-job.org — nothing in this repo can detect or alert on it silently going stale, so if posts stop appearing, check the PAT expiry first.
- `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` / `GMAIL_SELF_ADDRESS` are GitHub Actions secrets used only by `fetch_briefing_email.py` to read the briefing email via the Gmail API — obtained once locally via `scripts/gmail_get_refresh_token.py` (OAuth2 installed-app flow; personal Gmail has no service-account/domain-wide-delegation option). Unrelated to the Claude Project scheduled task, which only needs ordinary Gmail read/send access through its own Gmail connection.
- The Claude Project scheduled task no longer holds or uses any GitHub token — it was removed from this design when the trigger direction flipped from "Claude pushes" to "GitHub pulls".
- Cards have a fixed 1080x1350 frame but daily content length (news count, group-list length, notes) varies. Elements marked `.fit-text` in the templates get auto-shrunk by a Playwright post-load JS pass in `render_card.py` (down to a 55% floor) if content would otherwise overflow the card's border — see `AUTOFIT_JS`/`MIN_FIT_SCALE` in that file. This is a last-resort safety net; the primary fix for "too much text" is the 3-slide carousel split itself, not this shrink mechanism.
