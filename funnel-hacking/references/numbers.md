# Numbers: observed, estimated, benchmark

The report labels every figure. Honesty matters more than completeness. From outside a funnel you can't see its CTR, opt-in rate, conversion rate, revenue or traffic.

| Kind | Meaning | Examples | Needs |
|---|---|---|---|
| `observed` | Seen directly in this run | views, likes, comments, follower counts (yt-dlp metadata); ad start date and variant count (ad library); "370k+ subscribers" or "2,000+ reviews" claimed on the page (label it *claimed*); prices; time between steps; number of steps, CTAs, pixels and emails | Nothing extra. `fh.py report` derives most of these automatically. |
| `estimated` | Inferred for this funnel by a stated method | traffic from a third-party estimator; "≈ 1 to 3% of viewers click the description link" applied to a known view count | `--source` and `--method`, both required. Show a range, not a point. |
| `benchmark` | Industry figure, not this funnel's number | median landing-page conversion; email open rates by industry | `--source` (with a URL and the report year) and `--method` (what the figure measures) |

Rules:

- Never present a benchmark as this funnel's performance. Label the metric with what it is, for example "Median landing page conversion rate (all industries)".
- Prefer primary sources (the benchmark publisher's own report page) over blog roundups. If only a secondary source is available, say so in `--source`.
- Claims made on the page ("10,000 students") are observed *claims*, not verified facts. Put "claimed on page" in the source.
- When a number goes stale (view counts change), the capture timestamp is its date. Don't update it silently; capture again instead.
