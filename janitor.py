#!/usr/bin/env python3
"""gmail-janitor — clean a Gmail inbox by driving your own logged-in Chrome over CDP.

No OAuth, no API. Connects to a Chrome started with --remote-debugging-port and
operates the Gmail UI via Playwright. Archive-default, unsubscribe via Gmail's
native List-Unsubscribe only. See README.md.

Tested against Gmail web, June 2026. Gmail's DOM drifts — if a step stops finding
an element, the JS_* constants below are where to look.
"""
import argparse
import sys
import time
import urllib.parse
from collections import Counter

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("pip install playwright pyyaml && playwright install chromium")

CDP_DEFAULT = "http://localhost:9222"

# ---- proven JS snippets (Gmail web, June 2026) ----
JS_COUNT = "() => { const d=document.querySelector('.Dj'); return d ? d.innerText.replace(/\\s+/g,' ').trim() : 'n/a'; }"
JS_ROWS = "() => document.querySelectorAll('tr.zA').length"
JS_SENDERS = "() => [...document.querySelectorAll('tr.zA')].map(r => { const s=r.querySelector('span[email]'); return s ? (s.getAttribute('email')||'').toLowerCase() : null; }).filter(Boolean)"
JS_SELECT_ALL_VISIBLE = "() => { const c=[...document.querySelectorAll('div[role=checkbox],span[role=checkbox]')].filter(e=>e.offsetParent); if(c.length) c[0].click(); return !!c.length; }"
JS_ARCHIVE = "() => { const b=[...document.querySelectorAll('div[role=button]')].find(e=>/^Archive$/.test(e.getAttribute('aria-label')||'')); if(!b) return false; b.click(); return true; }"
JS_OPEN_FIRST = "() => { const r=document.querySelector('tr.zA'); if(!r) return false; (r.querySelector('.bog')||r).click(); return true; }"
JS_CLICK_UNSUB = "() => { const v=[...document.querySelectorAll('span,a,div[role=link]')].filter(e=>/^unsubscribe$/i.test((e.innerText||'').trim()) && e.offsetParent!==null); if(!v.length) return false; v[0].click(); return true; }"
JS_CONFIRM_UNSUB = "() => { const d=document.querySelector('div[role=dialog],div[role=alertdialog]'); if(!d) return 'no-dialog'; const b=[...d.querySelectorAll('button,div[role=button]')].find(x=>/^unsubscribe$/i.test((x.innerText||'').trim())); if(!b) return 'no-btn'; b.click(); return 'ok'; }"
JS_OPEN_SEARCH_OPTS = "() => { const b=document.querySelector('button[aria-label*=\"earch options\"]')||document.querySelector('div[aria-label*=\"earch options\"]'); if(b){b.click(); return true;} return false; }"
JS_ACCOUNT = "() => (document.title.match(/[\\w.+-]+@[\\w.-]+/)||['?'])[0]"


def search_url(slot, query):
    return f"https://mail.google.com/mail/u/{slot}/#search/" + urllib.parse.quote(query)


class Gmail:
    def __init__(self, page, slot):
        self.page = page
        self.slot = slot

    def goto(self, frag):
        self.page.goto(f"https://mail.google.com/mail/u/{self.slot}/#{frag}")
        self._wait()

    def search(self, query):
        self.page.goto(search_url(self.slot, query))
        self._wait()

    def _wait(self):
        try:
            self.page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        time.sleep(1.3)

    def ev(self, js, *args):
        return self.page.evaluate(js, *args) if args else self.page.evaluate(js)

    def active_account(self):
        return self.ev(JS_ACCOUNT)


def connect(cdp):
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(cdp)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = next((pg for pg in ctx.pages if "mail.google.com" in pg.url), None)
    if page is None:
        page = ctx.new_page()
    return p, browser, page


def guard_account(g, expected):
    if not expected:
        return
    actual = g.active_account()
    if expected.lower() not in (actual or "").lower():
        sys.exit(f"REFUSING: active Gmail tab is '{actual}', expected '{expected}'. "
                 f"Switch accounts or fix --account-email.")


# ---- commands ----
def cmd_recon(g, args):
    guard_account(g, args.account_email)
    buckets = [
        ("All Mail", "all"),
        ("Primary inbox", "inbox"),
    ]
    print("== headline ==")
    for label, frag in buckets:
        g.goto(frag)
        print(f"  {label:16s}: {g.ev(JS_COUNT)}")
    print("== clutter buckets (Gmail caps big counts at 'many') ==")
    for label, q in [
        ("bulk (^unsub)", "label:^unsub"),
        ("promotions", "category:promotions"),
        ("social", "category:social"),
        ("updates", "category:updates"),
        ("unread", "is:unread"),
        ("older 2y", "older_than:2y"),
        ("large >10MB", "larger:10m"),
    ]:
        g.search(q)
        print(f"  {label:16s}: {g.ev(JS_COUNT)}")


def cmd_histogram(g, args):
    guard_account(g, args.account_email)
    senders, domains = Counter(), Counter()
    for q in ["label:^unsub", "category:promotions"]:
        for p in range(1, args.pages + 1):
            frag = urllib.parse.quote(q) + ("" if p == 1 else f"/p{p}")
            g.page.goto(f"https://mail.google.com/mail/u/{g.slot}/#search/{frag}")
            g._wait()
            emails = g.ev(JS_SENDERS)
            if not emails:
                break
            for e in emails:
                senders[e] += 1
                if "@" in e:
                    domains[e.split("@")[1]] += 1
    print("== top senders (junk buckets) ==")
    for e, c in senders.most_common(args.top):
        print(f"  {c:4d}  {e}")
    print("== top domains ==")
    for d, c in domains.most_common(15):
        print(f"  {c:4d}  {d}")


def cmd_unsubscribe(g, args):
    guard_account(g, args.account_email)
    senders = read_lines(args.senders)
    for addr in senders:
        status = _unsub_one(g, addr) if args.apply else "DRY-RUN"
        print(f"  {addr:40s} -> {status}")


def _unsub_one(g, addr):
    g.search(f"from:{addr}")
    if not g.ev(JS_OPEN_FIRST):
        return "no-mail"
    time.sleep(1.5)
    if not g.ev(JS_CLICK_UNSUB):
        return "NO-NATIVE-LINK"
    time.sleep(1.6)
    res = g.ev(JS_CONFIRM_UNSUB)
    time.sleep(1.2)
    return "UNSUBSCRIBED" if res == "ok" else res


def cmd_filter(g, args):
    guard_account(g, args.account_email)
    senders = read_lines(args.senders)
    frm = " OR ".join(senders)
    if not args.apply:
        print(f"  DRY-RUN: would create skip-inbox+archive filter for: {frm}")
        return
    print(f"  creating filter (skip inbox + mark read + apply to existing) for {len(senders)} sender(s)")
    print(f"  -> {_make_filter(g, frm)}")


def _make_filter(g, frm):
    g.goto("inbox")
    if not g.ev(JS_OPEN_SEARCH_OPTS):
        return "no-search-opts"
    time.sleep(1.0)
    filled = g.ev(
        "(v) => { const ins=[...document.querySelectorAll('input[type=text]')].filter(e=>e.offsetParent && (e.getAttribute('aria-label')||'')!=='Search mail'); if(!ins.length) return false; const f=ins[0]; f.focus(); f.value=v; f.dispatchEvent(new Event('input',{bubbles:true})); f.dispatchEvent(new Event('change',{bubbles:true})); return f.value.length>0; }",
        frm)
    if not filled:
        return "fill-fail"
    time.sleep(0.5)
    g.ev("() => { const b=[...document.querySelectorAll('button,div[role=button]')].find(e=>/create filter/i.test((e.innerText||'').trim()) && e.offsetParent); if(b) b.click(); }")
    time.sleep(1.3)
    g.ev("() => { const want=[/skip the inbox/i,/mark as read/i,/also apply filter/i]; const boxes=[...document.querySelectorAll('input[type=checkbox]')].filter(e=>e.offsetParent); for(const b of boxes){ const lbl=(b.closest('div')?.innerText||'').trim(); if(want.some(rx=>rx.test(lbl)) && !b.checked) b.click(); } }")
    time.sleep(0.5)
    g.ev("() => { const b=[...document.querySelectorAll('button,div[role=button]')].find(e=>/^create filter$/i.test((e.innerText||'').trim()) && e.offsetParent); if(b) b.click(); }")
    time.sleep(1.8)
    return "created"


def cmd_archive(g, args):
    guard_account(g, args.account_email)
    if not args.apply:
        g.search(args.query)
        print(f"  DRY-RUN: {args.query} -> {g.ev(JS_COUNT)} (pass --apply to archive)")
        return
    g.search(args.query)
    total = 0
    for i in range(args.max_passes):
        n = g.ev(JS_ROWS)
        if n == 0:
            break
        g.ev(JS_SELECT_ALL_VISIBLE)
        time.sleep(0.7)
        if not g.ev(JS_ARCHIVE):
            print("  no archive button — stopping")
            break
        total += n
        time.sleep(2.0)
        print(f"  pass {i+1}: archived ~{n} (total ~{total})", flush=True)
    print(f"  done. archived ~{total}. NOTE: for deep backlogs prefer a filter "
          f"(skip-inbox + apply-to-existing) — one server-side op vs N page loops.")


def read_lines(path):
    with open(path) as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def main():
    ap = argparse.ArgumentParser(description="Clean a Gmail inbox via your logged-in Chrome.")
    ap.add_argument("--cdp", default=CDP_DEFAULT, help="Chrome DevTools endpoint")
    ap.add_argument("--slot", default="0", help="Gmail account slot (u/0, u/1, ...)")
    ap.add_argument("--account-email", default="", help="Refuse to run unless active tab matches")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("recon")
    h = sub.add_parser("histogram"); h.add_argument("--pages", type=int, default=8); h.add_argument("--top", type=int, default=25)
    u = sub.add_parser("unsubscribe"); u.add_argument("--senders", required=True); u.add_argument("--apply", action="store_true")
    f = sub.add_parser("filter"); f.add_argument("--senders", required=True); f.add_argument("--apply", action="store_true")
    a = sub.add_parser("archive"); a.add_argument("--query", required=True); a.add_argument("--apply", action="store_true"); a.add_argument("--max-passes", type=int, default=40)

    args = ap.parse_args()
    p, browser, page = connect(args.cdp)
    g = Gmail(page, args.slot)
    try:
        {"recon": cmd_recon, "histogram": cmd_histogram, "unsubscribe": cmd_unsubscribe,
         "filter": cmd_filter, "archive": cmd_archive}[args.cmd](g, args)
    finally:
        browser.close()
        p.stop()


if __name__ == "__main__":
    main()
