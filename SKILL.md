---
name: gmail-janitor
description: Clean a cluttered Gmail inbox by driving the user's own logged-in Chrome over CDP — map clutter, mass-unsubscribe from junk lists, create skip-inbox filters, and archive the backlog. Use when the user says "clean my inbox", "inbox zero", "unsubscribe from junk", "declutter Gmail", "too many emails", or wants to organize/triage their mail. Archive-default, reversible, no OAuth.
---

# gmail-janitor

Clean a Gmail inbox the right way: stop the inflow, then clear the backlog. Drives the user's logged-in Chrome over CDP — no API, no credentials.

## Order of operations (do not reorder)

1. **Recon first (read-only).** Map the clutter before touching anything. `python janitor.py recon --account-email <user>`. Confirm the active account is correct before any write.
2. **Histogram.** `python janitor.py histogram` — top senders by volume. This drives the unsubscribe + filter lists; do not invent sender lists.
3. **Unsubscribe.** Stop the inflow first. Archiving without unsubscribing just refills. Native Gmail unsubscribe only (`janitor.py unsubscribe --senders junk.txt --apply`). Senders without a native link → filter instead, never footer links or sender sites.
4. **Filter.** For senders the user keeps but wants out of the inbox (job alerts, GitHub, course updates): `janitor.py filter --senders keep.txt --apply` (skip-inbox + mark-read + apply-to-existing). A filter with apply-to-existing is also the **fastest archive for a deep backlog** — one server-side op instead of N page loops.
5. **Archive.** Backlog of unsubscribed senders: `janitor.py archive --query 'from:(...)' --apply`. Reversible (stays in All Mail).
6. **Triage survivors.** What's left in Primary is real mail — apply the 5-disposition pass (delete / delegate / respond / defer / do).

## Hard rules

- **Confirm before each destructive batch.** Show count + a sample first. Never silent mass-delete.
- **Archive-default.** Delete only on explicit per-bucket approval.
- **Unsubscribe is outward** (signals the sender). Confirm the sender list before running.
- **Account guard.** Always pass `--account-email`; the tool refuses if the active tab is a different account. Critical when the user has work + personal Gmail in the same Chrome.
- **Keep what the user keeps.** Scope archive to named senders, not a blanket category wipe, unless explicitly told "archive all promotions".

## Gmail quirks the tool already handles

- `category:` searches **ignore date operators** (`older_than`/`before` → zero results). Use `category:promotions` undated, or `label:^unsub older_than:Xm` (label form takes dates).
- "Select all conversations that match" **doesn't render** for `category:` searches or "Most relevant" sort → archive runs as a page-by-page loop, or (better) via a filter's apply-to-existing.
- Filters auto-follow label renames (Gmail tracks labels by ID), so restructuring labels won't break filters.

## Labels (optional restructure)

If the user has label sprawl: collapse the flat list into nested trees (`Travel/`, `Finance/`, `Work/`, ...) by renaming each label to `Parent/Leaf` in `#settings/labels` (Edit → set name → uncheck "Nest label under" → Save). Drive labels via filters going forward. Flag true duplicates (two labels for the same thing) for the user to pick a canonical — merging moves mail and isn't auto.

## Automation

See `cron/` to run a weekly maintenance pass (re-histogram, archive already-unsubscribed senders' backlog, summary). Requires Chrome running with `--remote-debugging-port=9222`.
