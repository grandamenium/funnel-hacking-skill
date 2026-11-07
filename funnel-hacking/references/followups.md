# Follow-ups: email, SMS, DMs, retargeting (read-only)

Follow-ups arrive after an opt-in, often over 7 to 14 days. They are part of the funnel and get logged as nodes, with their real arrival time.

## 1. Choose the inbox (ask the user)

Ask: "Which inbox should follow-ups for this run go to?" Recommend a **dedicated funnel-research address** over the user's personal inbox, for three reasons. It keeps marketing lists out of their real inbox. Searches are cleaner, because only funnel mail arrives there. And it avoids reading unrelated personal mail.

Record the choice:

```bash
FH inbox <run> --route mcp|cli|manual --address research@... --sender theirdomain.com mail.theirtool.com --check-until 2026-11-20
```

`FH inbox` prints the Gmail query for the run. The query is `(from:<sender> OR ...) after:<run start date>`. Add sender domains as you learn them. The first email often comes from an ESP domain, such as `convertkit-mail.com` or `klaviyomail.com`.

## 2. Read-only check routes

Never send, reply, label, archive, delete or unsubscribe. The only allowed actions are search and read.

**a) A Gmail MCP server or integration platform** (for example Composio, or any Gmail MCP the host already has). Use only its search and read tools, and pass the query that `FH inbox` printed. If Gmail isn't connected, don't connect it yourself. Tell the user which connection to approve, ideally for the research inbox only. Connecting an account is the user's decision.

**b) A Gmail CLI** that is already signed in to the research account:

```bash
<gmail-cli> search "<the FH inbox query>" --account <research-address> --json
```

Use it only for an account the user named for this run. Never default to their personal accounts.

**c) Manual.** The user forwards each email to you as an `.eml` file (most mail apps support "Download message" or "Show original"). For SMS and DMs, they send a screenshot and paste the text.

## 3. Log each message

```bash
FH add-node <run> --type email --channel email --parent <opt-in node> --eml msg.eml
FH add-node <run> --type sms --channel sms --parent n2 --body-file sms.txt --at "2026-11-08T09:14:00-05:00" --sender "+1 555..." --screenshot sms.png
FH add-node <run> --type retargeting-ad --channel ad --platform instagram --screenshot ad.png --note "seen in IG feed" --at ...
FH event <run> inbox_check "checked research inbox: 2 new (n9, n10)"
```

Save each message's content to `assets/nN/`. `add-node` copies the `.eml` and writes `message.txt`, plus `message.html` for HTML mail. Links in the message become frontier branches. Running `FH explore` captures the landing pages they point to.

The parent of an email is the stage that triggered it, usually the opt-in, or the previous email in the sequence. The edge delay is computed from the actual times.

Messages are addressed to the research identity. Before analysis, strip the recipient's address, name and any personal tokens from the copy.

## 4. Scheduling (document only)

Don't create crons, `/loop` jobs or scheduled tasks from inside this skill. If the user asks for recurring checks, for example "check this run's inbox daily for 14 days", set it up through the host's normal scheduling path (cron, a task scheduler, or your agent platform's scheduled tasks), and only when the user asks. The recurring job runs:

```
cd <runs parent> && python3 <skill>/scripts/fh.py status <run>
# then the inbox route's search (2a/2b) with the printed query, then add-node for each new message,
# then: fh.py event <run> inbox_check "<n new>"; stop after inbox.check_until
```

To avoid logging the same message twice, compare against nodes that already have the same `message.sender`, subject and `received_at`.
