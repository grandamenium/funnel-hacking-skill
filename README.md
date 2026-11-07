# Funnel Hacking skill

An agent skill that reverse-engineers a marketing funnel. Give it one top-of-funnel item, such as an ad, a post, a video or a URL. It follows that item the way a prospect would, all the way to the buy page.

It records every stage in detail:

- links and CTAs (exact text, target, placement)
- hooks and full copy
- offers, prices and anchors
- proof, urgency and popups
- the tracking pixels and UTMs the page uses
- the platform and exact timing

It saves screenshots of every page. It also explores the other paths it finds and builds a clickable HTML report of the whole funnel.

It works with Claude Code and any agent that can read a `SKILL.md` and run Python.

## What you get per funnel

```
runs/2026-11-06-some-funnel/
  funnel.json     the funnel as a graph: stages (nodes) and how you got between them (edges)
  events.jsonl    append-only log of everything that happened, with exact timestamps
  timeline.md     the funnel as a chronological story, generated from the log
  analysis.md     the agent's breakdown: structure, tactics, what to copy, gaps
  report.html     interactive report: top-down funnel graph, click any stage for screenshots,
                  copy, CTAs, offer and timing; every number labelled observed / estimated / benchmark
  assets/nN/      desktop + mobile full-page screenshots, saved HTML and text, optional scroll
                  recording, video metadata, captured follow-up emails
```

## What it does

- **Captures each page.** It takes desktop and mobile screenshots and pulls out the headline, copy, CTAs with their placement, forms, prices, proof, urgency and popups. It also detects tracking pixels (Meta, Google, TikTok, Clarity, Kit, ActiveCampaign, Stripe and more) from the page's network requests, plus UTM parameters.
- **Reads social posts.** For YouTube, TikTok, Instagram and other video posts, it uses `yt-dlp` metadata to get the caption, view, like and follower counts, and the links in the description, without downloading the video.
- **Explores branches on its own.** On every page it scores the other paths (other CTAs, "no thanks" links, link-in-bio options, pricing tiers) and explores them as branches. It tracks depth and coverage, and marks the path you took separately from the branches it explored.
- **Logs follow-ups.** Emails, SMS, DMs and retargeting ads get logged as new stages with their real arrival time. Each follow-up can come from a forwarded `.eml`, pasted text or a screenshot.
- **Stops at the buy page.** It captures the checkout and asks "Is this the end of the funnel?" If you say no, it keeps mapping upsells and downsells, without buying anything.
- **Keeps the numbers honest.** Click-through and conversion rates can't be seen from outside a funnel. The report shows only what it observed, plus clearly labelled benchmarks or estimates, each with a source and method.

## Safety rules built in

- It never submits a form, signs up, logs in, pays or sends a message for you. Those steps are gates where the agent stops and asks you.
- It only makes GET page loads. It respects `robots.txt` and waits at least 3 seconds between page loads.
- It captures public pages only. It doesn't get around paywalls, logins or bot checks.
- It recommends a dedicated research inbox for opt-ins instead of your personal email.
- It doesn't create recurring jobs on its own. Inbox checks are documented so you can schedule them yourself if you want.

## Install

Copy the `funnel-hacking/` folder into your agent's skills folder. For Claude Code:

```bash
git clone https://github.com/grandamenium/funnel-hacking-skill
cp -R funnel-hacking-skill/funnel-hacking ~/.claude/skills/
```

Requirements:

- Python 3.9+
- [Playwright for Python](https://playwright.dev/python/) with Chromium (`pip install playwright && playwright install chromium`)
- Optional: `pillow`, which keeps report screenshots small
- Optional: [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), for social post metadata

## Use

Ask your agent something like:

> Funnel hack this ad: https://... I want to see everything that happens after someone clicks it.

The agent follows `funnel-hacking/SKILL.md`. You can also drive the CLI yourself:

```bash
FH="python3 funnel-hacking/scripts/fh.py"
$FH new "https://www.youtube.com/watch?v=..." --slug creator-lead-magnet --platform youtube
$FH capture runs/<run> "https://www.youtube.com/watch?v=..." --type video
$FH capture runs/<run> "https://example.com/free-guide" --parent n1 --cta "Get the free guide"
$FH explore runs/<run> --max-pages 5          # follow the other paths automatically
$FH add-node runs/<run> --type email --parent n2 --eml welcome.eml   # log a follow-up email
$FH end runs/<run> --node n6 --answer yes     # you confirm the buy page is the end
$FH report runs/<run>                         # build report.html
```

Run `python3 funnel-hacking/scripts/fh.py -h` to see every command.

## Limits

- Page-type classification and gate detection are heuristics, and the agent corrects them as it goes.
- Some sites block automated visits in `robots.txt`, including several ad libraries and link-in-bio pages. For those, the skill falls back to you sharing a screenshot or the links.
- Paths behind a gate (after an opt-in) need you to take that step, ideally with a research email.
