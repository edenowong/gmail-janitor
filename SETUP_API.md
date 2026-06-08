# API backend setup (one-time, ~5 min)

`janitor_api.py` uses the Gmail REST API instead of driving the browser. It's
deterministic and batched — archive/label thousands per call, exact counts, no
UI flakiness. Trade-off: a one-time OAuth setup.

## 1. Enable the Gmail API

1. Go to <https://console.cloud.google.com/> → create a project (or pick one).
2. APIs & Services → Library → search "Gmail API" → **Enable**.

## 2. Create an OAuth client

1. APIs & Services → **OAuth consent screen** → External → fill app name + your email → add yourself as a Test user.
2. APIs & Services → **Credentials** → Create credentials → **OAuth client ID** → Application type **Desktop app**.
3. Download the JSON → save as `credentials.json` in this repo folder.

## 3. First run (consent once)

```bash
pip install google-api-python-client google-auth-oauthlib requests
python janitor_api.py recon
```

A browser opens → approve the `gmail.modify` + `gmail.settings.basic` scopes.
A `token.json` is cached; you won't be asked again (it auto-refreshes).

## Usage (same verbs as the CDP version, API-backed)

```bash
python janitor_api.py recon                         # exact-ish bucket counts
python janitor_api.py histogram --query 'label:^unsub' --sample 500
python janitor_api.py archive  --query 'from:(substack.com OR iqalerts@questrade.com)' --apply
python janitor_api.py filter   --senders keep.txt --label 'Careers' --apply
python janitor_api.py unsubscribe --senders junk.txt --apply
```

- **archive** = remove the `INBOX` label (reversible, stays in All Mail). No 50-per-page loop — all matches in one batch.
- **filter** creates a real Gmail filter AND clears the existing backlog (filters alone only act on new mail).
- **unsubscribe** reads the `List-Unsubscribe` header and POSTs the RFC-8058 one-click URL directly. mailto/manual-only senders are reported, not guessed.
- **label nesting** (`--label 'Careers'`): `ensure_label` creates slash-parents top-down so children actually nest — bare-parent-first, the rule the UI version learned the hard way (see SKILL.md). Reserved names (`Finance`, `Accounts`) still apply — pick alternatives (`Finances`, `Services`).

## Security

- `credentials.json` and `token.json` are gitignored. Never commit them.
- Scope is `gmail.modify` (read/label/archive/trash) + `gmail.settings.basic` (filters). Not `gmail.send`. The token never leaves your machine.
