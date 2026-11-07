# Gates

A gate is any step where moving forward needs the user's identity, account, money or voice. The agent never passes a gate on its own, on the taken path or on any branch. `fh.py capture` detects most gates and prints `GATE: <kind>`. Some gates it can't see, such as a JS-only modal or a "book a call" calendar. Watch for those yourself.

| Gate | Detected by | Ask the user | Never |
|---|---|---|---|
| `email` | email input in a form or on its own | "This page asks for an email. Do you want to (a) enter your funnel-research address yourself while I record, (b) let me enter <the address you approved for this run>, or (c) stop this path here?" | Use the user's personal email unless they explicitly say so for this run |
| `phone` | tel input or a phone/SMS field | Same choices. Recommend a research number (a VoIP or second SIM). | Enter any number without approval |
| `login` | password field, or a sign-in page | "This needs a login. Do you want to sign in yourself in the shared browser, or should I stop here?" | Type, store or reuse passwords or cookies |
| `payment` | card fields, a Stripe/PayPal iframe, or checkout words | No question about paying. Capture the page, then ask **"Is this the end of the funnel?"** | Click pay, buy, complete order or "yes, add" on an upsell |
| `message` | DM or comment-to-get CTAs ("comment GUIDE", "DM me") | "Getting this needs a DM or comment from your account. Do you want to send it yourself and forward me the reply?" | Send anything as the user |
| `booking` | Calendly or a typeform application | "Booking or applying sends your details to them. Do you want to do it yourself, or stop here?" | Submit an application or booking |

## Logging

Log every decision so the timeline shows why the path continued or stopped:

```bash
FH event <run> gate_decision "User chose (a): entered research email on n2 at 14:02" --node n2
FH capture <run> <thank-you-url> --parent n2 --trigger "form submitted by user" --cta "Download"
```

If the user passes a gate in their own browser, ask for the URL they landed on. If the URL can't be fetched without their session (it is personalized or tokenized), ask for screenshots instead. Then log the page with `add-node --type thank-you --channel web --screenshot ...`. Never store tokens from personalized URLs in `analysis.md` or the report. Redact them in the node's `url` field (`annotate` with `{"url": "...redacted..."}`).

## Option (b): agent types the approved research address

This is allowed only after the user approves it for this run, in this conversation, and names the address. Log the approval as a `gate_decision` event first. Use `agent-browser` to `fill` the email field. Submitting is still a gate step, so confirm once more right before you click submit. Name the address in that `gate_decision` event. It must be a research address, never a personal one.
