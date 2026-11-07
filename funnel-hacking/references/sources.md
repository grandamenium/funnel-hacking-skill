# Capture sources

## Pages (landing, opt-in, sales, checkout)
`fh.py capture` uses headless Chromium through Playwright. It takes desktop (1366 wide) and mobile (iPhone 13) full-page screenshots, saves the HTML and visible text, and records every network request so it can spot pixels. `--record` adds a scroll-through `.webm` video. Full-page screenshots stop at 16,000 CSS px.

For JS-heavy flows (multi-step quizzes, popups that open on a timer or on exit intent, buttons with no href), use **agent-browser**. Load its guide with `agent-browser skills get core`. Then use `open`, `snapshot`, `click @ref` (never a submit) and `screenshot --full`, and `get url` to find the next URL to `capture`. For an exit-intent popup, move the mouse to the top edge (`mouse move 600 0`) and screenshot. Log the popup with `add-node --type landing --branch --screenshot`, or `annotate` it onto the page's node.

## Social posts and videos
`capture` calls `yt-dlp -J --skip-download` for YouTube, TikTok, Instagram, Facebook video, Vimeo, X and Loom. This records the title, description or caption, uploader, follower count, views, likes, comments and upload date in `social-meta.json`. Links in the description become the node's CTAs, labelled with their line text.

Download a video only when the user asks and the platform's terms allow it. Then run `yt-dlp -o "assets/nN/video.%(ext)s" <url>`. For transcripts (useful for hook analysis), run `yt-dlp --write-auto-sub --sub-lang en --skip-download -o assets/nN/subs <url>`.

The `agent-reach` skill covers Twitter/X, Reddit, LinkedIn and others when a post needs a logged-in backend. Run `agent-reach doctor --json` to see which platforms are active.

## Ad libraries (for ad TOF items)
Use these to record **observed** facts: when the ad started running, whether it is still active, how many variants exist, the platforms it runs on and the landing URLs. Run length and variant count are the best public signals that an ad is working.

| Library | URL | Automated capture? |
|---|---|---|
| Meta Ad Library | facebook.com/ads/library | robots.txt disallows generic bots, so don't crawl it. The user can open the page, or share a screenshot, the "Started running on" date and the variant count. The official Ad Library API needs a Meta developer token with ID verification; it is not set up. |
| Google Ads Transparency Center | adstransparency.google.com | Allowed by robots.txt. `capture` works, but the page is JS-heavy, so use `--wait-ms 6000`. |
| TikTok Ad Library (EU/EEA ads) | library.tiktok.com | `/ads` is disallowed. Use the user-assisted route. |
| LinkedIn Ad Library | linkedin.com/ad-library | Disallowed. Use the user-assisted route. |

Log ad-library facts as a node (`add-node --type ad --channel ad --screenshot <file> --note "<facts>"`) plus `metric --kind observed` entries, such as "Ad running since" and "Active variants".

## Link-in-bio pages
Linktree and several similar services disallow generic bots in robots.txt. `capture` refuses those pages and logs a `blocked` event. Ask the user to paste the list of links, or share a screenshot. Then log it with `add-node --type link-in-bio --channel web --body-file links.txt --screenshot shot.png`. The links become frontier branches.

## When capture is blocked
These cases include robots.txt, a login wall, a bot check (Cloudflare challenge), a geo-block and personalized URLs. Don't work around them. Record the blocked event, tell the user, and offer the user-assisted route: they view the page and share screenshots, the URL and the text, and you log it with `add-node`.
