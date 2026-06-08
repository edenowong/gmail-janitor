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

If the user has label sprawl: collapse the flat list into nested trees (`Travel/`, `Finances/`, `Work/`, ...). Drive labels via filters going forward. Flag true duplicates (two labels for the same thing) for the user to pick a canonical — merging moves mail and isn't auto.

### Nesting — ALWAYS verify, it has sharp edges

Gmail nesting is NOT just "put a slash in the name". Hard-won rules:

1. **The parent label must already exist as a real label.** Renaming a label to `Parent/Child` does NOT auto-create `Parent`. If `Parent` doesn't exist, the child renders **flat** as a literal label named `Parent/Child` — looks nested in the name, is not nested in the tree.
2. **You cannot create a bare parent while `Parent/X` children already exist.** Gmail reserves the name and the create **silently no-ops** (no error toast, no row). So create parents BEFORE renaming children into them — or if you nested first, see step 4.
3. **Some parent names are reserved** (collide with Gmail system/category labels). The create silently fails. If a name won't take, pick an alternative (`Finance`→`Finances`, `Accounts`→`Logins`) and rename children into the alternative.
4. **Recovery when children are already flat `Parent/X`:** create a parent with an *available* name (`Finances`), then rename each flat `Finance/Amex` → `Finances/Amex`. It now nests under the real parent.
5. **VERIFY, don't trust the "Saved" click.** After nesting, confirm from the source of truth: open a child's Edit → "Nest label under" dropdown. Properly-nested children appear as **leaf names** (`Vegas`); unnested ones appear with **full slash paths** (`Finance/Amex`). Or check the nav: a real parent shows as an expandable group. A batch reporting "OK" only means the Save button fired — it is NOT evidence the label nested or even persisted (tab-pile lag silently drops saves).

## Automation

See `cron/` to run a weekly maintenance pass (re-histogram, archive already-unsubscribed senders' backlog, summary). Requires Chrome running with `--remote-debugging-port=9222`.
