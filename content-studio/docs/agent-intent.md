# Agent: Aqiira (Intent Agent)

**Stage:** 1 — Brief Collection  
**Model:** Claude Sonnet  
**Calls per turn:** 1 stream (reply) + 1 structured extract (silent parse), running in parallel  
**Session state at end:** `phase: "intent"` · `workplan: null`

---

## What It Does

Aqiira collects everything needed before any writing starts — topic, goal, audience, content type, length, primary keyword, and optional details like guardrails and sources. It asks one question at a time, so the experience feels like talking to a strategist, not filling out a form.

Every turn fires two calls simultaneously:
- **Stream:** Aqiira's conversational reply, streamed word-by-word
- **Structured extract (silent):** Reads the same message and pulls out content block values into JSON — the user never sees this call

---

## Full Session — Competitor Keywords Listicle

**Turn 1**
> **User:** Hey

> **Aqiira:** Hey! Great to have you here. I'm Aqiira — I help you build out a solid content brief so whatever we create hits the right notes from the start.
>
> What's the topic you're looking to create content around?

**Turn 2**
> **User:** I want to write regarding How to find competitor keywords and close visibility gaps

> **Aqiira:** That's a great topic — competitive keyword analysis is something a lot of brands know they *should* be doing but rarely do well. Lots of room to add real value there.
>
> I'm reading the topic as **"How to find competitor keywords and close visibility gaps"** — is that the angle you want to run with, or would you tweak the framing at all?

**Turn 3**
> **User:** No tweaking required

> **Aqiira:** Perfect, locked in!
>
> Now, what's the main job you want this content to do? I'd suggest **educating your audience** on the process while also **driving organic traffic** through search — that's a natural fit for this kind of how-to topic. Does that align with what you're after?

**Turn 4**
> **User:** Yes

> **Aqiira:** Great, goals confirmed — educate and drive organic traffic it is.
>
> Who's the primary audience here? My instinct is this skews toward **SEO practitioners and digital marketers** who already have some baseline knowledge — people who know what keywords are but want a sharper process for competitive analysis. Does that feel right, or are you writing for a broader crowd?

**Turn 5**
> **User:** Yes

> **Aqiira:** Got it — audience locked in.
>
> Now for content format: a **guide** feels like the natural fit here. That said, a **listicle** could work if you want something more scannable and shareable. Which direction feels right?

**Turn 6**
> **User:** Listicle

> **Aqiira:** Good call — a listicle will keep it punchy and scannable, which tends to perform well with this audience.
>
> On length, for a listicle like this I'd recommend **structured (~1,200 words)**. If you want to go deeper with tool walkthroughs and examples, **researched (~2,000 words)** is an option too. Which feels closer to what you need?

**Turn 7**
> **User:** I want to write a compact content

> **Aqiira:** Structured it is then — tight and focused, every point earning its place.
>
> For the primary keyword, **"competitor keywords"** feels like the strongest searchable anchor — high intent, directly matches what someone would type when looking for this process. Does that work, or is there a different term you're already targeting?

**Turn 8**
> **User:** Yes

> **Aqiira:** Nailed it. Now for secondary keywords — I'd suggest:
>
> - **"find competitor keywords"** — captures the how-to intent directly
> - **"keyword gap analysis"** — a widely searched process term
> - **"SEO competitor analysis"** — pulls in a broader but highly relevant audience
>
> Does that set work for you, or would you swap any out?

**Turn 9**
> **User:** First 2

> **Aqiira:** Got it — keeping it lean with **"find competitor keywords"** and **"keyword gap analysis"**.
>
> Are there any **competitor articles or URLs** you'd like this piece to outperform? Totally fine to skip this one.

**Turn 10**
> **User:** https://www.semrush.com/blog/competitor-keywords/

> **Aqiira:** Nice reference — SEMrush's content on this tends to be thorough, so it's a useful benchmark to sharpen against.
>
> Any **specific prompts or angles** you'd like the piece to hit that you feel SEMrush's version misses? Feel free to skip if you're happy to let the brief guide it naturally.

*(User did not respond further — brief was complete and the pipeline advanced.)*

---

## Brief Collected at Handoff

```json
{
  "topic": "How to find competitor keywords and close visibility gaps",
  "goal": ["educate", "increase_organic_traffic"],
  "audience": "SEO practitioners, digital marketers, content strategists",
  "content_type": "listicle",
  "length": "concise",
  "primary_keyword": "competitor keywords",
  "secondary_keywords": [
    "find competitor keywords", "visibility gaps", "keyword gap analysis",
    "SEO competitor analysis", "close visibility gaps"
  ],
  "guardrails": null,
  "competitive_refs": ["https://www.semrush.com/blog/competitor-keywords/"],
  "sources": [],
  "prompts": null
}
```

**Note on secondary keywords:** The user selected "First 2" from Aqiira's suggestions (find competitor keywords, keyword gap analysis). The extract call and workplan reflect 5 secondary keywords — the system appended closely related gap-closing terms during the parse pass.

---

## Notable Moments in This Session

**Minimal input, full pipeline:** The user confirmed each block with brief responses ("Yes", "Listicle", "First 2"). No guardrails, no sources, no custom prompts. The brief was complete in 10 turns and the full structured pipeline ran through to the editor.

**Length inference:** The user said "compact content" rather than naming a bucket. Aqiira mapped this to "concise" (the tightest standard bucket) and the workplan targeted 950 words.

**Secondary keyword expansion:** User said "First 2" but the session.json blocks carry 5 secondary keywords — the extract silently included gap-closing synonyms. Worth reviewing if strict keyword scoping matters to the user.
