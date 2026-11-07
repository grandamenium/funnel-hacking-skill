#!/usr/bin/env python3
"""fh.py - funnel-hacking run manager.

One run folder per funnel: funnel.json (graph), events.jsonl (append-only,
chronological), assets/ (screenshots, HTML, text, messages), timeline.md
(generated from events.jsonl), analysis.md (written by the agent).

The script only ever performs GET navigations. It never fills or submits
forms, never logs in and never clicks purchase buttons. Gates are detected and
reported so the agent can stop and ask the user.

Run `python3 fh.py -h` or `python3 fh.py <command> -h` for usage.
"""
import argparse
import datetime as dt
import email
import email.policy
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse

SCHEMA_VERSION = 1
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 funnel-research")
MAX_SHOT_H = 16000  # CSS px; very long or infinite-scroll pages otherwise make 100M+ pixel PNGs
MIN_GAP_S = 3.0  # politeness delay between page loads in one run

NODE_TYPES = [
    "ad", "post", "video", "profile", "link-in-bio", "landing", "opt-in",
    "thank-you", "email", "sms", "dm", "webinar", "vsl", "sales-page",
    "order-form", "checkout", "upsell", "downsell", "order-bump", "community",
    "retargeting-ad", "other",
]
BUY_TYPES = {"checkout", "order-form", "upsell", "downsell", "order-bump"}

PIXELS = {
    "meta_pixel": r"connect\.facebook\.net|facebook\.com/tr",
    "google_tag": r"googletagmanager\.com|google-analytics\.com|gtag/js",
    "google_ads": r"googleadservices\.com|doubleclick\.net",
    "tiktok_pixel": r"analytics\.tiktok\.com",
    "linkedin_insight": r"snap\.licdn\.com|px\.ads\.linkedin\.com",
    "x_pixel": r"static\.ads-twitter\.com|analytics\.twitter\.com",
    "pinterest_tag": r"ct\.pinterest\.com|s\.pinimg\.com/ct",
    "snap_pixel": r"tr\.snapchat\.com|sc-static\.net",
    "reddit_pixel": r"redditstatic\.com/ads|alb\.reddit\.com",
    "hotjar": r"hotjar\.com",
    "ms_clarity": r"clarity\.ms",
    "segment": r"cdn\.segment\.com|api\.segment\.io",
    "hubspot": r"js\.hs-scripts\.com|hs-analytics\.net|hsforms",
    "klaviyo": r"klaviyo\.com",
    "convertkit": r"convertkit\.com|ck\.page|kit\.com",
    "mailchimp": r"list-manage\.com|chimpstatic\.com",
    "activecampaign": r"activehosted\.com|trackcmp\.net",
    "clickfunnels": r"clickfunnels\.com|myclickfunnels\.com",
    "kajabi": r"kajabi",
    "gohighlevel": r"leadconnectorhq\.com|msgsndr\.com|highlevel",
    "stripe": r"js\.stripe\.com",
    "paypal": r"paypal\.com/sdk",
    "hyros": r"hyros\.com",
    "triple_whale": r"triplewhale",
    "wistia": r"wistia\.(com|net)",
    "vimeo": r"player\.vimeo\.com",
    "vidalytics": r"vidalytics",
    "youtube_embed": r"youtube\.com/embed|youtube-nocookie\.com",
    "calendly": r"calendly\.com",
    "intercom": r"intercom\.io|intercomcdn",
}
TRACKING_PARAMS = re.compile(
    r"^(utm_\w+|fbclid|gclid|gbraid|wbraid|ttclid|msclkid|li_fat_id|twclid|"
    r"mc_cid|mc_eid|_hsenc|_hsmi|ref|affiliate|aff|aff_id|via|src|source|"
    r"cid|campaign|adset|ad_id|sscid|irclickid|clickid)$", re.I)
URGENCY = re.compile(
    r"(limited time|only \d+ (left|spots|seats)|spots? (are )?limited|ends "
    r"(tonight|today|soon|in)|expires?|deadline|countdown|last chance|closing "
    r"(soon|tonight)|hurry|before (it'?s|the) gone|price (goes|will go) up|"
    r"while (supplies|spots) last|doors close|today only|\d+ hours? left|"
    r"limited (spots|seats|availability)|selling fast|almost (full|gone))", re.I)
PROOF = re.compile(
    r"(testimonial|case stud(y|ies)|as seen (on|in)|featured (on|in)|trusted by|"
    r"\d[\d,.]*\+? (students|customers|members|clients|users|businesses|people)|"
    r"reviews?\b|rated \d|\d(\.\d)? ?(/ ?5|stars?)|success stor(y|ies)|results|"
    r"money[- ]back|guarantee)", re.I)
PRICE = re.compile(r"(?:[$€£]\s?\d[\d,]*(?:\.\d{2})?(?:\s?/\s?(?:mo|month|yr|year|week))?|"
                   r"\b\d[\d,]*(?:\.\d{2})?\s?(?:USD|EUR|GBP)\b|\bfree\b)", re.I)
BUY_WORDS = re.compile(
    r"(complete (my |your )?(order|purchase)|place (my |your )?order|pay now|"
    r"buy now|checkout|order summary|billing (address|information)|card number|"
    r"credit card|add to cart|proceed to payment|complete checkout|"
    r"secure (checkout|payment)|order total|yes,? (upgrade|add)|one[- ]time offer)",
    re.I)
NO_THANKS = re.compile(r"(no,? thanks|no thank you|skip|i'?ll pass|not now|"
                       r"maybe later|continue without)", re.I)
SKIP_LINK = re.compile(
    r"(privacy|terms|cookie|legal|disclaimer|refund|gdpr|accessibility|"
    r"careers|press|sitemap|login|log-in|signin|sign-in|account|"
    r"unsubscribe|mailto:|tel:|javascript:|#$)", re.I)
SOCIAL_HOSTS = re.compile(
    r"(facebook|instagram|tiktok|twitter|x\.com|linkedin|youtube|youtu\.be|"
    r"pinterest|threads\.net|reddit|snapchat|t\.me|discord)", re.I)
LINK_IN_BIO = re.compile(r"(linktr\.ee|beacons\.ai|stan\.store|lnk\.bio|"
                         r"bio\.link|komi\.io|hoo\.be|campsite\.bio|tap\.bio)", re.I)
YTDLP_HOSTS = re.compile(r"(youtube\.com|youtu\.be|tiktok\.com|instagram\.com|"
                         r"facebook\.com/.*/videos|fb\.watch|vimeo\.com|x\.com|"
                         r"twitter\.com|loom\.com)", re.I)


# ---------------------------------------------------------------- utilities

def now():
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_ts(s):
    if s is None:
        return None
    s = s.strip().replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.astimezone()  # treat naive input as local time
    return t.astimezone(dt.timezone.utc)


def human_delta(seconds):
    if seconds is None:
        return "-"
    s = int(round(seconds))
    sign = "-" if s < 0 else ""
    s = abs(s)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = [f"{d}d" if d else "", f"{h}h" if h else "", f"{m}m" if m else "",
             f"{s}s" if (s or not (d or h or m)) else ""]
    return sign + " ".join(p for p in parts if p)


def slugify(text, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].strip("-") or "funnel"


def norm_url(u):
    """Normalize for de-duplication: drop fragment and tracking params."""
    p = urllib.parse.urlsplit(u)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not TRACKING_PARAMS.match(k)]
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path,
                                    urllib.parse.urlencode(sorted(q)), ""))


def tracking_params(u):
    p = urllib.parse.urlsplit(u)
    return {k: v for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
            if TRACKING_PARAMS.match(k)}


def host(u):
    return urllib.parse.urlsplit(u).netloc.lower().removeprefix("www.")


def uniq_ci(items, n):
    seen, out = set(), []
    for x in items:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out[:n]


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- run state

class Run:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.funnel_path = os.path.join(self.path, "funnel.json")
        self.events_path = os.path.join(self.path, "events.jsonl")
        self.assets = os.path.join(self.path, "assets")
        if not os.path.exists(self.funnel_path):
            die(f"not a run folder (no funnel.json): {self.path}")
        with open(self.funnel_path) as f:
            self.f = json.load(f)

    def save(self):
        tmp = self.funnel_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.f, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.funnel_path)

    def events(self):
        out = []
        if os.path.exists(self.events_path):
            with open(self.events_path) as f:
                for line in f:
                    if line.strip():
                        out.append(json.loads(line))
        return out

    def start(self):
        return parse_ts(self.f["created_at"])

    def event(self, kind, summary, at=None, node=None, edge=None, data=None):
        """Append-only. `at` is when it happened; logged_at is when we wrote it."""
        evs = self.events()
        logged = now()
        t = at or logged
        if (t - logged).total_seconds() > 300:
            die(f"event time {iso(t)} is in the future; log things when they happen")
        ev = {
            "seq": len(evs) + 1,
            "ts": iso(t),
            "elapsed_s": round((t - self.start()).total_seconds(), 1),
            "kind": kind,
            "summary": summary,
            "node": node,
            "edge": edge,
            "logged_at": iso(logged),
        }
        if evs and parse_ts(evs[-1]["ts"]) > t:
            ev["logged_late"] = True  # happened before the previous event
        if data:
            ev["data"] = data
        with open(self.events_path, "a") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    def node(self, nid):
        for n in self.f["nodes"]:
            if n["id"] == nid:
                return n
        die(f"no node {nid}")

    def next_id(self, prefix, items):
        return f"{prefix}{len(items) + 1}"

    def last_node_time(self):
        ts = [parse_ts(n["captured_at"]) for n in self.f["nodes"] if n.get("captured_at")]
        return max(ts) if ts else None

    def add_node(self, node):
        node["id"] = self.next_id("n", self.f["nodes"])
        t = parse_ts(node["captured_at"])
        parent = self.node(node["parent"]) if node.get("parent") else None
        ref = parse_ts(parent["captured_at"]) if parent else self.last_node_time()
        node["since_prev_s"] = round((t - ref).total_seconds(), 1) if ref else None
        node["since_start_s"] = round((t - self.start()).total_seconds(), 1)
        node["depth"] = (parent["depth"] + 1) if parent else 0
        self.f["nodes"].append(node)
        return node

    def add_edge(self, frm, to, trigger, cta=None, channel="web", path="taken",
                 delay_s=None):
        e = {"id": self.next_id("e", self.f["edges"]), "from": frm, "to": to,
             "trigger": trigger, "cta": cta, "channel": channel, "path": path,
             "delay_s": delay_s}
        if delay_s is None and frm:
            a, b = self.node(frm), self.node(to)
            e["delay_s"] = round((parse_ts(b["captured_at"]) -
                                  parse_ts(a["captured_at"])).total_seconds(), 1)
        self.f["edges"].append(e)
        return e

    def seen_urls(self):
        s = set()
        for n in self.f["nodes"]:
            for k in ("url", "final_url"):
                if n.get(k):
                    s.add(norm_url(n[k]))
        return s

    def update_coverage(self):
        b = self.f["branches"]
        nodes = self.f["nodes"]
        cov = {
            "nodes_total": len(nodes),
            "nodes_taken_path": sum(1 for n in nodes if n.get("path") == "taken"),
            "nodes_branch": sum(1 for n in nodes if n.get("path") == "branch"),
            "max_depth": max((n.get("depth", 0) for n in nodes), default=0),
            "frontier_open": sum(1 for x in b["frontier"] if x["status"] == "open"),
            "frontier_explored": sum(1 for x in b["frontier"] if x["status"] == "explored"),
            "frontier_skipped": sum(1 for x in b["frontier"] if x["status"] == "skipped"),
            "frontier_gated": sum(1 for x in b["frontier"] if x["status"] == "gated"),
        }
        found = len(b["frontier"])
        cov["coverage_pct"] = round(100.0 * (found - cov["frontier_open"]) / found, 1) if found else 100.0
        self.f["coverage"] = cov


def resolve_run(arg):
    if os.path.isdir(arg):
        return Run(arg)
    root = os.environ.get("FH_RUNS_DIR", os.path.join(os.getcwd(), "runs"))
    cand = os.path.join(root, arg)
    if os.path.isdir(cand):
        return Run(cand)
    die(f"run not found: {arg} (looked in {root})")


# ---------------------------------------------------------------- browser

def chromium_path():
    pats = [
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/*.app/Contents/MacOS/*",
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome",
    ]
    for pat in pats:
        hits = sorted(glob.glob(os.path.expanduser(pat)))
        if hits:
            return hits[-1]
    return None


def launch(p):
    try:
        return p.chromium.launch()
    except Exception:
        exe = chromium_path()
        if not exe:
            raise
        return p.chromium.launch(executable_path=exe)


EXTRACT_JS = r"""
() => {
  const vh = window.innerHeight;
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const txt = el => (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim();
  const place = el => { const r = el.getBoundingClientRect(); const y = r.top + window.scrollY;
    const inNav = !!el.closest('nav,header'); const inFoot = !!el.closest('footer');
    return {y: Math.round(y), above_fold: y < vh, region: inNav ? 'header' : inFoot ? 'footer' :
      (y < vh ? 'hero' : (y > document.body.scrollHeight - vh ? 'bottom' : 'body')),
      in_modal: !!el.closest('[class*=modal],[class*=popup],[id*=modal],[id*=popup],[class*=exit],[role=dialog]')}; };
  const ctas = [];
  document.querySelectorAll('a[href],button,input[type=submit],input[type=button],[role=button]').forEach(el => {
    const t = txt(el); if (!t && el.tagName !== 'A') return;
    const href = el.href || el.getAttribute('data-href') || (el.form ? el.form.action : null) || null;
    const cls = (el.className && el.className.baseVal === undefined ? el.className : '') + '';
    const isButton = el.tagName !== 'A' || /btn|button|cta/i.test(cls);
    ctas.push({text: t.slice(0,160), target: href, tag: el.tagName.toLowerCase(),
      is_button: isButton, visible: vis(el), submits_form: !!(el.form && (el.type === 'submit' || el.tagName === 'BUTTON')),
      ...place(el)});
  });
  const forms = [...document.querySelectorAll('form')].map(f => ({
    action: f.action || null, method: (f.method || 'get').toLowerCase(), visible: vis(f), ...place(f),
    fields: [...f.querySelectorAll('input,select,textarea')].filter(i => i.type !== 'hidden').map(i => ({
      type: i.type || i.tagName.toLowerCase(), name: i.name || null,
      label: (i.labels && i.labels[0] ? txt(i.labels[0]) : '') || i.placeholder || i.getAttribute('aria-label') || null,
      autocomplete: i.autocomplete || null})),
    hidden_fields: [...f.querySelectorAll('input[type=hidden]')].map(i => i.name).filter(Boolean)
  }));
  const loose_inputs = [...document.querySelectorAll('input')].filter(i => !i.form && i.type !== 'hidden' && vis(i))
    .map(i => ({type: i.type, name: i.name || null, placeholder: i.placeholder || null}));
  const hs = sel => [...document.querySelectorAll(sel)].filter(vis).map(txt).filter(Boolean).slice(0, 20);
  const meta = n => { const m = document.querySelector(`meta[name="${n}"],meta[property="${n}"]`); return m ? m.content : null; };
  const iframes = [...document.querySelectorAll('iframe')].map(f => f.src).filter(Boolean);
  const videos = [...document.querySelectorAll('video')].map(v => v.currentSrc || v.src || (v.querySelector('source')||{}).src).filter(Boolean);
  const images = [...document.querySelectorAll('img')].filter(vis).map(i => ({src: i.currentSrc || i.src, alt: i.alt || null,
    w: i.naturalWidth, h: i.naturalHeight})).filter(i => i.w >= 120 || i.h >= 120).slice(0, 40);
  const timers = [...document.querySelectorAll('[class*=countdown],[id*=countdown],[class*=timer],[id*=timer]')].filter(vis).map(txt).slice(0, 5);
  const modals = [...document.querySelectorAll('[class*=modal],[class*=popup],[id*=modal],[id*=popup],[class*=exit-intent],[role=dialog]')]
    .map(m => ({visible: vis(m), text: txt(m).slice(0, 300), has_form: !!m.querySelector('form,input')})).filter(m => m.text).slice(0, 10);
  return {
    title: document.title, lang: document.documentElement.lang || null,
    meta_description: meta('description'), og_title: meta('og:title'), og_description: meta('og:description'),
    og_image: meta('og:image'), canonical: (document.querySelector('link[rel=canonical]')||{}).href || null,
    h1: hs('h1'), h2: hs('h2'), h3: hs('h3').slice(0, 12),
    text: document.body ? document.body.innerText : '',
    ctas, forms, loose_inputs, iframes, videos, images, timers, modals,
    page_height: document.body ? document.body.scrollHeight : 0,
  };
}
"""


_ROBOTS = {}


def _robots_rules(origin):
    """Fetch robots.txt with a normal UA (urllib's default UA is often 403'd,
    which the stdlib parser treats as disallow-all) and return the rules that
    apply to us: all `*` groups plus any group naming funnel-research."""
    if origin in _ROBOTS:
        return _ROBOTS[origin]
    import urllib.request
    req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(500000).decode("utf-8", "replace")
    except Exception as e:
        code = getattr(e, "code", None)
        # 4xx (other than 401/403) means no robots.txt: everything allowed.
        rules = None if code in (401, 403) else []
        _ROBOTS[origin] = rules
        return rules
    rules, agents, in_rules = [], [], False
    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(v.lower())
        elif k in ("allow", "disallow"):
            in_rules = True
            if v and any(a == "*" or "funnel-research" in a for a in agents):
                rules.append((k == "allow", v))
    _ROBOTS[origin] = rules
    return rules


def robots_allowed(url):
    p = urllib.parse.urlsplit(url)
    rules = _robots_rules(f"{p.scheme}://{p.netloc}")
    if rules is None:
        return False, "robots.txt access denied (401/403); treat as disallowed"
    target = (p.path or "/") + (f"?{p.query}" if p.query else "")
    best = None  # longest matching rule wins; allow wins ties
    for allow, pat in rules:
        rx = "^" + re.escape(pat).replace(r"\*", ".*")
        if rx.endswith(r"\$"):
            rx = rx[:-2] + "$"
        if re.match(rx, target):
            if best is None or len(pat) > len(best[1]) or (len(pat) == len(best[1]) and allow):
                best = (allow, pat)
    if best is None or best[0]:
        return True, "allowed"
    return False, f"disallowed by robots.txt rule '{best[1]}'"


def ytdlp_info(url, out_json):
    if not shutil.which("yt-dlp"):
        return None
    try:
        r = subprocess.run(["yt-dlp", "-J", "--skip-download", "--no-warnings", url],
                           capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    info = json.loads(r.stdout)
    keep = {k: info.get(k) for k in (
        "id", "title", "description", "uploader", "uploader_id", "uploader_url",
        "channel", "channel_url", "channel_follower_count", "upload_date",
        "timestamp", "duration", "view_count", "like_count", "comment_count",
        "tags", "categories", "webpage_url", "thumbnail", "chapters")}
    with open(out_json, "w") as f:
        json.dump(keep, f, indent=2, ensure_ascii=False)
    return keep


def detect_gates(x, url):
    gates = []
    login = re.search(r"(log ?in|sign ?in)\b", x["title"] + " " + " ".join(x["h1"]), re.I)
    for fm in x["forms"]:
        types = {(fl["type"] or "").lower() for fl in fm["fields"]}
        names = " ".join(f"{fl.get('name') or ''} {fl.get('label') or ''} "
                         f"{fl.get('autocomplete') or ''}" for fl in fm["fields"]).lower()
        if "password" in types:
            gates.append({"kind": "login", "detail": "password field"})
        if re.search(r"card|cc-number|cvc|cvv|expir", names):
            gates.append({"kind": "payment", "detail": "card fields"})
        if "email" in types or "email" in names:
            gates.append({"kind": "email", "detail": f"form -> {fm['action']}"})
        if "tel" in types or re.search(r"phone|mobile|sms", names):
            gates.append({"kind": "phone", "detail": f"form -> {fm['action']}"})
    if any(i["type"] == "email" for i in x["loose_inputs"]):
        gates.append({"kind": "email", "detail": "email input outside a form"})
    if any(re.search(r"stripe|paypal|checkout|braintree|recurly|chargebee", f or "", re.I)
           for f in x["iframes"]):
        gates.append({"kind": "payment", "detail": "payment iframe"})
    if login and not gates:
        gates.append({"kind": "login", "detail": "login page title"})
    # de-duplicate by kind
    seen, out = set(), []
    for g in gates:
        if g["kind"] not in seen:
            seen.add(g["kind"])
            out.append(g)
    return out


def classify(x, url, given):
    if given:
        return given
    h = host(url)
    blob = " ".join([x["title"], " ".join(x["h1"]), " ".join(x["h2"][:5])]).lower()
    text = x["text"][:20000]
    if LINK_IN_BIO.search(h):
        return "link-in-bio"
    if re.search(r"youtube|youtu\.be|tiktok|instagram|facebook|x\.com|twitter|linkedin", h):
        return "post"
    if BUY_WORDS.search(text) and any(g["kind"] == "payment" for g in detect_gates(x, url)):
        return "checkout"
    if re.search(r"thank you|you'?re in|check your (inbox|email)|confirm(ed)? your", blob):
        return "thank-you"
    if re.search(r"webinar|masterclass|live (training|workshop)|register", blob):
        return "webinar"
    paid = [m.group(0) for m in PRICE.finditer(text)
            if not re.match(r"(free|[$€£]\s?0(\.00)?$)", m.group(0), re.I)]
    buy_cta = any(re.search(r"(enroll|buy|order|purchase|join now|get (instant )?access|"
                            r"start (my|your) (trial|membership)|subscribe now|add to cart)",
                            c["text"], re.I) for c in x["ctas"] if c["visible"])
    if paid and buy_cta:
        return "sales-page"
    if any(g["kind"] in ("email", "phone") for g in detect_gates(x, url)):
        return "opt-in"
    if PRICE.search(text) and re.search(r"enroll|join|buy|get (started|access)|order", text, re.I):
        return "sales-page"
    return "landing"


def summarize_ctas(x, page_url):
    out, seen = [], set()
    for c in x["ctas"]:
        if not c["visible"]:
            continue
        tgt = c["target"]
        if tgt:
            tgt = urllib.parse.urljoin(page_url, tgt)
        key = (c["text"].lower(), norm_url(tgt) if tgt and tgt.startswith("http") else tgt)
        if key in seen:
            continue
        seen.add(key)
        kind = "button" if c["is_button"] else "link"
        if NO_THANKS.search(c["text"]):
            kind = "no-thanks"
        elif c["submits_form"]:
            kind = "form-submit"
        elif c["region"] in ("header", "footer") and not c["is_button"]:
            kind = "nav"
        out.append({"text": c["text"], "target": tgt, "kind": kind,
                    "placement": {"region": c["region"], "above_fold": c["above_fold"],
                                  "y": c["y"], "in_modal": c["in_modal"]}})
    return out


def desc_ctas(body):
    """Links in a caption, description, email or SMS, labelled by their line."""
    out = []
    for i, line in enumerate(body.splitlines()):
        for u in re.findall(r"https?://[^\s\"'<>)\]]+", line):
            label = re.sub(r"https?://\S+", "", line).strip(" :-\u2192>|")
            out.append({"text": label or u, "target": u.rstrip(".,;"), "kind": "link",
                        "placement": {"region": "description", "line": i + 1}})
    return out


OFFER_WORDS = re.compile(r"(free|get |join|course|academy|program|download|guide|"
                         r"prompts|template|newsletter|checklist|webinar|masterclass|"
                         r"workshop|book|challenge|trial|apply|community|cohort|"
                         r"coaching|system|toolkit|cheat ?sheet|playbook|ebook|my )",
                         re.I)


def branch_priority(run, c, page_url):
    """Higher = more likely to be this creator's own funnel rather than a mention."""
    t, score, why = c["target"], 0, []
    if OFFER_WORDS.search(c["text"]):
        score += 3; why.append("offer words")
    if tracking_params(t) or re.match(r"^(go|link|links|l|get|try|join)\.", host(t)) \
            or re.search(r"/(yt|ytd|ig|tt|bio)\b", t, re.I):
        score += 2; why.append("tracked/short link")
    brand = set()
    for n in run.f["nodes"]:
        s = n.get("social") or {}
        for k in ("uploader_id", "channel", "uploader"):
            if s.get(k):
                brand |= {w for w in re.split(r"[^a-z0-9]+", s[k].lower()) if len(w) > 3}
        brand.add(host(n.get("final_url") or "").split(".")[-2] if n.get("final_url") and "." in host(n["final_url"]) else "")
    brand.discard(""); brand -= {"youtube", "tiktok", "instagram", "facebook", "twitter", "linkedin"}
    joined = re.sub(r"[^a-z0-9]", "", host(t) + urllib.parse.urlsplit(t).path.lower())
    if any(b and b in joined for b in brand):
        score += 3; why.append("creator-owned")
    if re.search(r"(geni\.us|amzn\.|amazon\.|ref\.|/ref/|affiliate)", t, re.I):
        score -= 2; why.append("affiliate/third-party")
    return score, ", ".join(why)


def frontier_candidates(run, node, ctas, page_url):
    """Alternate paths worth exploring as branches (GET links only)."""
    seen = run.seen_urls() | {norm_url(x["target"]) for x in run.f["branches"]["frontier"]}
    out = []
    page_host = host(page_url)
    for c in ctas:
        t = c["target"]
        if not t or not t.startswith("http") or c["kind"] == "form-submit":
            continue
        reason = None
        if c["kind"] == "no-thanks":
            reason = "no-thanks / decline path"
        elif c["kind"] == "button":
            reason = "button CTA"
        elif node["type"] in ("link-in-bio", "post", "video", "profile", "email", "sms", "dm"):
            reason = f"link on {node['type']}"
        elif re.search(r"(pricing|plans?|offer|enroll|join|apply|book|call|webinar|"
                       r"free|download|guide|course|program|start|trial|get )",
                       c["text"], re.I) and c["kind"] != "nav":
            reason = "offer-like link"
        if not reason:
            continue
        if SKIP_LINK.search(t) or SKIP_LINK.search(c["text"]):
            continue
        if SOCIAL_HOSTS.search(host(t)) and node["type"] not in ("link-in-bio",):
            continue  # social profiles are usually not the funnel path
        if host(t) == page_host and norm_url(t) == norm_url(page_url):
            continue
        k = norm_url(t)
        if k in seen:
            continue
        seen.add(k)
        pri, why = branch_priority(run, c, page_url)
        out.append({"from": node["id"], "cta": c["text"], "target": t,
                    "reason": reason + (f"; {why}" if why else ""), "priority": pri,
                    "status": "open", "depth": node["depth"] + 1})
    return out


def capture(run, url, ntype=None, platform=None, parent=None, cta=None,
            trigger="click", channel="web", path="taken", mobile=True,
            record=False, wait_ms=2500, ignore_robots=False, note=None):
    if run.f["status"] == "complete":
        die("run is complete (end confirmed). Use `reopen` first if the funnel continues.")
    ok, why = robots_allowed(url)
    if not ok and not ignore_robots:
        run.event("blocked", f"robots.txt disallows {url}; not captured",
                  data={"url": url})
        die(f"{why}: {url}. Not captured. Ask the user to view it and paste/screenshot instead.", 3)

    last = run.f.get("last_fetch_at")
    if last:
        gap = (now() - parse_ts(last)).total_seconds()
        if gap < MIN_GAP_S:
            time.sleep(MIN_GAP_S - gap)

    from playwright.sync_api import sync_playwright  # lazy: other commands need no browser

    nid_guess = f"n{len(run.f['nodes']) + 1}"
    adir = os.path.join(run.assets, nid_guess)
    os.makedirs(adir, exist_ok=True)
    requests = []
    t_click = now()
    with sync_playwright() as p:
        browser = launch(p)
        ctx_kw = {"user_agent": UA, "viewport": {"width": 1366, "height": 900}}
        if record:
            ctx_kw["record_video_dir"] = adir
            ctx_kw["record_video_size"] = {"width": 1366, "height": 900}
        ctx = browser.new_context(**ctx_kw)
        page = ctx.new_page()
        page.on("request", lambda r: requests.append(r.url))
        resp = page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(wait_ms)
        # scroll to trigger lazy content (and give the recording something to show)
        h = page.evaluate("document.body ? document.body.scrollHeight : 0") or 0
        for y in range(0, int(h), 700):
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(250 if record else 80)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        t_loaded = now()
        final_url = page.url
        robots_final = robots_allowed(final_url)
        status = resp.status if resp else None
        redirects = []
        if resp:
            r = resp.request.redirected_from
            while r:
                redirects.insert(0, r.url)
                r = r.redirected_from
        x = page.evaluate(EXTRACT_JS)
        full_h = page.evaluate("document.documentElement.scrollHeight") or 900
        page.screenshot(path=os.path.join(adir, "desktop-full.png"), full_page=True,
                        clip={"x": 0, "y": 0, "width": 1366, "height": min(full_h, MAX_SHOT_H)})
        page.screenshot(path=os.path.join(adir, "desktop-fold.png"), full_page=False)
        with open(os.path.join(adir, "page.html"), "w") as f:
            f.write(page.content())
        video_path = page.video.path() if record and page.video else None
        ctx.close()
        if mobile:
            mctx = browser.new_context(**p.devices["iPhone 13"])
            mp = mctx.new_page()
            try:
                mp.goto(final_url, wait_until="domcontentloaded", timeout=60000)
                try:
                    mp.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                mp.wait_for_timeout(1500)
                mh = mp.evaluate("document.documentElement.scrollHeight") or 844
                mp.screenshot(path=os.path.join(adir, "mobile-full.png"), full_page=True,
                              clip={"x": 0, "y": 0, "width": 390,
                                    "height": min(mh, MAX_SHOT_H // 2)})
            except Exception as e:
                print(f"warn: mobile capture failed: {e}", file=sys.stderr)
            mctx.close()
        browser.close()
    run.f["last_fetch_at"] = iso(now())

    with open(os.path.join(adir, "page.txt"), "w") as f:
        f.write(x["text"])
    if video_path and os.path.exists(video_path):
        os.replace(video_path, os.path.join(adir, "recording.webm"))
        video_path = os.path.join(adir, "recording.webm")

    social = None
    if YTDLP_HOSTS.search(final_url):
        social = ytdlp_info(final_url, os.path.join(adir, "social-meta.json"))

    pixels = sorted({name for name, pat in PIXELS.items()
                     for u in requests if re.search(pat, u, re.I)})
    ctas = summarize_ctas(x, final_url)
    gates = detect_gates(x, final_url)
    ntype = classify(x, final_url, ntype)
    text = x["text"]
    if social and social.get("description"):
        # On social platforms the DOM buttons are player/app chrome; the funnel
        # CTAs are the links in the caption/description.
        text = (social.get("title") or "") + "\n\n" + social["description"]
        ctas = desc_ctas(social["description"])
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    prices = sorted(set(m.group(0).strip() for m in PRICE.finditer(text)))[:30]
    node = {
        "type": ntype,
        "platform": platform or host(final_url),
        "url": url,
        "final_url": final_url,
        "redirect_chain": redirects,
        "robots": robots_final[1],
        "http_status": status,
        "captured_at": iso(t_loaded),
        "load_s": round((t_loaded - t_click).total_seconds(), 1),
        "path": path,
        "parent": parent,
        "title": (social or {}).get("title") or x["title"],
        "hook": None,  # agent fills: first line / first 3 seconds / headline promise
        "headline": (x["h1"] or x["h2"] or [None])[0],
        "subheadlines": x["h2"][:10],
        "copy": {"text_file": f"assets/{nid_guess}/page.txt",
                 "word_count": len(text.split()),
                 "opening": lines[:8]},
        "meta": {k: x[k] for k in ("meta_description", "og_title", "og_description",
                                   "og_image", "canonical", "lang")},
        "ctas": ctas,
        "forms": x["forms"],
        "offers": [],  # agent fills: {name, price, anchor_price, bonuses, guarantee}
        "prices_seen": prices,
        "proof": uniq_ci((m.group(0) for m in PROOF.finditer(text)), 25),
        "urgency": uniq_ci([m.group(0) for m in URGENCY.finditer(text)] + x["timers"], 20),
        "popups": x["modals"],
        "tracking": {"params": tracking_params(url) | tracking_params(final_url),
                     "pixels": pixels, "third_party_hosts":
                     sorted({host(u) for u in requests if host(u) and host(u) != host(final_url)})[:80]},
        "media": {"iframes": x["iframes"], "videos": x["videos"], "images": x["images"][:20]},
        "gates": gates,
        "social": social,
        "assets": {k: f"assets/{nid_guess}/{v}" for k, v in (
            ("screenshot", "desktop-full.png"), ("screenshot_fold", "desktop-fold.png"),
            ("screenshot_mobile", "mobile-full.png"), ("html", "page.html"),
            ("text", "page.txt")) if os.path.exists(os.path.join(adir, v))},
        "notes": note,
    }
    if video_path:
        node["assets"]["recording"] = f"assets/{nid_guess}/recording.webm"
    if social:
        node["assets"]["social_meta"] = f"assets/{nid_guess}/social-meta.json"
    node = run.add_node(node)
    assert node["id"] == nid_guess

    edge = None
    if parent:
        if cta:
            run.event("click", f"{'[branch] ' if path == 'branch' else ''}clicked \"{cta}\" on {parent}",
                      at=t_click, node=parent, data={"target": url})
        edge = run.add_edge(parent, node["id"], trigger, cta=cta, channel=channel, path=path)
    run.event("page_view", f"{'[branch] ' if path == 'branch' else ''}{ntype}: {node['title'] or final_url}",
              at=t_loaded, node=node["id"], edge=edge["id"] if edge else None,
              data={"url": final_url, "path": path})

    if not robots_final[0]:
        print(f"warn: redirect landed on a robots-disallowed URL ({robots_final[1]}). "
              "Captured once; do not crawl further on this host.", file=sys.stderr)
    for g in gates:
        run.event("gate", f"{g['kind']} gate on {node['id']} ({g['detail']}); agent stops, user decides",
                  node=node["id"], data=g)
    new = frontier_candidates(run, node, ctas, final_url)
    run.f["branches"]["frontier"].extend(new)
    # mark the frontier entry this capture satisfied
    for fr in run.f["branches"]["frontier"]:
        if fr["status"] == "open" and norm_url(fr["target"]) in (norm_url(url), norm_url(final_url)):
            fr["status"] = "explored" if path == "branch" else "taken"
            fr["node"] = node["id"]

    looks_buy = ntype in BUY_TYPES or any(g["kind"] == "payment" for g in gates) \
        or bool(BUY_WORDS.search(text[:20000]) and prices)
    if looks_buy:
        node["buy_page_candidate"] = True
        if path == "taken":
            run.f["status"] = "awaiting_end_confirmation"
            run.f["end"] = {"candidate_node": node["id"], "asked_at": iso(now())}
            run.event("end_check", f"{node['id']} looks like the buy/peak-offer page; "
                      "asking the user: Is this the end of the funnel?", node=node["id"])
    run.update_coverage()
    run.save()
    render_timeline(run)
    return node, gates, new, looks_buy


# ---------------------------------------------------------------- timeline

def render_timeline(run):
    f = run.f
    evs = sorted(run.events(), key=lambda e: (e["ts"], e["seq"]))
    nodes = {n["id"]: n for n in f["nodes"]}
    out = [f"# Funnel timeline: {f['title']}", "",
           f"- Run: `{f['run_id']}`",
           f"- Started: {f['created_at']}",
           f"- TOF input: {f['tof']['input']}" + (f" ({f['tof']['platform']})" if f['tof'].get('platform') else ""),
           f"- Status: **{f['status']}**",
           f"- Nodes: {len(f['nodes'])} ({f['coverage'].get('nodes_taken_path', 0)} on the taken path, "
           f"{f['coverage'].get('nodes_branch', 0)} explored branches), edges: {len(f['edges'])}",
           f"- Branch coverage: {f['coverage'].get('coverage_pct', 0)}% "
           f"({f['coverage'].get('frontier_open', 0)} open)",
           "", "Generated from `events.jsonl` (sorted by when each event happened). Do not edit by hand; "
           "run `fh.py timeline <run>`.", "",
           "| # | Time (UTC) | Elapsed | Event | Node | What happened |",
           "|---|---|---|---|---|---|"]
    prev = None
    for e in evs:
        t = parse_ts(e["ts"])
        gap = f" (+{human_delta((t - prev).total_seconds())})" if prev else ""
        prev = t
        late = " (logged late)" if e.get("logged_late") else ""
        out.append(f"| {e['seq']} | {e['ts']}{gap} | {human_delta(e['elapsed_s'])} | {e['kind']} | "
                   f"{e.get('node') or ''} | {e['summary'].replace('|', '/')}{late} |")
    out += ["", "## Stages (taken path first)", ""]
    for n in sorted(f["nodes"], key=lambda n: (n.get("path") != "taken", n["captured_at"])):
        tag = "TAKEN" if n.get("path") == "taken" else "branch"
        out.append(f"### {n['id']} [{tag}] {n['type']} on {n['platform']} (depth {n.get('depth', 0)})")
        out.append("")
        if n.get("final_url"):
            out.append(f"- URL: {n['final_url']}")
        out.append(f"- Captured: {n['captured_at']} (since previous: {human_delta(n.get('since_prev_s'))}, "
                   f"since start: {human_delta(n.get('since_start_s'))})")
        for k in ("title", "hook", "headline"):
            if n.get(k):
                out.append(f"- {k.title()}: {n[k]}")
        ctas = [c for c in n.get("ctas", []) if c["kind"] in ("button", "no-thanks", "form-submit")][:8]
        if ctas:
            out.append("- Main CTAs: " + "; ".join(
                f"\"{c['text'][:60]}\" ({c['kind']}, {c['placement'].get('region')})" for c in ctas))
        if n.get("offers"):
            out.append("- Offers: " + "; ".join(json.dumps(o, ensure_ascii=False) for o in n["offers"]))
        elif n.get("prices_seen"):
            out.append("- Prices seen: " + ", ".join(n["prices_seen"][:10]))
        if n.get("urgency"):
            out.append("- Urgency: " + ", ".join(n["urgency"][:6]))
        if n.get("proof"):
            out.append("- Proof: " + ", ".join(n["proof"][:8]))
        tr = n.get("tracking", {})
        if tr.get("pixels") or tr.get("params"):
            out.append(f"- Tracking: pixels {', '.join(tr.get('pixels') or []) or 'none'}; "
                       f"params {json.dumps(tr.get('params') or {})}")
        if n.get("gates"):
            out.append("- Gates: " + ", ".join(f"{g['kind']} ({g['detail']})" for g in n["gates"]))
        shots = [v for k, v in n.get("assets", {}).items() if v.endswith(".png")]
        if shots:
            out.append("- Screenshots: " + ", ".join(f"[{os.path.basename(s)}]({s})" for s in shots))
        out.append("")
    out += ["## Edges", "", "| Edge | From | To | Trigger | CTA | Channel | Delay | Path |",
            "|---|---|---|---|---|---|---|---|"]
    for e in f["edges"]:
        out.append(f"| {e['id']} | {e['from']} | {e['to']} | {e['trigger']} | "
                   f"{(e.get('cta') or '').replace('|', '/')[:60]} | {e['channel']} | "
                   f"{human_delta(e.get('delay_s'))} | {e['path']} |")
    openf = [x for x in f["branches"]["frontier"] if x["status"] == "open"]
    if openf:
        out += ["", "## Unexplored branches", ""]
        out += [f"- from {x['from']}: \"{x['cta'][:60]}\" -> {x['target']} ({x['reason']})" for x in openf]
    with open(os.path.join(run.path, "timeline.md"), "w") as fh:
        fh.write("\n".join(out) + "\n")


# ---------------------------------------------------------------- commands

def cmd_new(a):
    root = a.root or os.environ.get("FH_RUNS_DIR") or os.path.join(os.getcwd(), "runs")
    t = now()
    local_date = t.astimezone().strftime("%Y-%m-%d")
    slug = slugify(a.slug or a.tof)
    path = os.path.join(root, f"{local_date}-{slug}")
    if os.path.exists(path):
        die(f"run already exists: {path}")
    os.makedirs(os.path.join(path, "assets"))
    f = {
        "schema_version": SCHEMA_VERSION,
        "run_id": os.path.basename(path),
        "title": a.title or a.slug or a.tof,
        "created_at": iso(t),
        "tof": {"input": a.tof, "platform": a.platform, "notes": a.notes},
        "status": "active",
        "end": None,
        "identity": {"email": None, "phone": None, "chosen_by_user": False},
        "inbox": {"route": None, "address": None, "watch_senders": [], "check_until": None,
                  "last_checked_at": None},
        "nodes": [], "edges": [],
        "branches": {"frontier": [], "max_depth": a.max_depth},
        "coverage": {},
    }
    with open(os.path.join(path, "funnel.json"), "w") as fh:
        json.dump(f, fh, indent=2)
    run = Run(path)
    run.event("run_start", f"run started from TOF: {a.tof}", at=parse_ts(iso(t)),
              data={"platform": a.platform, "notes": a.notes})
    run.update_coverage()
    run.save()
    render_timeline(run)
    print(path)


def print_capture(node, gates, new, looks_buy):
    print(json.dumps({
        "node": node["id"], "type": node["type"], "title": node["title"],
        "final_url": node["final_url"], "path": node["path"],
        "screenshots": [v for v in node["assets"].values() if v.endswith(".png")],
        "pixels": node["tracking"]["pixels"],
        "main_ctas": [c["text"][:70] for c in node["ctas"]
                      if c["kind"] in ("button", "no-thanks", "form-submit")][:10],
        "gates": gates,
        "new_branches": [f"{x['cta'][:50]} -> {x['target']}" for x in new],
    }, indent=2, ensure_ascii=False))
    if gates:
        print("\nGATE: " + ", ".join(g["kind"] for g in gates) +
              ". Stop here. Ask the user how to proceed (see references/gates.md). "
              "Do not fill or submit anything.")
    if looks_buy and node["path"] == "taken":
        print("\nASK THE USER: \"Is this the end of the funnel?\" "
              "Then run `fh.py end <run> --node " + node["id"] + " --answer yes|no`.")


def cmd_capture(a):
    run = resolve_run(a.run)
    if a.type and a.type not in NODE_TYPES:
        die(f"--type must be one of: {', '.join(NODE_TYPES)}")
    res = capture(run, a.url, ntype=a.type, platform=a.platform, parent=a.parent,
                  cta=a.cta, trigger=a.trigger, channel=a.channel,
                  path="branch" if a.branch else "taken", mobile=not a.no_mobile,
                  record=a.record, wait_ms=a.wait_ms, ignore_robots=False, note=a.note)
    print_capture(*res)


def cmd_explore(a):
    run = resolve_run(a.run)
    max_depth = a.max_depth or run.f["branches"].get("max_depth") or 3
    done = 0
    while done < a.max_pages:
        openf = [x for x in run.f["branches"]["frontier"] if x["status"] == "open"]
        if a.from_node:
            openf = [x for x in openf if x["from"] == a.from_node]
        if not openf:
            break
        fr = sorted(openf, key=lambda x: (x["depth"], -x.get("priority", 0)))[0]
        if fr.get("priority", 0) < a.min_priority:
            for x in openf:
                if x.get("priority", 0) < a.min_priority:
                    x["status"] = "skipped"
                    x["skip_reason"] = f"priority {x.get('priority', 0)} < {a.min_priority}"
            run.event("branch_skipped", f"skipped low-priority links (likely mentions, not funnel)",
                      data={"min_priority": a.min_priority})
            run.save()
            continue
        if fr["depth"] > max_depth:
            fr["status"] = "skipped"
            fr["skip_reason"] = f"beyond max depth {max_depth}"
            run.event("branch_skipped", f"skipped {fr['target']} (depth {fr['depth']} > {max_depth})",
                      node=fr["from"])
            run.save()
            continue
        if a.same_site and host(fr["target"]).split(".")[-2:] != \
                host(run.node(fr["from"])["final_url"]).split(".")[-2:]:
            fr["status"] = "skipped"
            fr["skip_reason"] = "off-site (--same-site)"
            run.save()
            continue
        ok, why = robots_allowed(fr["target"])
        if not ok:
            fr["status"] = "skipped"
            fr["skip_reason"] = why
            run.event("branch_skipped", f"skipped {fr['target']} ({why})", node=fr["from"])
            run.save()
            continue
        try:
            node, gates, new, looks_buy = capture(
                run, fr["target"], parent=fr["from"], cta=fr["cta"], trigger="click",
                path="branch", mobile=not a.no_mobile)
        except SystemExit:
            raise
        except Exception as e:
            run = resolve_run(run.path)
            for x in run.f["branches"]["frontier"]:
                if x["target"] == fr["target"] and x["status"] == "open":
                    x["status"] = "skipped"
                    x["skip_reason"] = f"capture failed: {str(e)[:200]}"
            run.event("branch_skipped", f"capture failed for {fr['target']}", node=fr["from"])
            run.save()
            continue
        run = resolve_run(run.path)
        if gates:
            # explored up to the gate; children behind a gate are never followed
            for x in run.f["branches"]["frontier"]:
                if x["from"] == node["id"] and x["status"] == "open" and \
                        re.search(r"(submit|sign ?up|register|subscribe|buy|order|pay|join)",
                                  x["cta"], re.I):
                    x["status"] = "gated"
            run.save()
        done += 1
        print(f"explored {node['id']} {node['type']} {node['final_url']}"
              + (f"  GATE: {','.join(g['kind'] for g in gates)}" if gates else "")
              + ("  (buy-page candidate)" if looks_buy else ""))
    run.update_coverage()
    run.save()
    render_timeline(run)
    print(json.dumps(run.f["coverage"], indent=2))


def cmd_add_node(a):
    """Manual stage: email/SMS/DM/retargeting ad/webinar etc. seen outside the browser."""
    run = resolve_run(a.run)
    if a.type not in NODE_TYPES:
        die(f"--type must be one of: {', '.join(NODE_TYPES)}")
    at = parse_ts(a.at) if a.at else now()
    nid = f"n{len(run.f['nodes']) + 1}"
    adir = os.path.join(run.assets, nid)
    os.makedirs(adir, exist_ok=True)
    body, meta = "", {}
    if a.eml:
        with open(a.eml, "rb") as fh:
            msg = email.message_from_binary_file(fh, policy=email.policy.default)
        shutil.copy(a.eml, os.path.join(adir, "message.eml"))
        meta = {"from": str(msg["from"] or ""), "subject": str(msg["subject"] or ""),
                "date": str(msg["date"] or "")}
        if msg["date"] and not a.at:
            at = email.utils.parsedate_to_datetime(str(msg["date"])).astimezone(dt.timezone.utc)
        part = msg.get_body(preferencelist=("plain", "html"))
        body = part.get_content() if part else ""
        if part and part.get_content_type() == "text/html":
            with open(os.path.join(adir, "message.html"), "w") as fh:
                fh.write(body)
            body = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(
                r"(?is)<(script|style).*?</\1>", " ", body)))
            body = re.sub(r"[ \t]+", " ", body)
    elif a.body_file:
        with open(a.body_file) as fh:
            body = fh.read()
    if a.screenshot:
        for i, s in enumerate(a.screenshot, 1):
            shutil.copy(s, os.path.join(adir, f"screenshot-{i}{os.path.splitext(s)[1]}"))
    with open(os.path.join(adir, "message.txt"), "w") as fh:
        fh.write(body)
    links = sorted(set(re.findall(r"https?://[^\s\"'<>)\]]+", body)))
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    node = {
        "type": a.type, "platform": a.platform or a.channel, "url": a.url, "final_url": a.url,
        "captured_at": iso(at), "path": "branch" if a.branch else "taken", "parent": a.parent,
        "title": a.subject or meta.get("subject") or a.title,
        "hook": a.subject or meta.get("subject") or (lines[0] if lines else None),
        "headline": None, "subheadlines": [],
        "copy": {"text_file": f"assets/{nid}/message.txt", "word_count": len(body.split()),
                 "opening": lines[:8]},
        "message": {"channel": a.channel, "sender": a.sender or meta.get("from"),
                    "received_at": iso(at), **({"date_header": meta["date"]} if meta else {})},
        "ctas": desc_ctas(body),
        "forms": [], "offers": [],
        "prices_seen": sorted(set(m.group(0).strip() for m in PRICE.finditer(body)))[:30],
        "proof": uniq_ci((m.group(0) for m in PROOF.finditer(body)), 25),
        "urgency": uniq_ci((m.group(0) for m in URGENCY.finditer(body)), 20),
        "tracking": {"params": {k: v for l in links for k, v in tracking_params(l).items()},
                     "pixels": [], "link_hosts": sorted({host(l) for l in links})},
        "media": {}, "gates": [],
        "assets": {k: f"assets/{nid}/{fn}" for k, fn in (
            ("text", "message.txt"), ("eml", "message.eml"), ("html", "message.html"))
            if os.path.exists(os.path.join(adir, fn))},
        "notes": a.note,
    }
    for f in sorted(os.listdir(adir)):
        if f.startswith("screenshot-"):
            node["assets"].setdefault("screenshots", []).append(f"assets/{nid}/{f}")
    node = run.add_node(node)
    edge = None
    if a.parent:
        edge = run.add_edge(a.parent, node["id"], a.trigger or f"{a.channel} received",
                            cta=a.cta, channel=a.channel, path=node["path"])
    kind = {"email": "message_received", "sms": "message_received", "dm": "message_received",
            "retargeting-ad": "retargeting_seen"}.get(a.type, "stage_logged")
    run.event(kind, f"{a.type} via {a.channel}: {node['title'] or '(no subject)'}", at=at,
              node=node["id"], edge=edge["id"] if edge else None,
              data={"sender": node["message"]["sender"], "links": links[:20]})
    new = frontier_candidates(run, node, node["ctas"], a.url or "about:blank")
    run.f["branches"]["frontier"].extend(new)
    run.update_coverage()
    run.save()
    render_timeline(run)
    print(json.dumps({"node": node["id"], "received_at": node["captured_at"],
                      "links": links[:20], "new_branches": len(new)}, indent=2))


def cmd_event(a):
    run = resolve_run(a.run)
    at = parse_ts(a.at) if a.at else None
    data = json.loads(a.data) if a.data else None
    ev = run.event(a.kind, a.summary, at=at, node=a.node, data=data)
    if a.kind == "inbox_check":
        run.f["inbox"]["last_checked_at"] = ev["ts"]
        run.save()
    render_timeline(run)
    print(json.dumps(ev, indent=2))


def cmd_annotate(a):
    run = resolve_run(a.run)
    n = run.node(a.node)
    patch = json.load(open(a.json[1:])) if a.json.startswith("@") else json.loads(a.json)
    protected = {"id", "captured_at", "since_prev_s", "since_start_s", "depth"}
    for k, v in patch.items():
        if k in protected:
            die(f"field {k} is computed; not editable")
        n[k] = v
    run.save()
    render_timeline(run)
    print(f"annotated {a.node}: {', '.join(patch)}")


def cmd_end(a):
    run = resolve_run(a.run)
    if a.answer == "yes":
        run.f["status"] = "complete"
        run.f["end"] = {"node": a.node, "confirmed_by": "user", "confirmed_at": iso(now())}
        run.node(a.node)["is_end"] = True
        run.event("run_end", f"user confirmed {a.node} is the end of the funnel; run complete "
                  "(no purchase made)", node=a.node)
    else:
        run.f["status"] = "active"
        run.f["end"] = None
        run.event("end_check", f"user says {a.node} is NOT the end; continue "
                  "(upsells, downsells, order bumps, alternate offers)", node=a.node,
                  data={"user_note": a.note})
    run.save()
    render_timeline(run)
    print(run.f["status"])


def cmd_reopen(a):
    run = resolve_run(a.run)
    run.f["status"] = "active"
    run.event("note", f"run reopened: {a.reason}")
    run.save()
    render_timeline(run)
    print("active")


def cmd_inbox(a):
    run = resolve_run(a.run)
    ib = run.f["inbox"]
    for k in ("route", "address", "check_until"):
        v = getattr(a, k)
        if v:
            ib[k] = v
    if a.sender:
        ib["watch_senders"] = sorted(set(ib["watch_senders"]) | set(a.sender))
    run.save()
    since = run.f["created_at"][:10].replace("-", "/")
    q = " OR ".join(f"from:{s}" for s in ib["watch_senders"]) or "from:<sender-domain>"
    print(json.dumps(ib, indent=2))
    print(f"\nGmail query for this run: ({q}) after:{since}")


def cmd_metric(a):
    """Numbers for the report. Estimates and benchmarks must say where they came from."""
    run = resolve_run(a.run)
    if a.kind in ("estimated", "benchmark") and not (a.source and a.method):
        die("estimated and benchmark figures need --source and --method")
    if a.node:
        run.node(a.node)
    m = {"label": a.label, "value": a.value, "kind": a.kind, "node": a.node,
         "source": a.source, "method": a.method, "added_at": iso(now())}
    run.f.setdefault("metrics", []).append(m)
    run.save()
    print(json.dumps(m, indent=2))


def cmd_summary(a):
    """Run-level summary for the report: funnel_type, key_tactics, steal, gaps, price_ladder."""
    run = resolve_run(a.run)
    patch = json.load(open(a.json[1:])) if a.json.startswith("@") else json.loads(a.json)
    run.f.setdefault("summary", {}).update(patch)
    run.save()
    print(f"summary fields: {', '.join(run.f['summary'])}")


def cmd_report(a):
    run = resolve_run(a.run)
    if run.f["status"] != "complete" and not a.draft:
        die("the user has not confirmed the end of the funnel yet. Ask \"Is this the end of the "
            "funnel?\" and run `end --answer yes`, or pass --draft for a preview.")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import report
    out = report.build(run, embed=a.embed, draft=a.draft)
    if not a.draft:
        run.event("report", "generated report.html")
        render_timeline(run)
    print(out)


def cmd_timeline(a):
    run = resolve_run(a.run)
    run.update_coverage()
    run.save()
    render_timeline(run)
    print(os.path.join(run.path, "timeline.md"))


def cmd_status(a):
    run = resolve_run(a.run)
    f = run.f
    run.update_coverage()
    print(json.dumps({
        "run": f["run_id"], "status": f["status"], "end": f["end"],
        "nodes": [f"{n['id']} {n.get('path')} {n['type']} {n.get('final_url') or n.get('title')}"
                  for n in f["nodes"]],
        "open_gates": [f"{n['id']}: {g['kind']}" for n in f["nodes"] for g in n.get("gates", [])],
        "coverage": f["coverage"], "inbox": f["inbox"],
        "open_branches": [f"{x['from']} \"{x['cta'][:40]}\" -> {x['target']}"
                          for x in f["branches"]["frontier"] if x["status"] == "open"][:30],
    }, indent=2, ensure_ascii=False))


def cmd_validate(a):
    run = resolve_run(a.run)
    errs = []
    ids = {n["id"] for n in run.f["nodes"]}
    for n in run.f["nodes"]:
        if n["type"] not in NODE_TYPES:
            errs.append(f"{n['id']}: bad type {n['type']}")
        for k, v in n.get("assets", {}).items():
            for p in (v if isinstance(v, list) else [v]):
                if not os.path.exists(os.path.join(run.path, p)):
                    errs.append(f"{n['id']}: missing asset {p}")
    for e in run.f["edges"]:
        if e["from"] not in ids or e["to"] not in ids:
            errs.append(f"{e['id']}: dangling edge")
    evs = run.events()
    for i, e in enumerate(evs, 1):
        if e["seq"] != i:
            errs.append(f"events.jsonl seq gap at line {i}")
            break
    logged = [parse_ts(e["logged_at"]) for e in evs]
    if logged != sorted(logged):
        errs.append("events.jsonl logged_at not monotonic (file was edited, not appended)")
    print("ok" if not errs else "\n".join(errs))
    sys.exit(1 if errs else 0)


def main():
    p = argparse.ArgumentParser(prog="fh.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("new", help="start a run from a TOF item")
    s.add_argument("tof", help="TOF URL, or a short description if there is no URL")
    s.add_argument("--slug"); s.add_argument("--title"); s.add_argument("--platform")
    s.add_argument("--notes"); s.add_argument("--root", help="runs folder (default $FH_RUNS_DIR or ./runs)")
    s.add_argument("--max-depth", type=int, default=3)
    s.set_defaults(fn=cmd_new)

    s = sp.add_parser("capture", help="load a URL (GET only), screenshot and extract a stage")
    s.add_argument("run"); s.add_argument("url")
    s.add_argument("--type", help="|".join(NODE_TYPES)); s.add_argument("--platform")
    s.add_argument("--parent", help="node id this came from"); s.add_argument("--cta")
    s.add_argument("--trigger", default="click"); s.add_argument("--channel", default="web")
    s.add_argument("--branch", action="store_true", help="explored branch, not the user's path")
    s.add_argument("--record", action="store_true", help="save a scroll-through .webm")
    s.add_argument("--no-mobile", action="store_true"); s.add_argument("--wait-ms", type=int, default=2500)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_capture)

    s = sp.add_parser("explore", help="auto-capture open branches (BFS, GET only, gates respected)")
    s.add_argument("run"); s.add_argument("--max-pages", type=int, default=8)
    s.add_argument("--max-depth", type=int); s.add_argument("--from-node")
    s.add_argument("--same-site", action="store_true"); s.add_argument("--no-mobile", action="store_true")
    s.add_argument("--min-priority", type=int, default=2,
                   help="skip links scored below this (mentions, affiliates); 0 explores everything")
    s.set_defaults(fn=cmd_explore)

    s = sp.add_parser("add-node", help="log a stage seen outside the browser (email, SMS, DM, ad)")
    s.add_argument("run"); s.add_argument("--type", required=True)
    s.add_argument("--channel", default="email", help="email|sms|dm|web|ad|...")
    s.add_argument("--platform"); s.add_argument("--parent"); s.add_argument("--cta")
    s.add_argument("--trigger"); s.add_argument("--at", help="when it happened/arrived (ISO)")
    s.add_argument("--eml", help=".eml file (forwarded or exported email)")
    s.add_argument("--body-file"); s.add_argument("--subject"); s.add_argument("--title")
    s.add_argument("--sender"); s.add_argument("--url"); s.add_argument("--screenshot", nargs="*")
    s.add_argument("--branch", action="store_true"); s.add_argument("--note")
    s.set_defaults(fn=cmd_add_node)

    s = sp.add_parser("event", help="append an event (delay, gate decision, inbox_check, note)")
    s.add_argument("run"); s.add_argument("kind"); s.add_argument("summary")
    s.add_argument("--node"); s.add_argument("--at"); s.add_argument("--data", help="JSON")
    s.set_defaults(fn=cmd_event)

    s = sp.add_parser("annotate", help="merge agent analysis fields into a node")
    s.add_argument("run"); s.add_argument("node"); s.add_argument("json", help="JSON or @file")
    s.set_defaults(fn=cmd_annotate)

    s = sp.add_parser("end", help="record the user's answer to 'Is this the end of the funnel?'")
    s.add_argument("run"); s.add_argument("--node", required=True)
    s.add_argument("--answer", choices=["yes", "no"], required=True); s.add_argument("--note")
    s.set_defaults(fn=cmd_end)

    s = sp.add_parser("reopen", help="reopen a completed run"); s.add_argument("run")
    s.add_argument("--reason", required=True); s.set_defaults(fn=cmd_reopen)

    s = sp.add_parser("inbox", help="set the follow-up inbox route and watched senders")
    s.add_argument("run"); s.add_argument("--route", help="mcp|cli|manual")
    s.add_argument("--address"); s.add_argument("--sender", nargs="*")
    s.add_argument("--check-until", dest="check_until")
    s.set_defaults(fn=cmd_inbox)

    s = sp.add_parser("metric", help="add a number for the report (observed|estimated|benchmark)")
    s.add_argument("run"); s.add_argument("--label", required=True); s.add_argument("--value", required=True)
    s.add_argument("--kind", choices=["observed", "estimated", "benchmark"], required=True)
    s.add_argument("--node"); s.add_argument("--source"); s.add_argument("--method")
    s.set_defaults(fn=cmd_metric)

    s = sp.add_parser("summary", help="merge run-level summary fields (JSON or @file)")
    s.add_argument("run"); s.add_argument("json"); s.set_defaults(fn=cmd_summary)

    s = sp.add_parser("report", help="build report.html (after the user confirms the end)")
    s.add_argument("run"); s.add_argument("--draft", action="store_true")
    s.add_argument("--embed", choices=["full", "fold", "none"], default="full")
    s.set_defaults(fn=cmd_report)

    for name, fn, h in (("timeline", cmd_timeline, "regenerate timeline.md"),
                        ("status", cmd_status, "summary, gates, open branches"),
                        ("validate", cmd_validate, "check graph, assets and event log")):
        s = sp.add_parser(name, help=h); s.add_argument("run"); s.set_defaults(fn=fn)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
