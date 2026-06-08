# gmail-janitor

**TL;DR:** A small automation that cleans a cluttered Gmail inbox by driving your *own logged-in Chrome* — it maps your clutter, mass-unsubscribes from junk lists, creates auto-filters, and archives the backlog. It defaults to Archive (reversible) over Delete and never touches lists you keep. Run it once, or wire the included cron to keep your inbox clean automatically.

No OAuth, no API scopes, no third-party server sees your mail. It connects to a Chrome you already started and clicks the same buttons you would.

---

## Why

Inbox cleanup in 2026 is a systems problem, not a willpower problem. The long tail (newsletters, promos, notifications) is ~80% of volume and 0% needs reading. The winning sequence:

1. **Unsubscribe first** — stop the inflow. Archiving without unsubscribing just refills.
2. **Filter** the senders you want out of the inbox but not gone (job alerts, GitHub, course updates).
3. **Archive** the backlog (reversible — stays in All Mail, searchable).
4. **Triage** the survivors with the 5-disposition pass (delete / delegate / respond / defer / do).

This tool automates steps 1-3.

## How it works

Connects to your running Chrome over the DevTools Protocol (CDP) via Playwright `connect_over_cdp`, finds your Gmail tab, and operates the UI. Because it uses *your* session, it sees exactly what you see and needs no credentials.

Proven Gmail behaviors it relies on (captured June 2026):

- **Native unsubscribe:** opening a List-Unsubscribe email surfaces Gmail's header "Unsubscribe" link → a confirm dialog. One-click, safe (RFC 8058). The tool clicks *only* this — never footer links or sender websites.
- **`category:` searches don't take date operators.** `category:promotions older_than:3m` returns zero. Use `category:promotions` undated, or `label:^unsub older_than:Xm` (label form *does* take dates).
- **"Select all conversations that match" doesn't render for `category:` searches or "Most relevant" sort.** So bulk archive runs as a page-by-page loop (select 50 → Archive → repeat).
- **Filters:** search-options panel → From → Create filter → check Skip-Inbox + Mark-read + Apply-to-existing → Create.

## Safety

- **Archive-default.** Delete only with `--delete` and only on buckets you name.
- **Unsubscribe is outward** (signals the sender you're active). The tool asks for the sender list; it does not invent one.
- **Keeps what you keep.** Archive is scoped to senders you unsubscribed/named, never a blanket category wipe, unless you pass `--all-promotions`.
- **Dry-run by default for destructive steps** (`--apply` to actually act).
- **Account guard.** Pass `--account-email` and the tool refuses to run if the active Gmail tab is a different account.

## Install

```bash
pip install playwright pyyaml
playwright install chromium   # only needed if you let it launch its own Chrome

# Start (or restart) Chrome with remote debugging, logged into Gmail:
#   macOS:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

## Usage

```bash
# 1. Map the clutter (read-only)
python janitor.py recon --account-email you@gmail.com

# 2. Top junk senders by volume (read-only)
python janitor.py histogram

# 3. Unsubscribe from a list of senders (native Gmail unsubscribe only)
python janitor.py unsubscribe --senders senders.txt --apply

# 4. Create skip-inbox+archive filters for senders you keep but don't want in inbox
python janitor.py filter --senders keep.txt --apply

# 5. Archive a sender's / query's backlog (reversible)
python janitor.py archive --query 'from:(a@x.com OR b@y.com)' --apply
```

`senders.txt` / `keep.txt` = one email or domain per line.

## Cron / automation

See [`cron/`](cron/) — a launchd plist (macOS) and crontab example that run a weekly maintenance pass: re-histogram, archive the backlog of already-unsubscribed senders, and email yourself a summary. Chrome must be running with `--remote-debugging-port=9222` for the scheduled run to connect.

## Status

v0.1 — tested against Gmail web, June 2026. Gmail's DOM and selectors drift; if a step stops finding an element, the selector constants at the top of `janitor.py` are where to look. Issues/PRs welcome.

## License

MIT — see [LICENSE](LICENSE).
