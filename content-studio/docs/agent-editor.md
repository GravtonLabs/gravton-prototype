# Agent: Edit Agent

**Stage:** 5 — Human-in-the-Loop Editing  
**Model:** Claude Sonnet  
**Calls per round:** 1 text call (full draft in, full revised draft out)

---

## What It Does

The Edit Agent applies the human's instructions to the live draft. The editor types any instruction in plain language and the agent rewrites accordingly — tone, structure, length, specific sentences. Brand voice is always held constant. The deterministic rule checks re-run automatically after every edit.

---

## From This Session

The session is currently in the **editor** phase. The draft entered the editor at **13/43 checks (30.2%)**, with the primary failure pattern being secondary keyword density and H2 anchoring — not structural or voice problems.

The actionable failures at editor open:

```
❌ kw_density (primary):     0.52% (needs 1.0–1.5%)
❌ secondary_kw_in_h2:       5 secondary keywords not used as H2 anchors
❌ secondary_kw_density:     secondary keywords underrepresented across the draft
⚠  quotable:                "difficulty score of 20" — unsourced threshold
⚠  evidence:                "Competitor A / B" scenario not framed as hypothetical
```

---

## What the Edit Agent Handles — Post-Draft

### Edit Round 1 — Secondary Keyword H2 Anchoring

> **User:** The secondary keywords aren't in the headings. Fix that.

**Edit Agent approach:** Revise H2s to work secondary keywords into the heading text naturally without breaking the interrogative format.

**Selected heading revisions:**

| Original | Revised |
|----------|---------|
| "What Core Principles Guide Effective Competitor Keyword Analysis?" | "What Core Principles Guide an Effective Keyword Gap Analysis?" |
| "How Do You Find Competitor Keywords and Close Visibility Gaps?" | "How Do You Find Competitor Keywords and Close Visibility Gaps?" *(already contains primary + "close visibility gaps")* |
| "What Do Real Keyword Gap Analyses Look Like in Practice?" | unchanged — already anchors "keyword gap analysis" |
| "How Do You Measure Progress on Closing Visibility Gaps?" | unchanged |

**Rule check re-run:**
```
secondary_kw_in_h2: ✅ PASS — "keyword gap analysis" and "visibility gaps" now in H2s
```

**Aqiira:** *"H2 headings updated to anchor 'keyword gap analysis' and 'visibility gaps'. Rubric: 17/43. Remaining failures are keyword density — I can fix that in the next round."*

---

### Edit Round 2 — Keyword Density

> **User:** Fix the keyword density

**The problem:** Primary keyword "competitor keywords" appears ~5× in 964 words = 0.52%. Need 1.0–1.5% = approximately 10–15 occurrences.

**Selected insertions across the draft:**

| Location | Before | After |
|----------|--------|-------|
| Intro sentence | "Competitor keywords are the search terms…" | unchanged — already present |
| Section 2 body | "Mapping competitor keywords reveals demand…" | add: "Building a competitor keywords inventory also prevents…" |
| Section 4 step 3 | "Export competitor keyword data…" | "Export your competitor keywords data…" |
| FAQ answer 3 | "Use platforms that provide SERP overlap data…" | "Use platforms that provide competitor keywords data, SERP overlap…" |
| FAQ answer 1 | "Run a full analysis when you set quarterly…" | "Re-run your competitor keywords audit when you set quarterly priorities…" |

**Rule check re-run:**
```
kw_density (primary): ✅ PASS — now ~11× in 972 words = 1.13%
secondary_kw_density: ✅ PASS — secondary terms distributed with revised H2s + body insertions
```

**Aqiira:** *"Keyword density is now 1.1% — in range. Secondary keywords are anchored in headings and distributed across body copy. Rubric: 39/43. Remaining: the 'difficulty score of 20' sourcing flag and the Competitor A/B framing note."*

---

### Edit Round 3 — Evidence Framing

> **User:** Clean up those two warnings

**Before (quotable flag):**
```markdown
Terms below a difficulty score of 20 with transactional or informational intent
become first-tier targets.
```

**After:**
```markdown
Low-difficulty, high-intent terms become first-tier targets regardless of specific
tool thresholds — the exact cutoff depends on your domain authority and vertical.
```

**Before (evidence framing):**
```markdown
Consider a model scenario. Your domain competes against Competitor A and Competitor B.
```

**After:**
```markdown
Consider a hypothetical. Your domain competes against two organic competitors.
```

**Rule check re-run:**
```
quotable: ✅ PASS — unsourced threshold removed
evidence: ✅ PASS — scenario explicitly framed as hypothetical
```

**Aqiira:** *"Both warnings cleared. Rubric: 43/43. Draft is ready to export — MD, HTML, or TXT."*

---

## Cost — Edit Stage

| Call | Model | Tokens (in/out) | Cost |
|------|-------|-----------------|------|
| Edit round 1 (H2 anchoring) | Sonnet | ~2,100 / ~1,100 | ~$0.023 |
| Edit round 2 (keyword density) | Sonnet | ~2,100 / ~1,150 | ~$0.024 |
| Edit round 3 (evidence framing) | Sonnet | ~2,100 / ~1,050 | ~$0.022 |
| **3 rounds total** | | | **~$0.069** |

> Cost is low per round because the article is ~970 words. The full draft passes on both input and output on every call — there's no diffing or partial update.
