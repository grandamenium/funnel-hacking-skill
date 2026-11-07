"""Builds report.html for a funnel-hacking run (called by `fh.py report`).

Self-contained: data and screenshots are embedded, so the file can be sent or
opened anywhere. Every number shown carries a kind: observed, estimated or
benchmark. Observed numbers are derived here from what was captured; estimates
and benchmarks come only from `fh.py metric` entries, which require a source
and method.
"""
import base64
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "report.html")


def _human(seconds):
    if seconds is None:
        return None
    s = int(round(seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = [f"{d}d" if d else "", f"{h}h" if h else "", f"{m}m" if m else "",
             f"{s}s" if (s or not (d or h or m)) else ""]
    return " ".join(p for p in parts if p)


def _img(run, rel, mode):
    """Return a data URI (JPEG, downscaled) or the relative path if PIL is missing."""
    if mode == "none" or not rel:
        return rel
    p = os.path.join(run.path, rel)
    if not os.path.exists(p):
        return None
    try:
        from PIL import Image
    except ImportError:
        with open(p, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    Image.MAX_IMAGE_PIXELS = None  # our own screenshots, not untrusted uploads
    im = Image.open(p).convert("RGB")
    w = 420 if "mobile" in rel else 900
    if im.width > w:
        im = im.resize((w, int(im.height * w / im.width)))
    max_h = 9000
    if im.height > max_h:
        im = im.crop((0, 0, im.width, max_h))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=68, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def observed_metrics(f):
    out = []
    nodes = f["nodes"]
    taken = sorted([n for n in nodes if n.get("path") == "taken"], key=lambda n: n["captured_at"])

    def add(label, value, node=None, source="captured in this run"):
        if value in (None, "", []):
            return
        out.append({"label": label, "value": value, "kind": "observed", "node": node,
                    "source": source, "method": None})

    add("Steps on the taken path", len(taken))
    add("Branch pages explored", sum(1 for n in nodes if n.get("path") == "branch"))
    add("Max depth", f["coverage"].get("max_depth"))
    add("Branch coverage", f"{f['coverage'].get('coverage_pct', 0)}%")
    if taken:
        t0 = taken[0]["since_start_s"] or 0
        offer = next((n for n in taken if n.get("buy_page_candidate") or n.get("is_end")), None)
        if offer:
            add("Time to offer (TOF to buy page)", _human(offer["since_start_s"] - t0), offer["id"])
        add("Total run time (first to last stage)", _human(taken[-1]["since_start_s"] - t0))
    for n in nodes:
        main = [c for c in n.get("ctas", []) if c["kind"] in ("button", "no-thanks", "form-submit")]
        if main:
            add("Main CTAs on page", len(main), n["id"])
        if n.get("prices_seen"):
            add("Prices shown", ", ".join(n["prices_seen"][:8]), n["id"])
        if n.get("tracking", {}).get("pixels"):
            add("Tracking pixels/tools", len(n["tracking"]["pixels"]), n["id"])
        s = n.get("social") or {}
        for k, label in (("view_count", "Views"), ("like_count", "Likes"),
                         ("comment_count", "Comments"),
                         ("channel_follower_count", "Followers/subscribers")):
            if s.get(k) is not None:
                add(label, f"{s[k]:,}", n["id"], source="platform metadata (yt-dlp)")
        if s.get("upload_date"):
            d = s["upload_date"]
            add("Published", f"{d[:4]}-{d[4:6]}-{d[6:]}", n["id"], source="platform metadata (yt-dlp)")
    for e in f["edges"]:
        if e.get("path") == "taken" and e.get("delay_s") is not None:
            add(f"Delay {e['from']} -> {e['to']}", _human(e["delay_s"]), e["to"])
    return out


def build(run, embed="full", draft=False):
    f = json.loads(json.dumps(run.f))  # deep copy
    for n in f["nodes"]:
        imgs = {}
        for k in ("screenshot", "screenshot_mobile"):
            rel = n.get("assets", {}).get(k)
            if rel:
                if embed == "fold" and k == "screenshot":
                    rel = n["assets"].get("screenshot_fold", rel)
                imgs[k] = _img(run, rel, embed)
        for i, rel in enumerate(n.get("assets", {}).get("screenshots", []) or []):
            imgs[f"extra_{i}"] = _img(run, rel, embed)
        n["_img"] = imgs
        txt = n.get("assets", {}).get("text")
        if txt and os.path.exists(os.path.join(run.path, txt)):
            with open(os.path.join(run.path, txt)) as fh:
                n["_copy"] = fh.read()[:20000]
        n.pop("forms", None) if not n.get("forms") else None
    f["_metrics"] = observed_metrics(f) + f.get("metrics", [])
    f["_events"] = sorted(run.events(), key=lambda e: (e["ts"], e["seq"]))
    f["_draft"] = draft
    data = json.dumps(f, ensure_ascii=False).replace("</", "<\\/")
    with open(TEMPLATE) as fh:
        tpl = fh.read()
    out_html = tpl.replace("__FUNNEL_TITLE__", (f.get("title") or "Funnel").replace("<", "&lt;")) \
                  .replace("__FUNNEL_DATA__", data)
    name = "report-draft.html" if draft else "report.html"
    out = os.path.join(run.path, name)
    with open(out, "w") as fh:
        fh.write(out_html)
    return out
