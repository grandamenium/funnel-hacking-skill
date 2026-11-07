# funnel.json and events.jsonl

## funnel.json (schema_version 1)

```
run_id, title, created_at (UTC ISO), tof{input, platform, notes}
status: active | awaiting_end_confirmation | complete
end: {candidate_node, asked_at} | {node, confirmed_by, confirmed_at} | null
identity: {email, phone, chosen_by_user}      # research identity only, never personal
inbox: {route, address, watch_senders[], check_until, last_checked_at}
nodes[]: one per stage
  id (n1..), type, platform, url, final_url, redirect_chain[], http_status, robots
  captured_at, since_prev_s (vs parent, or the previous node), since_start_s, load_s
  path: taken | branch, parent, depth
  title, hook, headline, subheadlines[]
  copy{text_file, word_count, opening[]}, meta{meta_description, og_*, canonical, lang}
  ctas[]{text, target, kind: button|link|no-thanks|form-submit|nav, placement{region, above_fold, y, in_modal}}
  forms[]{action, method, fields[]{type,name,label,autocomplete}, hidden_fields[]}
  offers[] (written by the agent: name, price, anchor_price, bonuses, guarantee, ...)
  prices_seen[], proof[], urgency[], popups[]
  tracking{params{utm_*,fbclid,...}, pixels[], third_party_hosts[]}
  media{iframes[], videos[], images[]}, social{...yt-dlp fields}
  message{channel, sender, received_at} (email/sms/dm nodes)
  gates[]{kind: email|phone|login|payment, detail}
  buy_page_candidate, is_end, analysis{strategy, tactics[], steal[]}, notes
  assets{screenshot, screenshot_fold, screenshot_mobile, html, text, recording, social_meta, eml, screenshots[]}
edges[]: {id (e1..), from, to, trigger, cta, channel, path, delay_s}
branches: {frontier[]{from, cta, target, reason, priority, status: open|taken|explored|skipped|gated, node, skip_reason, depth}, max_depth}
coverage: {nodes_total, nodes_taken_path, nodes_branch, max_depth, frontier_*, coverage_pct}
metrics[]: {label, value, kind: observed|estimated|benchmark, node, source, method}
summary: {funnel_type, key_tactics[], price_ladder[]{price,name,node}, steal{business:[...]}, gaps[]}
```

Node types: ad, post, video, profile, link-in-bio, landing, opt-in, thank-you, email, sms, dm, webinar, vsl, sales-page, order-form, checkout, upsell, downsell, order-bump, community, retargeting-ad, other.

## events.jsonl

The file is append-only, one JSON object per line:

```
{"seq": 7, "ts": "<when it happened, UTC>", "elapsed_s": 312.4, "kind": "page_view",
 "summary": "...", "node": "n3", "edge": "e2", "logged_at": "<when written>",
 "logged_late": true?, "data": {...}?}
```

Kinds: `run_start, click, page_view, gate, gate_decision, branch_skipped, blocked, end_check, run_end, message_received, retargeting_seen, stage_logged, inbox_check, delay, note, report`.

The two times mean different things. `ts` is when the event happened; `logged_at` is when it was written. An email that arrived at 09:00 and was logged at 15:00 has `ts` 09:00. `timeline.md` sorts by `ts` (ties broken by `seq`), so the story stays strictly chronological. `logged_late` marks events that were appended after a later-timestamped event. `fh.py` refuses future timestamps. `validate` checks that `seq` is contiguous and `logged_at` is monotonic, which shows the file was only ever appended to.
