---
name: metric-explainer
description: Flow 4 of the Opportunity Engine — plain-language explanation of any visibility metric and how it relates to the others. Load when the user asks educational metric questions like "what is presence / share of voice / position / sentiment / consistency?", "how are metrics A and B connected?", "do these need to move together?", "how is A different from B?", "how do I make sense of A, B and C together?", or "why is my share of voice lower than my presence?". Produces a clear explanation of what the metric is, what the user's own number means, and how it connects to or differs from related metrics.
---

# Flow 4 — Ask about any metric

On demand and educational. Metrics like presence, share of voice, position, sentiment, and
consistency confuse people, and a single number rarely means much alone. Explain it in plain
language, tell the user what *their* number means, and — this is the heart of the flow — explain how
metrics relate to each other when that helps them understand their situation.

## Input
A metric question in plain language, started from a metric label or typed in chat.

## Output
A plain-language explanation covering:
- **What the metric is** — in one or two sentences, no jargon.
- **What the user's number means** — pull their actual value and interpret it (good/weak, relative
  to competitors) rather than just defining the term.
- **How it connects to or differs from related metrics** — the relationship that explains their
  situation.

## Method
1. **Get the definition right.** Load the `insights-metrics` skill — it is the authoritative source
   for what each metric is, how it's computed, its buckets and thresholds. Do not improvise formulas
   or cut-offs. Use `org-knowledge-base` for the plain-English framing.
2. **Translate to plain language.** Strip the math down to the idea. Presence = *are you mentioned
   at all*. Share of voice = *how much of the answer you own versus competitors*. Position = *how
   early/prominently you're mentioned* (lower rank is better). Sentiment = *how favourably you're
   framed*. Consistency = *whether you get the same answer every time*.
3. **Make it about their number.** Query the user's current value (and a comparison point — prior
   run or top competitor) so the explanation is concrete: "yours is 0.18, competitors average 0.40."
4. **Explain the relationships when they clarify the situation:**
   - Presence vs SoV — you can be present (mentioned) yet have low SoV (you're named briefly while
     competitors dominate the same answer).
   - Position vs SoV — being mentioned first (good position) but rarely (low SoV) tells a different
     story than being mentioned often but late.
   - Sentiment vs visibility — high visibility with negative sentiment can be worse than modest
     visibility with positive framing.
   - Consistency vs presence — a brand absent in every run shows misleadingly "consistent"; that's a
     visibility problem, not stability (per the `insights-metrics` caveat).
   Only bring in the relationships that help; don't dump the whole web of metrics.
5. **Answer the actual question shape** — "what is A" (define + their number), "A vs B" (contrast),
   "A and B connected" (relationship), "make sense of A, B, C" (a short combined reading).

## Guardrails
- Always defer to `insights-metrics` for definitions, buckets, and thresholds — never invent them.
- Keep it educational and plain; avoid restating formulas unless the user wants the math.
- Read-only; you're explaining, not changing data.
- If the user pivots from "what does this mean" to "why did it move," that's Flow 2
  (`change-deep-dive`); to "how do I improve it," Flow 3 (`fix-prompts`).

## Example
The user asks why their share of voice is lower than their presence. You explain: presence means
they get mentioned; share of voice means how much of the answer they own. Theirs is lower because
they're named only briefly while competitors dominate the same answers — and you back it with their
two numbers and the competitor who's eating the share.
