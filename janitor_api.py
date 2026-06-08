#!/usr/bin/env python3
"""gmail-janitor API backend — Gmail REST API instead of driving the UI.

Deterministic, batched, exact counts. Same subcommands as janitor.py
(recon / histogram / unsubscribe / filter / archive) but backed by
users.messages.batchModify, settings.filters.create, and direct
List-Unsubscribe (RFC 8058) POSTs.

Setup: see SETUP_API.md. Needs credentials.json (OAuth client) once;
caches token.json. Scope: gmail.modify + gmail.settings.basic.
"""
import argparse
import os
import sys
import re
from collections import Counter
from email.utils import parseaddr

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import requests
except ImportError:
    sys.exit("pip install google-api-python-client google-auth-oauthlib requests")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
CHUNK = 1000  # batchModify hard limit is 1000 ids/call


def service(creds_path="credentials.json", token_path="token.json"):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                sys.exit(f"Missing {creds_path}. See SETUP_API.md.")
            creds = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES).run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def count(svc, q):
    """Exact-ish count via resultSizeEstimate (Gmail's own estimate)."""
    r = svc.users().messages().list(userId="me", q=q, maxResults=1).execute()
    return r.get("resultSizeEstimate", 0)


def all_ids(svc, q):
    ids, page = [], None
    while True:
        r = svc.users().messages().list(userId="me", q=q, pageToken=page, maxResults=500).execute()
        ids += [m["id"] for m in r.get("messages", [])]
        page = r.get("nextPageToken")
        if not page:
            break
    return ids


def batch_modify(svc, ids, add=None, remove=None):
    for i in range(0, len(ids), CHUNK):
        body = {"ids": ids[i:i + CHUNK]}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        svc.users().messages().batchModify(userId="me", body=body).execute()
    return len(ids)


def label_map(svc):
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    return {l["name"]: l["id"] for l in labels}


def ensure_label(svc, name):
    """Return label id, creating it (and its slash-parents) if needed.
    Gmail nests on '/' but the PARENT must exist as a real label first —
    create parents top-down so children actually nest (see SKILL.md)."""
    m = label_map(svc)
    parts = name.split("/")
    for i in range(len(parts)):
        sub = "/".join(parts[:i + 1])
        if sub not in m:
            created = svc.users().labels().create(
                userId="me", body={"name": sub,
                                    "labelListVisibility": "labelShow",
                                    "messageListVisibility": "show"}).execute()
            m[sub] = created["id"]
    return m[name]


# ---- commands ----
def cmd_recon(svc, a):
    for label, q in [
        ("All Mail", "in:anywhere"), ("Primary inbox", "in:inbox category:primary"),
        ("bulk (^unsub)", "label:^unsub"), ("promotions", "category:promotions"),
        ("social", "category:social"), ("updates", "category:updates"),
        ("unread", "is:unread"), ("older 2y", "older_than:2y"), ("large >10MB", "larger:10M"),
    ]:
        print(f"  {label:16s}: ~{count(svc, q):,}")


def cmd_histogram(svc, a):
    ids = all_ids(svc, a.query)[: a.sample]
    senders = Counter()
    # metadata fetch (From header only) — cheap
    for mid in ids:
        msg = svc.users().messages().get(userId="me", id=mid, format="metadata",
                                         metadataHeaders=["From"]).execute()
        hdrs = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        addr = parseaddr(hdrs.get("From", ""))[1].lower()
        if addr:
            senders[addr] += 1
    print(f"== top senders in `{a.query}` (sampled {len(ids)}) ==")
    for e, c in senders.most_common(a.top):
        print(f"  {c:4d}  {e}")


def cmd_archive(svc, a):
    ids = all_ids(svc, a.query)
    print(f"  {a.query} -> {len(ids):,} messages")
    if not a.apply:
        print("  DRY-RUN (pass --apply to archive). Archive = remove INBOX label, reversible.")
        return
    n = batch_modify(svc, ids, remove=["INBOX"])
    print(f"  archived {n:,} (still in All Mail).")


def cmd_filter(svc, a):
    senders = read_lines(a.senders)
    crit_from = " OR ".join(senders)
    lid = ensure_label(svc, a.label) if a.label else None
    add = [lid] if lid else []
    if not a.apply:
        print(f"  DRY-RUN: filter from:({crit_from}) -> skip inbox{' + label '+a.label if a.label else ''}")
        return
    body = {"criteria": {"from": crit_from},
            "action": {"removeLabelIds": ["INBOX"], "addLabelIds": add}}
    svc.users().settings().filters().create(userId="me", body=body).execute()
    # filters only apply to NEW mail — clear the existing backlog explicitly
    ids = all_ids(svc, f"from:({crit_from})")
    batch_modify(svc, ids, add=add or None, remove=["INBOX"])
    print(f"  filter created + {len(ids):,} existing archived.")


def cmd_unsubscribe(svc, a):
    senders = read_lines(a.senders)
    for s in senders:
        print(f"  {s:40s} -> {unsub_one(svc, s, a.apply)}")


def unsub_one(svc, sender, apply):
    r = svc.users().messages().list(userId="me", q=f"from:{sender}", maxResults=1).execute()
    msgs = r.get("messages", [])
    if not msgs:
        return "no-mail"
    msg = svc.users().messages().get(userId="me", id=msgs[0]["id"], format="metadata",
                                     metadataHeaders=["List-Unsubscribe", "List-Unsubscribe-Post"]).execute()
    hdrs = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    lu = hdrs.get("list-unsubscribe", "")
    one_click = "list-unsubscribe-post" in hdrs  # RFC 8058
    urls = re.findall(r"<([^>]+)>", lu)
    http = next((u for u in urls if u.startswith("http")), None)
    mailto = next((u for u in urls if u.startswith("mailto:")), None)
    if not (http or mailto):
        return "NO-LIST-UNSUBSCRIBE"
    if not apply:
        return f"DRY-RUN ({'one-click' if one_click else 'http' if http else 'mailto'})"
    if http and one_click:
        resp = requests.post(http, data={"List-Unsubscribe": "One-Click"}, timeout=15)
        return f"POSTed one-click ({resp.status_code})"
    if http:
        return f"http unsubscribe link (manual confirm may be needed): {http}"
    return f"mailto unsubscribe: {mailto}"


def read_lines(path):
    with open(path) as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def main():
    ap = argparse.ArgumentParser(description="Gmail inbox cleanup via the Gmail REST API.")
    ap.add_argument("--credentials", default="credentials.json")
    ap.add_argument("--token", default="token.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("recon")
    h = sub.add_parser("histogram"); h.add_argument("--query", default="label:^unsub"); h.add_argument("--sample", type=int, default=500); h.add_argument("--top", type=int, default=25)
    ar = sub.add_parser("archive"); ar.add_argument("--query", required=True); ar.add_argument("--apply", action="store_true")
    f = sub.add_parser("filter"); f.add_argument("--senders", required=True); f.add_argument("--label", default=""); f.add_argument("--apply", action="store_true")
    u = sub.add_parser("unsubscribe"); u.add_argument("--senders", required=True); u.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    svc = service(a.credentials, a.token)
    {"recon": cmd_recon, "histogram": cmd_histogram, "archive": cmd_archive,
     "filter": cmd_filter, "unsubscribe": cmd_unsubscribe}[a.cmd](svc, a)


if __name__ == "__main__":
    main()
