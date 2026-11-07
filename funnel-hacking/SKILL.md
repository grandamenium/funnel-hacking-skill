---
name: funnel-hacking
description: Reverse-engineer a marketing funnel from one top-of-funnel item (an ad, post, video or URL) and follow it to the buy page. Every stage (nodes and edges) is recorded with its links, CTAs, hooks, copy, offers, prices, proof, urgency, tracking pixels, platform and exact timing. Captures go to a per-funnel run folder with screenshots and an append-only event log. Follow-up emails, SMS and retargeting are logged as they arrive, and the run finishes with an interactive HTML report. Use it when someone wants to funnel hack, study a competitor's funnel, see where an ad leads, map a creator's lead magnet or offer ladder, or copy a funnel structure. Also use it when they share an ad or post and ask "what happens after I click this?".
---

# Funnel hacking

Start from one top-of-funnel (TOF) item. Walk the funnel as a prospect would, record every stage in maximal detail, and stop at the buy page. Each funnel gets its own run folder. The agent does the browsing, capturing and analysis; the user does anything that needs their identity or money.

## Hard rules (never break these, on any path or branch)

- **Never submit a form, sign up, log in, pay, or send a message** as the user. These are gates (see below), and gates need the user.
- **Stop at the buy page.** Capture it fully, never buy anything, then ask the user: **"Is this the end of the funnel?"**
- **Public pages only.** Don't bypass logins, paywalls or bot checks. `fh.py` checks robots.txt and refuses disallowed URLs. It also waits at least 3 s between page loads.
- **Personal data:** store only what the public page shows. If the user enters their own details at a gate, keep them out of `analysis.md` and the report.
- **No crons.** Inbox follow-up checks are scheduled only if the user asks, and they are set up with the host's task tooling (see `references/followups.md`).

## The run folder

```
runs/<YYYY-MM-DD>-<slug>/
  funnel.json     graph: nodes (stages), edges (transitions), branches, coverage, metrics, summary
  events.jsonl    append-only; one line per thing that happened, exact UTC time + elapsed since start
  timeline.md     generated from events.jsonl, in order (never edit by hand)
  analysis.md     written by you (template: templates/analysis.md)
  report.html     generated after the user confirms the end of the funnel
  assets/nN/      per stage: desktop-full.png, desktop-fold.png, mobile-full.png,
                  page.html, page.txt, recording.webm (if --record), social-meta.json,
                  message.eml/.txt/.html (emails, SMS)
```

The schema is in `references/schema.md`. Only change `funnel.json` through `fh.py` (`annotate`, `summary`, `metric`), because it keeps the graph, events and timeline consistent.

## Tool

`scripts/fh.py`, a Python CLI that uses Playwright and runs headless Chromium. If Playwright's bundled browser is missing, it falls back to any Chromium in the ms-playwright cache. Run it from the folder that should hold `runs/`, or set `FH_RUNS_DIR`. Below, `FH` means `python3 <skill>/scripts/fh.py`.

| Command | What it does |
|---|---|
| `FH new <tof-url-or-text> --slug s --platform p --notes n` | create the run and log `run_start` |
| `FH capture <run> <url> [--parent nX --cta "text"] [--type T] [--branch] [--record]` | GET the page; take desktop and mobile full-page screenshots; save HTML and text; extract CTAs, forms, prices, proof, urgency, popups, pixels and UTMs; detect gates; add frontier branches; log click and page_view events |
| `FH explore <run> [--max-pages 8 --max-depth 3 --min-priority 2]` | auto-capture open branches breadth-first, highest priority first, and mark them `path: branch` |
| `FH add-node <run> --type email --channel email --parent nX [--eml f / --body-file f] [--at ISO]` | log a stage seen outside the browser: an email, SMS, DM, retargeting ad or webinar |
| `FH event <run> <kind> "<summary>" [--node nX] [--at ISO]` | append an event, such as a gate decision, delay, inbox check or note |
| `FH annotate <run> nX '<json>' or @file` | add your analysis to a node: hook, offers, analysis{strategy,tactics,steal}, type fix |
| `FH metric <run> --label --value --kind observed/estimated/benchmark [--source --method]` | add a number for the report; estimates and benchmarks must have a source and method |
| `FH summary <run> @file` | run-level summary: funnel_type, key_tactics, price_ladder, steal{business:[...]}, gaps |
| `FH end <run> --node nX --answer yes/no` | record the user's answer to "Is this the end of the funnel?" |
| `FH inbox <run> --route ... --address ... --sender domain... --check-until DATE` | set up follow-up watching and print the Gmail query |
| `FH report <run> [--draft]` | build `report.html`; it refuses until the end is confirmed unless you pass `--draft` |
| `FH timeline / status / validate <run>` | regenerate the timeline / summarize / check integrity |

`capture` prints JSON (node id, type, screenshots, pixels, main CTAs, gates, new branches). It also prints `GATE:` or `ASK THE USER:` lines when you must stop.

## Workflow

1. **Intake.** Get the TOF item: a URL (ad, post, video, page), or a screenshot or paste if there is no URL. Also get the platform and any notes, such as where it was seen and the targeting. If the TOF is an ad, also look it up in the ad library (`references/sources.md`) to record run length and variant count.
2. **Identity at gates.** Ask the user up front how gates will be handled, so you don't have to stop mid-run. Offer these choices:
   - (a) the user enters a dedicated funnel-research email/phone while you record
   - (b) the user gives you that dedicated address and approves you typing it in. This happens only after explicit approval for this run, and you never use the user's personal details without their OK.
   - (c) stop at the first gate (dry run)

   Recommend a dedicated research inbox over the user's personal inbox.
3. **`FH new`**, then **`FH capture`** the TOF URL (`--type ad|post|video` if you know it). For social posts, `capture` also pulls the caption or description, view and like counts and follower counts through yt-dlp metadata. It never downloads the video unless the user asks and the platform allows it.
4. **Follow the user's path.** Pick the CTA a real prospect would most likely click, usually the most prominent owned offer, or the one the user names. Then run `FH capture <run> <target> --parent nX --cta "<exact CTA text>"`. For JS-only buttons with no href, open the page with `agent-browser` and click the button. Clicking is fine as long as it is not a submit, login or pay action. Then capture the resulting URL.
5. **At a gate, stop.** `capture` prints `GATE: email|phone|login|payment`. Follow `references/gates.md`: ask the user, log their decision with `FH event <run> gate_decision "..."`, and either wait for them to act or end the path. After the user passes a gate themselves, capture the next page they land on (they give you the URL, or you read it from the shared browser) with `--trigger "form submitted by user"`.
6. **Explore branches.** At each node, `capture` adds alternate paths to `branches.frontier`. These include other CTAs, link-in-bio options, "no thanks" or downsell links, pricing tiers and popups, and each one gets a priority. Run `FH explore <run>` to capture them automatically as `path: branch`. Gates apply to branches too, and `explore` never submits anything. Use `--same-site`, `--max-depth` and `--min-priority` to stay focused. Low-priority links (tool mentions, affiliate links, social profiles) are skipped and recorded as skipped, so coverage stays honest.
7. **Buy page.** When a node looks like a checkout, order form or peak offer, `capture` sets `status: awaiting_end_confirmation` and prints `ASK THE USER: "Is this the end of the funnel?"`. Ask exactly that question.
   - **Yes:** `FH end <run> --node nX --answer yes`.
   - **No:** run `FH end ... --answer no` and continue into the upsells, downsells, order bumps and alternate offers. Never buy anything to see an upsell. Capture what is visible without paying (for example, a public OTO URL or a "no thanks" link). Otherwise ask the user to forward or screenshot it, and log it with `add-node --screenshot`.
8. **Delayed stages.** Emails, SMS and retargeting ads arrive over days. Log each with `FH add-node` using the real arrival time (`--at`, or the `Date:` header of an `.eml`). Read-only inbox checks and how to schedule them are in `references/followups.md`. Retargeting ads the user sees go in as `--type retargeting-ad --channel ad --screenshot <file>`.
9. **Analyze.** For each node on the taken path and each notable branch, run `FH annotate` with the hook, the offers (name, price, anchor, bonuses, guarantee) and `analysis: {strategy, tactics[], steal[]}`. Add numbers with `FH metric`, following `references/numbers.md`. Write `analysis.md` from `templates/analysis.md`, then run `FH summary` with the run-level fields. Put the "what to copy" section in terms of the user's own businesses; ask which ones if you don't know.
10. **Report.** Once the user confirms the end, run `FH report <run>`. The report is self-contained HTML. It shows a top-down graph with the taken path highlighted and the branches dashed. Clicking a node opens its screenshots, copy, CTAs, offer and timing. It also has an analysis overlay, a summary panel and every number labelled observed, estimated or benchmark. Open it and look at it (screenshot it with Playwright or agent-browser) before you hand it over. Check that `FH validate <run>` prints `ok`.

## Resuming a run

`FH status <run>` shows the status, open gates, open branches and inbox settings. Every command appends to `events.jsonl`, so a run can be resumed by any agent at any time. After a run is complete, use `FH reopen <run> --reason "..."` to log a late upsell or follow-up page. Logging emails with `add-node` never needs a reopen.

## What good output looks like

- Every taken-path node has a screenshot (desktop and mobile), a hook, a headline, CTAs with placement, an offer and price where shown, and timing.
- Edges say how the transition happened: the exact CTA text, the trigger (click, form submitted by user, email received), the channel and the delay.
- `timeline.md` reads as a strictly chronological story, from the first view to the buy page and the follow-ups.
- The analysis says *why* each stage works and what to copy, not just what is on the page.
- Numbers never pretend: CTR and conversion are unobservable from outside, so they appear only as labelled benchmarks or estimates with a source.

## References

- `references/gates.md`: gate types, what to ask, and how to log decisions
- `references/sources.md`: ad libraries, platform capture tools, link-in-bio pages, and what to do when robots.txt or a login blocks capture
- `references/followups.md`: read-only Gmail checks (MCP/integration, CLI, manual), the inbox choice, and documented scheduling
- `references/numbers.md`: observed vs estimated vs benchmark, with acceptable sources
- `references/schema.md`: the fields in `funnel.json` and `events.jsonl`
- `templates/analysis.md`: the analysis.md skeleton
