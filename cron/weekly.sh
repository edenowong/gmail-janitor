#!/usr/bin/env bash
# Weekly gmail-janitor maintenance pass.
# Requires Chrome running with --remote-debugging-port=9222, logged into Gmail.
# Edit ACCOUNT, SLOT, and the senders files for your setup.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT="${GMAIL_JANITOR_ACCOUNT:-you@gmail.com}"
SLOT="${GMAIL_JANITOR_SLOT:-0}"
PORT=9222

# 1. Make sure a debuggable Chrome is up (no-op if already running on the port).
if ! curl -s "http://localhost:${PORT}/json/version" >/dev/null 2>&1; then
  echo "Chrome not on :${PORT}. Start it logged into Gmail:"
  echo "  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=${PORT}"
  exit 1
fi

cd "$REPO"

# 2. Refresh the junk histogram (logged, not acted on).
python janitor.py --slot "$SLOT" --account-email "$ACCOUNT" histogram > "cron/last_histogram.txt" || true

# 3. Re-archive the backlog of senders you've already unsubscribed from
#    (catches stragglers). Edit cron/maintained_senders.txt with one address/line.
if [ -f cron/maintained_senders.txt ]; then
  QUERY="from:($(paste -sd '|' cron/maintained_senders.txt | sed 's/|/ OR /g'))"
  python janitor.py --slot "$SLOT" --account-email "$ACCOUNT" archive --query "$QUERY" --apply || true
fi

echo "gmail-janitor weekly pass done: $(date)"
