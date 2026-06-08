# Automation

Run a weekly maintenance pass: refresh the junk histogram and re-archive the backlog
of senders you've already unsubscribed from (catches stragglers).

**Prerequisite:** Chrome running with `--remote-debugging-port=9222`, logged into Gmail.
The scheduled run connects to that session — if Chrome isn't up, the pass no-ops with a message.

## Setup

1. List the senders to keep tidy, one per line:
   ```
   echo "promos@oldstore.com" >> cron/maintained_senders.txt
   ```
2. Edit `weekly.sh` env (or export `GMAIL_JANITOR_ACCOUNT` / `GMAIL_JANITOR_SLOT`).
3. Pick a scheduler:

### macOS (launchd) — recommended
```bash
cp cron/com.gmail-janitor.weekly.plist ~/Library/LaunchAgents/
# edit the ProgramArguments path + EnvironmentVariables in the copied file
launchctl load ~/Library/LaunchAgents/com.gmail-janitor.weekly.plist
```

### crontab (Linux/macOS)
```cron
# Mondays 09:00
0 9 * * 1 GMAIL_JANITOR_ACCOUNT=you@gmail.com /abs/path/gmail-janitor/cron/weekly.sh >> /tmp/gmail-janitor.log 2>&1
```

## Note on headless

Gmail's UI requires a logged-in session. The cleanest setup is a long-lived Chrome
launched once with the debug port (it can be a dedicated profile). A truly headless
cron on a server needs that Chrome + Gmail login to persist — keep the debug Chrome
running under your user session rather than spawning a fresh one per run.
