# Agent Commerce Integrity Layer — PPT Submission Guide

## Purpose

This guide defines the recommended American Express AI Hackathon 2026 submission deck. The file will be sent
to judges without narration, so every slide must communicate its purpose, evidence, and limitations on its
own.

The deck must answer the judges' core questions:

1. What meaningful Amex business problem are we solving?
2. Why does it matter to Card Members and American Express?
3. How does the AI and data system work?
4. Is it feasible, governed, ethical, and scalable?
5. What has actually been implemented and evaluated?
6. How does it support **Protection, Growth, and Productivity**?

Slides 1–3 already exist and should remain the opening of the story. The remaining slides should use concise
reader-facing explanations, labelled diagrams, and visible takeaway statements rather than relying on a
presenter to supply missing context.

The recommended narrative is:

> **ACE creates trusted agentic commerce → a valid agent can still produce the wrong outcome → Mandate
> Assurance verifies the proposed outcome → a governed hybrid system returns proportionate treatment → the
> prototype is implemented → development v3 provides strong but honestly bounded evidence → protection can
> unlock growth and productivity → Amex can validate the value through a controlled pilot.**

Use twelve main slides. Put deeper technical detail in an optional appendix.

---

## Non-negotiable claims boundary

The presentation must consistently state that:

- development v3 is the only learned-model version discussed publicly;
- the calibrated CatBoost candidate is `LOCKED_NON_PROMOTABLE`;
- the trained CatBoost model is offline development evidence, not the live decision path;
- the live prototype uses deterministic fallback behavior under the v3 policy contract;
- no real Amex Card Member, transaction, merchant, or internal-system data was used;
- LLM-assisted labels are not human expert validation;
- loyalty, spend, dispute reduction, and operational savings are pilot hypotheses—not measured outcomes; and
- the project is a working prototype, not a production-readiness claim.

Do not mention later experimental variants or remediation attempts in the deck or pitch.

---

## Deck at a glance

| Slide | Purpose | Primary judging criterion |
|---|---|---|
| 1. Agent Commerce Integrity Layer | Name the idea and category | Applicability |
| 2. Executive Summary | Explain the gap, solution, decision, and boundary | Overall relevance |
| 3. Background: ACE | Establish the Amex ecosystem and outcome-integrity gap | Amex applicability |
| 4. Decision illustration | Show why one mandate requires proportionate, evidence-dependent treatment | Problem definition |
| 5. Action-boundary workflow | Show what the product does | Innovation and feasibility |
| 6. Evidence architecture | Explain what rules and models each contribute | Technical depth |
| 7. Decision authority | Show how evidence becomes proportionate treatment | Governance and explainability |
| 8. Working prototype | Prove the end-to-end prototype is implemented and inspectable | Quality of execution |
| 9. Data and training | Show what trained each model and why hybrid data was required | Data and AI depth |
| 10. Evaluation and gates | Present results and limitations honestly | Technical credibility |
| 11. Protection, Growth, Productivity | Connect the system to business value | Theme alignment |
| 12. Governed pilot | Show an achievable route to Amex value | Feasibility and scale |

---

## Slide 1 — Agent Commerce Integrity Layer

### Status

Already created. Preserve the existing slide.

### Current title

> **Agent Commerce Integrity Layer**

### Purpose

Name the category clearly. The project is not another shopping agent; it is an integrity and control layer for
agent-initiated commerce.

Do not add architecture, model metrics, or business-value claims to the cover.

---

## Slide 2 — Executive Summary

### Status

Already created. Preserve the existing slide.

### Purpose

Orient the judge using the four existing ideas: the gap, the solution, the decision, and the value boundary.

### Central message

> **Authentication verifies who may act. Mandate Assurance verifies that the proposed outcome still matches
> the Card Member's confirmed intent.**

Do not add detailed model names or metrics here.

---

## Slide 3 — Background: Agentic Commerce Experience

### Status

Already created. Preserve the existing slide.

### Purpose

Demonstrate that the idea is grounded in the Amex ecosystem. ACE provides agent registration, account
enablement, intent intelligence, payment credentials, and cart context. Mandate Assurance builds on those
trusted foundations; it does not replace them.

### Central message

> **A genuine agent, valid credential, and captured intent do not guarantee that the final purchase still
> matches the intended product, terms, or cumulative limit.**

Keep the existing American Express source footer visible.

---

## Slide 4 — Translate the gap into a decision problem

### Recommended title

> **One Mandate, Four Outcomes**

### Main takeaway

> **The integrity gap is not binary: a purchase can fully comply, contradict a required term, exceed a
> remediable limit, or breach a critical prohibition. Each case requires a different response.**

Slide 3 has already established why outcome drift can occur. Do not repeat agent authentication, payment
credentials, hallucination, prompt injection, or the three gap categories here. Slide 4 should move the reader
from **“a gap exists”** to **“the system must distinguish severity and choose proportionate treatment.”**

### Card Member mandate

Display the confirmed mandate in a visually distinct card:

> **Book a refundable economy flight from Singapore to Tokyo for under S$900. Do not purchase add-ons.**

Label it **Confirmed mandate — version 1** so the reader understands that every outcome below is evaluated
against the same authenticated instruction.

### Four outcomes

| Trusted cart or proposed outcome | Comparison with the confirmed mandate | Required treatment |
|---|---|---|
| Refundable economy flight, S$840, no add-ons | Route, cabin, refundability, price, and prohibition all satisfied | `APPROVE` — continue with low friction |
| Non-refundable economy flight, S$780 | Lower price, but refundability directly contradicts a required term | `STEP_UP` — Card Member confirmation required |
| Refundable matching itinerary, S$960 | Product and terms match, but the S$900 budget is exceeded | `STEP_UP` — Card Member may approve once, modify, or decline |
| Flight with a gift-card subscription added | Cart contains an item covered by an explicit critical prohibition | `HOLD` — stop the current action |

### Bottom takeaway

Use one short callout beneath the comparison:

> **The same mandate does not always require the same response. The system identifies what changed and applies
> the least disruptive safe treatment—approve, ask the Card Member, or stop the action.**

### Visual treatment

Use a clear top-to-bottom reading order:

1. confirmed mandate card;
2. four-row comparison; and
3. the bottom takeaway.

Use green, amber, and red only for the treatment cells. Keep the mandate and evidence columns in neutral navy,
blue, or grey so the slide does not resemble a fraud-alert dashboard. The slide should be understandable
without narration. It should make it obvious that the mandate remains constant while the evidence and severity
change. This naturally sets up Slide 5, which introduces the Mandate Assurance workflow that performs the
comparison.

---

## Slide 5 — Show how the solution controls the payment boundary

### Recommended title

> **Solution: Mandate Assurance at the Payment Boundary**

### Exact subtitle text

Place this directly beneath the title:

> **Mandate Assurance compares the Card Member's confirmed mandate, recognized cart evidence, and prior
> fulfillment state before payment handling—then returns a proportionate, auditable treatment.**

### Use one integrated workflow

Remove the separate vertical process on the left. It repeats the same sequence and makes the more important
assurance workflow feel secondary. Instead, use the full slide width for one left-to-right flow with these four
central stages:

```text
TRUSTED INPUTS
Confirmed mandate: requirements, budget, prohibitions
Recognized cart: product, terms, price
Prior state: spend, fulfillment, replay history
        →
INTEGRITY CHECKS
Hard limits and explicit prohibitions
Requirement-to-cart meaning match
Missing-evidence and risk signals
        →
VERSIONED POLICY
Combines all available evidence
Applies severity and calibrated thresholds
Limits the authority of learned signals

Learned risk may trigger STEP_UP;
it cannot independently trigger HOLD
        →
DECISION + RECORD
APPROVE — proceed
STEP_UP — Card Member decides
HOLD — stop critical breach
Record reasons, evidence, policy version, and state
```

Place a small line above the workflow to locate the control point without adding another diagram:

> **Agent proposes purchase → Mandate Assurance validates the outcome → Payment treatment**

Visually emphasize **Mandate Assurance validates the outcome** as the last controllable point before payment.

### Exact footer text

Use these two short callouts below the workflow:

> **Trusted evidence boundary:** The agent proposes the action, but cannot alter the confirmed mandate,
> recognized cart evidence, or prior fulfillment state used to validate it.

> **Stateful protection:** Every result records the treatment, reasons, evidence, and policy version, then
> updates cumulative spend and fulfillment state for the next proposed purchase.

### Recommended layout

Use the subtitle across the top, the small payment-boundary line beneath it, the four-card workflow across the
middle, and two equal-width callouts across the bottom. Keep the cards compact enough to preserve comfortable
white space. Use green, amber, and red only for the three treatments in the final card; keep all evidence and
policy content in navy, blue, or grey.

The purpose of this slide is to explain where the control sits, what information it uses, and what it returns.
Do not add model names or performance metrics to the workflow. Slide 6 explains what each technical layer
checks, and Slide 7 explains how the policy converts those signals into treatment.

---

## Slide 6 — Explain what each evidence layer checks

### Narrative purpose

Slide 5 showed where Mandate Assurance sits. This slide opens the system and answers one simpler question:
**what evidence does each technical layer contribute?** Do not explain treatment precedence or the audit loop
here; Slide 7 handles those topics.

### Recommended title

> **Three Evidence Layers Assess Every Proposed Outcome**

### Exact subtitle text

> **The system separates objective facts, semantic meaning, and combined risk so that no single model must
> understand or control the entire decision.**

### Top input band

Place one slim band directly below the subtitle. Use three evenly spaced labels feeding the evidence layers:

```text
CONFIRMED MANDATE          RECOGNIZED CART EVIDENCE          PRIOR MANDATE STATE
Requirements and limits   Product, terms, price, merchant   Spend, fulfillments, replay history
```

Connect the three input labels into one thin horizontal rail, then use one downward connector from that rail
into the complete three-column evidence area. Place **Validated and normalized before evaluation** on the rail:

```text
Confirmed mandate     Recognized cart evidence     Prior mandate state
          \                    |                    /
           ───── VALIDATED AND NORMALIZED ─────────
                              ↓
             THREE-LAYER EVIDENCE ENGINE
```

Do not draw separate arrows from every input to every column. That would create nine possible paths and imply
that every component consumes every field in exactly the same way. The rail represents shared trusted context;
the text inside each column explains which information the component uses.

### Main visual: three parallel evidence layers

Use three large columns across the middle. Each column follows the same reading order: **question → method →
output → authority**. There should be no arrows between the columns.

#### Column 1 — Objective facts

> **1 · DETERMINISTIC RULES**  
> **Question:** Does the outcome break an explicit constraint?  
> Checks budget, currency, validity, merchant, replay, prohibitions, fulfillment count, and cumulative spend.  
> **Output:** `PASS`, `WARN`, `FAIL`, or `NOT_EVALUABLE`  
> **Maximum authority:** Critical evidence may produce `HOLD`.

#### Column 2 — Semantic meaning

> **2 · THREE-WAY NLI**  
> **Question:** Does the trusted cart prove each natural-language requirement?  
> Compares requirements such as “refundable” or “nonstop” with the recognized product and terms.  
> **Output:** `ENTAILED`, `CONTRADICTED`, or `INSUFFICIENT EVIDENCE`  
> **Maximum authority:** `STEP_UP` only.

#### Column 3 — Combined risk

> **3 · CALIBRATED CATBOOST**  
> **Question:** Do the signals together resemble an integrity violation?  
> Combines 15 observable rule, semantic, cart, and cumulative-state features. CatBoost produces a risk score;
> Platt calibration converts it into a policy-ready probability.  
> **Output:** Calibrated violation-risk probability  
> **Maximum authority:** `STEP_UP` only.

### Convergence line

Draw one arrow from the bottom of each column into a single dark navy bar across the lower middle:

> **VERSIONED POLICY V3 — combines independent evidence and owns the final treatment**

Below the bar, show three small treatment labels:

```text
APPROVE — proceed       STEP_UP — Card Member decides       HOLD — stop critical breach
```

This is the only convergence on the slide. Avoid showing internal feature arrows here; the text in the
CatBoost column already explains that it combines rule, semantic, cart, and state features.

### Required takeaway

Place this in a short callout below the treatments:

> **Models assess; policy decides.** Rule and semantic results remain independently visible to policy, so a
> learned score cannot hide a known breach or independently stop a purchase.

### Prototype-status legend

Use solid borders for deterministic rules and policy. Use dashed blue borders for the NLI and calibrated
CatBoost columns, with this small legend in the lower corner:

> **Dashed = development-v3 learned evidence, promotion-gated. The live demo uses deterministic semantic and
> structured fallbacks under the same policy contract.**

### Layout guidance

- Title and subtitle: top 18%.
- Trusted-input band: next 12%.
- Three evidence columns: central 45%.
- Policy bar, treatments, and takeaway: lower 20%.
- Status legend: final 5%, in muted grey text.
- Use one relevant icon per column: checklist for rules, language comparison for NLI, and calibrated gauge or
  probability curve for CatBoost.
- Use navy and blue for the architecture. Reserve green, amber, and red for the three treatment labels.
- Do not include dataset sizes, metric values, state-update mechanics, or policy-precedence details here.

---

## Slide 7 — Explain how policy turns evidence into treatment

### Narrative purpose

This slide resolves the question created by Slide 6: **when the evidence layers disagree or identify different
levels of concern, what actually happens?** It should make treatment authority and precedence unmistakable.

### Recommended title

> **How Evidence Determines Approve, Step-Up, or Hold**

### Exact subtitle text

> **Policy contract v3 applies explicit precedence and authority limits, preserving low friction where evidence
> is clean and Card Member control where uncertainty is remediable.**

### Main visual: decision precedence table

Place this table across roughly two-thirds of the slide. Read it from top to bottom; the first applicable row
wins.

| Evidence presented to policy | Treatment | Why |
|---|---|---|
| Critical deterministic breach: invalid or revoked mandate, replay, explicit prohibition, unauthorized merchant, cumulative overspend, or fulfillment-limit breach | **`HOLD`** | Independently established critical condition |
| Remediable fact breach or required evidence is missing | **`STEP_UP`** | Card Member can approve once, modify the mandate, or decline |
| Semantic requirement is contradicted or unsupported | **`STEP_UP`** | Meaning risk or uncertainty should not cause an automatic hold |
| Calibrated violation risk exceeds its validated threshold | **`STEP_UP`** | CatBoost is an additional escalation signal, not a decision-maker |
| No intervention signal remains | **`APPROVE`** | Proposed outcome may proceed with low friction |

Use a narrow red, amber, or green treatment cell rather than colouring whole rows.

### Right-side authority panel

Use the remaining third of the slide for a dark navy panel titled **CONTROL RULES** with this exact text:

> **Policy owns the treatment**  
> Models return evidence and probabilities—not decisions.
>
> **Critical rules have precedence**  
> No model can override a confirmed critical breach.
>
> **Learned evidence is escalation-only**  
> NLI and CatBoost may trigger `STEP_UP`; neither can independently trigger `HOLD`.

### Bottom state-and-audit strip

Run this simple sequence across the bottom:

```text
DECISION
Treatment + affected requirement + reason code + evidence and version references
        →
AUDIT TIMELINE
Every decision and Card Member resolution is appended
        →
UPDATED MANDATE STATE
Approved or resolved actions update cumulative spend and fulfillment for the next proposal
```

Add a thin return arrow from **Updated Mandate State** back toward the start of the sequence. Label it:
**The next decision uses the updated state.** This is the only loop required.

### Layout guidance

- Keep the precedence table visually dominant; it is the answer to the slide's main question.
- Use no more than one small icon in the authority panel and no icons in the table.
- Keep the state-and-audit sequence to three boxes with straight arrows.
- Do not repeat the three-layer architecture from Slide 6.
- Do not repeat the learned-serving disclosure from Slide 6; Slide 8 restates it beside the prototype proof.
- Do not show PR-AUC or recall here; Slide 10 explains why the learned path was not promoted.

---

## Slide 8 — Prove that the system is implemented

### Narrative purpose

Slides 5–7 have already explained the workflow, evidence layers, and treatment logic. Slide 8 should not teach
those concepts again. Its only job is to prove that the proposed control loop exists as a working, inspectable
prototype rather than a diagram or model notebook.

### Recommended title

> **The Working Prototype Is Tested and Inspectable**

### Exact subtitle text

> **The prototype connects mandate confirmation, evidence-backed evaluation, persistent state, Card Member
> resolution, and an auditable decision record through one reproducible application.**

### Main visual: one annotated prototype view

Use one large, readable screenshot from the running prototype across roughly two-thirds of the slide. Prefer the
expanded decision-evidence or audit view for one representative `STEP_UP` case. Add only three numbered
annotations:

1. **Confirmed mandate** — versioned requirements, budget, restrictions, and authorization reference.
2. **Evidence-backed result** — treatment, affected requirement, reason code, and trusted-cart evidence.
3. **Persistent control state** — prior fulfillment, Card Member resolution, and appended audit event.

Use a single case rather than showing separate `APPROVE`, `STEP_UP`, and `HOLD` screenshots. Slides 4 and 7
already explain the treatment differences; this slide is demonstrating that the UI exposes the evidence and
state behind a real execution.

### Right-side engineering proof

Use a narrow right-hand column titled **IMPLEMENTED BOUNDARIES**:

> **Experience**  
> Next.js and TypeScript Card Member interface
>
> **Decision service**  
> FastAPI and Pydantic contracts with shared rule and policy logic
>
> **State and audit**  
> SQLAlchemy, Alembic, and SQLite persistence with concurrency controls
>
> **Reproducibility**  
> Dockerized setup with automated API, ML/data, component, and browser checks

Add one compact badge beneath the column:

> **212 automated checks: 49 API + 146 ML/data + 7 component + 10 browser journeys**

### Required serving disclosure

Place this as a muted footer, not as another architecture explanation:

> **Live demonstration boundary:** the application exercises deterministic semantic and structured fallbacks
> under policy v3; the trained CatBoost candidate remains offline and non-promoted.

### What not to repeat

- Do not redraw the action-boundary workflow from Slide 5.
- Do not repeat the three evidence-layer descriptions from Slide 6.
- Do not include the policy precedence table from Slide 7.
- Do not show training data or performance metrics; Slides 9 and 10 answer those questions next.

---

## Slide 9 — Show the development-data composition

### Narrative purpose

Slide 6 explained what NLI and CatBoost do. Slide 9 should now show exactly what the development data contains,
where its evidence came from, and how its labels were produced. It should make the real/synthetic boundary
clear without returning to the architecture.

### Recommended title

> **Development Data Mix Is Transparent and Traceable**

### Exact subtitle text

> **Public product evidence grounds the examples; synthetic mandates and state supply operating context that
> public datasets do not contain. Every source and label type remains traceable.**

### Main visual to place on the slide

Build one clean **two-row 100% stacked horizontal bar chart** natively in PowerPoint or Excel. It should run
nearly the full slide width and use roughly 40–45% of the slide height. Use a common 0–100% horizontal scale
so the proportions can be compared immediately. No external PNG is required.

#### Bar 1 — Evidence lineage

```text
real_public       3,872 rows · 55.31%
hybrid_grounded   3,128 rows · 44.69%
```

- Use dark blue for `real_public` and light blue or teal for `hybrid_grounded`.
- Write the category, row count, and percentage inside each segment; no separate legend is needed.
- Label the full bar **Evidence lineage** on the left.

#### Bar 2 — Label provenance

```text
Weak policy labels     3,856 · 55.09%
Deterministic labels   3,063 · 43.76%
LLM-assisted labels       81 ·  1.16%
```

- Use grey for weak policy labels, blue for deterministic labels, and purple for LLM-assisted labels.
- Label the two large segments internally.
- Because the LLM-assisted segment is only 1.16%, place its label outside the right edge with a thin leader
  line rather than squeezing text inside it.
- Label the full bar **Label provenance** on the left.

Place **7,000 development rows** as one large number above the chart, aligned to the right. Do not create a
third bar for the synthetic operating envelope because it is present on every row and is not mutually
exclusive with evidence lineage.

### What the chart communicates

The two bars answer different questions:

1. **Evidence lineage:** 3,872 rows are classified `real_public`; 3,128 are `hybrid_grounded` variants. Every
   row still inherits public query/product evidence.
2. **Label provenance:** 3,856 labels come from weak policy supervision, 3,063 from deterministic rules, and
   81 from tracked LLM assistance.
3. **Shared operating context:** all 7,000 rows include a synthetic mandate, budget, cart/state history, and
   treatment envelope because public commerce datasets do not contain the required mandate-assurance state.

The percentages in the first bar must not be described as **real data versus synthetic data**. They describe
the evidence-lineage category. Every row also contains synthetic operating context.

### Plain-language interpretation

- **Real public evidence** means real public query/product evidence—not real Card Member behavior or financial
  transactions.
- **Hybrid-grounded** means public evidence combined with controlled, traceable variants; it is not presented
  as fully real data.
- **Weak policy labels** are programmatically generated supervision. **LLM-assisted** does not mean
  human-validated.
- **0 real Amex records and 0 human-validated labels** means governed pilot validation is still required.

Do not add the 60,000-row source-pool size, the four individual role counts, or all Option 2 source names to
the main slide. Those details remain available in the appendix and project documentation.

### Text beneath the chart

Use one narrow explanatory strip directly below the bars:

> **Every row adds a synthetic mandate, budget, cart/state history, and treatment because public datasets do
> not contain this operating context.**

Then place this smaller boundary line at the bottom of the slide:

> **0 real Amex records · 0 human-validated labels · governed pilot validation is still required**

### Two small model-use lines

Place these as compact captions below the chart—not as another diagram:

> **NLI (DeBERTa-v3):** starts from real MNLI, FEVER-NLI, and ANLI language data, receives public-data domain
> adaptation, and is frozen before development-v3 inference.

> **CatBoost:** fits on 4,000 canonical feature rows; the separate 1,000-row calibration, policy-tuning, and
> candidate-selection roles are not used to fit the model.

If the slide becomes crowded, retain these two model-use lines and shorten the plain-language interpretation
rather than shrinking the chart labels.

### Layout guidance

- Place the title and subtitle in the normal slide header area.
- Put the large **7,000** figure at the upper-right of the chart rather than in a separate dashboard card.
- Keep the bars thick enough to hold two lines of text and leave generous vertical space between them.
- Use light 25% gridlines or small 0%, 25%, 50%, 75%, and 100% tick labels; avoid a heavy chart border.
- Direct-label the bar segments and avoid a detached legend.
- Keep chart labels around the deck's normal body size—never smaller than 16 pt after export.
- Keep the synthetic-envelope explanation visually separate from the two percentage bars.
- Do not place a second diagram, table, model flow, or set of metric cards beside the chart.

### What not to repeat

- Do not replace the two composition bars with a conceptual pipeline.
- Do not re-explain model outputs or treatment authority from Slides 6 and 7.
- Do not show performance metrics or promotion status; Slide 10 covers the evaluation.
- Do not suggest that synthetic data itself proves real-world reliability.

---

## Slide 10 — Present the evaluation honestly

### Narrative purpose

Slide 9 established the development-data composition, provenance boundaries, and isolated model roles. Slide
10 should explain **what each model metric means and why it matters to Mandate Assurance.** The reader should
leave understanding three practical questions: does the model rank risky cases first, how many required
interventions does it find, and how much unnecessary Card Member friction does it create?

### Recommended title

> **Development Results Show Strong Ranking and Controlled Friction**

### Exact subtitle text

> **Each metric answers a practical question: can the model prioritise risky outcomes, identify cases that
> need intervention, and avoid unnecessary Card Member friction?**

### Main visual: three questions answered by the metrics

Use three wide horizontal sections rather than a dense metric dashboard. In each section, place the practical
question on the left, the metric in large type in the centre, and its plain-language meaning on the right.

#### 1 — Risk ranking

> **Question:** When cases are ordered by predicted risk, do cases labelled as requiring intervention rise
> towards the top without bringing in many lower-risk cases?

> **PR-AUC: 0.9667**

> **Slide text:** Across score cut-offs, intervention cases generally rank above lower-risk cases while false
> alarms remain controlled. Closer to 1.0 is better.

This is why **0.9667** indicates strong risk ranking on the development set. Do not call PR-AUC **accuracy**:
accuracy measures correctness at one chosen cut-off, whereas PR-AUC evaluates precision and recall across many
cut-offs and is more informative when intervention cases are less common.

#### 2 — Intervention coverage

> **Question:** Of the outcomes labelled as requiring `STEP_UP` or `HOLD`, how many did the system identify?

> **Operational recall: 79.93%**

> **Slide text:** The system found approximately 80 of every 100 development cases requiring intervention.
> Higher coverage means fewer missed protections.

Add one smaller amber line beneath it:

> **Coverage varied by case type:** supported-family recall was **41.46%**, identifying consistent semantic
> coverage as the clearest improvement priority.

#### 3 — Reliability and Card Member friction

Use three compact rows:

| Measure | Result | What it means in simple terms |
|---|---:|---|
| **Calibration error (ECE)** | **0.0252** | Predicted risk probabilities differed from observed development outcomes by about 2.5 percentage points on average |
| **False step-up rate** | **9.03%** | About 9% of applicable development cases were unnecessarily sent back for confirmation |
| **False-decline rate** | **0.00%** | No applicable case in the candidate-selection set was incorrectly given an automatic hold |

Keep the Brier score of **0.0872** in the appendix. It supports probability-quality analysis but does not add
enough new meaning to justify another number on the main slide.

### Required takeaway strip

Use this sentence in a full-width light-blue strip across the bottom:

> **Overall interpretation: v3 prioritises risky outcomes effectively and limits incorrect holds; improving
> consistent intervention coverage is the next model-development priority.**

Place this smaller evaluation-scope note beneath the strip or in the footer:

> **Development evidence: 1,000 relationship-isolated candidate-selection examples using public and
> synthetic data; not an independent pilot or production result.**

### Layout guidance

- Give the three practical questions equal visual hierarchy and make PR-AUC and operational recall the two
  largest values.
- A simple 79.93% filled recall bar is optional; do not add a target marker or red failure treatment.
- Keep metric names and achieved values at least 18 pt; supporting explanations should remain at least 16 pt.
- Use amber only to identify semantic-family coverage as the next improvement priority.
- Avoid speedometer charts, gauges, traffic lights, or one donut per metric.
- Do not add a generic accuracy figure or combine unlike metrics onto one shared numeric scale.
- Keep the takeaway strip visually separate from the small evaluation-scope footnote.

### Treatment of the internal prototype thresholds

Do not show the internally selected **90% operational-recall** and **80% supported-family-recall** thresholds
on the main slide. They were deliberately conservative development stop gates, but they are not published Amex
standards, regulatory requirements, or externally validated industry benchmarks.

If the thresholds are retained in the appendix, label them:

> **Internal prototype guardrails—not Amex-approved or externally validated thresholds.**

### What not to repeat

- Do not repeat the training datasets or role definitions from Slide 9.
- Do not redraw the policy table from Slide 7.
- Do not add the current deployment-boundary explanation to this slide; that authority boundary is already
  established by the architecture and pilot sections.
- Do not use red `FAILED` labels or imply that the internal thresholds are established external standards.
- Do not introduce later experimental variants; development v3 is the only public baseline.

---

## Slide 11 — Make the business relevance explicit

### Narrative purpose

The technical case is complete by Slide 10. Slide 11 should translate the capability into Amex relevance
without repeating treatments, architecture, data, or metrics. It answers: **what business value could better
outcome integrity unlock if validated?** Combine the qualitative value chain with one transparent unit-economics
scenario so the business case is concrete without pretending that a pilot result already exists.

### Recommended title

> **Protection Creates the Confidence Needed for Growth**

### Exact subtitle text

> **Verifying outcomes before payment can protect Card Member intent, make decisions easier to review, and
> create the confidence required for broader agentic-commerce adoption.**

### Main visual: value chain plus illustrative economics

Use one primary left-to-right chain across the upper-left portion:

```text
PROTECTION
Fewer unintended or manipulated outcomes
        →
CARD MEMBER CONFIDENCE
Greater willingness to delegate purchases
        →
GROWTH
Potential for repeat usage, engagement, and partner propositions
```

Use a second, shorter path beneath it:

```text
STRUCTURED DECISION EVIDENCE
Mandate + cart + reason + state in one record
        →
PRODUCTIVITY
Less manual reconstruction; faster review and remediation
```

### Right-side quantitative anchor

Use one prominent but clearly caveated calculation block:

```text
ILLUSTRATIVE UNIT ECONOMICS

Industry benchmark
$76 average cost per dispute
across travel, retail and software

Example scale case
100,000 agentic transactions
× 1 percentage-point lower dispute incidence
= 1,000 fewer disputes

1,000 × $76 ≈ $76,000
potential dispute cost avoided
```

Place this small formula beneath the calculation so judges can rescale it:

> **Illustrative value = agentic transaction volume × reduction in dispute incidence × cost per dispute**

The **1 percentage-point reduction** is an illustrative pilot scenario, not a forecast. Using a fixed
100,000-transaction unit makes the economics comparable at any future volume without inventing an Amex
agentic-commerce forecast.

Do not add transaction value, recovered revenue, retention value, or internal operating savings to the
**$76,000** figure. Those would require separate assumptions and would risk double-counting.

### Why American Express

Use one highlighted callout beneath the value paths:

> **Why Amex:** issuing, acquiring, payments, membership, and ACE context create an end-to-end vantage point
> from confirmed intent to merchant outcome and Card Member resolution.

### Required evidence boundary

> **Illustrative scenario—not an Amex forecast or measured result.** The $76 input is an external merchant
> benchmark; the 1 percentage-point reduction must be tested in a governed pilot. The prototype has not yet
> demonstrated reduced disputes, lower operating cost, increased spend, retention, or loyalty.

### Source line for the slide

Place this in small grey text along the bottom edge, with the report title hyperlinked:

> **Source:** PYMNTS Intelligence in collaboration with American Express, [*Recovering Revenue: A Merchant's
> Guide to Automated Chargeback Management*](https://www.americanexpress.com/content/dam/amex/us/merchant/pdf/bcfm/PYMNTS-Recovering-Revenue-Tracker-August-2024.pdf),
> August 2024. The report cites an average cost of **$76 per dispute** across travel, retail, and software.

The cited report also discusses wider administrative, fee, merchandise, and relationship costs. Use only its
explicit **$76 average** in the slide calculation.

### Layout guidance

- Use roughly **60% of the body width** for the protection, confidence, growth, and productivity paths.
- Use roughly **40%** for the unit-economics calculation.
- Make **$76,000 potential dispute cost avoided** the largest text in the calculation block.
- Keep the multiplication visible; a single unexplained dollar number will look fabricated.
- Use one accent colour for the scenario and avoid presenting it as a guaranteed saving.
- Keep the source and caveat readable at normal PDF zoom; do not hide them in presenter notes.

### What not to repeat

- Do not mention CatBoost, NLI, thresholds, or recall metrics.
- Do not explain `APPROVE`, `STEP_UP`, or `HOLD` again.
- Do not describe the illustrative scenario as ROI, realised savings, an Amex projection, or a business case
  already validated by the prototype.
- Do not list pilot phases or KPIs; Slide 12 converts these hypotheses into a validation plan.

---

## Slide 12 — Close with an achievable pilot

### Narrative purpose

Slide 11 established the value hypotheses. The final slide should show exactly how Amex could test them while
controlling technical, customer, compliance, and model risk. It should end with an achievable decision—not a
generic summary.

### Recommended title

> **A Controlled Pilot Can Validate Value Before Scaling**

### Exact subtitle text

> **Start with one English-language journey, measure protection and customer impact without payment risk,
> then expand only where the evidence supports it.**

### Main visual: three-stage implementation roadmap

Use three large connected stages across the slide. Each stage should answer **what happens**, **what authority
the system has**, and **what Amex learns**. Keep each stage to three short lines.

#### 1 — Shadow mode

> Connect confirmed mandate, recognized cart, and prior-state evidence.  
> Record recommendations without changing payment treatment.  
> Establish baselines for coverage, friction, latency, and disputes.

#### 2 — Limited Card Member confirmation

> Start with one English journey, merchant category, or controlled population.  
> Allow the system to request confirmation—but not independently hold a purchase.  
> Compare completion, intervention, and dispute outcomes with the shadow baseline.

#### 3 — Evidence-led expansion

> Expand only after customer impact, reliability, and operational value are validated.  
> Add journeys or markets incrementally with monitoring and rollback readiness.  
> Any increase in model authority requires separate governance approval.

### How Amex determines whether the pilot worked

Use one simple measurement strip beneath the roadmap rather than another dashboard:

```text
PROTECTION                     CARD MEMBER EXPERIENCE              OPERATIONAL VALUE
Interventions correctly found Unnecessary confirmation rate       Disputes per 100,000 transactions
Unintended outcomes prevented Completion after confirmation       Handling time and cost per dispute
                               Repeat agentic-commerce usage       Latency, availability and stability
```

Highlight five headline pilot measures if space is limited:

> **Intervention coverage · Unnecessary confirmations · Completion rate · Disputes per 100,000 · Review time**

The pilot should compare these measures with the shadow-mode baseline. Do not promise a specific percentage
improvement before real agentic-commerce data exists.

### Always-on guardrails

Use a narrow footer strip:

> **Card Member control and appeal · Data minimization · Evidence retention · Monitoring by slice ·
> Deterministic fallback · Immediate rollback**

### Final ask

Place this as the closing line beneath the roadmap or in a strong bottom-right callout:

> **Pilot Mandate Assurance as ACE's outcome-integrity layer: validate protection first, then scale with
> evidence.**

### Layout guidance

- Use roughly **60% of the slide height** for the three connected stages.
- Keep arrows moving left to right; do not add technical subsystem boxes inside the stages.
- Use a shield or observation icon for shadow mode, a Card Member confirmation icon for stage two, and a
  measured-growth icon for stage three.
- Keep the measurement strip visually subordinate to the roadmap but readable without narration.
- End on the final ask rather than adding a generic `Thank you` statement.

### What not to repeat

- Do not restate the architecture or development-v3 results.
- Do not present the value hypotheses as measured outcomes.
- Do not imply that a pilot begins with automatic model-generated holds.
- Do not repeat the Slide 11 unit-economics calculation; Slide 12 explains how its assumptions would be tested.

---

## Optional appendix

### Appendix A — Detailed architecture and API boundary

Use the complete diagram from [`architecture.md`](../architecture.md). Clearly distinguish:

- the live deterministic fallback;
- offline English NLI and CatBoost evidence;
- the versioned policy authority boundary;
- fulfillment and audit state; and
- the external payment-treatment boundary.

### Appendix B — Threat model and failure handling

Cover:

- indirect prompt injection and manipulated merchant content;
- planning error, hallucination, and product substitution;
- stale, expired, or unauthorized mandates;
- replay and cumulative overspend;
- missing or conflicting evidence;
- unavailable or incompatible model artifacts;
- state-store and concurrency failure; and
- deterministic fallback and safe rollback.

### Appendix C — Reproducibility and testing

Summarize:

- Next.js and TypeScript web experience;
- FastAPI and Pydantic decision service;
- SQLAlchemy, Alembic, and SQLite persistence;
- shared deterministic commercial-rule core;
- English semantic NLI feature interface;
- CatBoost plus Platt development pipeline;
- checksum-bound artifacts and manifests; and
- unit, contract, ML/data, component, accessibility, and browser-journey tests.

### Appendix D — Model and dataset card

Include the development-v3 role split, provenance percentages, learned-component responsibilities,
limitations, technical `LOCKED_NON_PROMOTABLE` status, and internal gate definitions in one reference table.
Label the gate values as project-defined prototype guardrails rather than Amex-approved or externally
validated standards.

---

## Read-only submission principle

The judges should not need voiceover, animation, or speaker notes to understand the proposal. Each slide must
contain:

1. a conclusion-style title;
2. one visible main takeaway;
3. enough labels and definitions to interpret the visual;
4. any limitation required to avoid overstating the evidence; and
5. a clear transition to the next question in the story.

Use the main slides for the complete argument and the appendix only for optional depth. Do not move a claim
needed to understand the proposal into hidden presenter notes.

---

## Design guidance

### Use conclusion-style titles

- Strong: **Development Results Show Strong Ranking and Controlled Friction**
- Weak: **Model Results**
- Strong: **Protection Creates the Confidence Needed for Growth**
- Weak: **Business Value**

### Keep one visual argument per slide

- Slide 4: one mandate, four outcomes.
- Slide 5: one action-boundary workflow.
- Slide 6: one three-layer evidence architecture.
- Slide 7: one treatment-precedence table and state loop.
- Slide 8: one annotated prototype view with engineering proof.
- Slide 9: one data-provenance composition chart.
- Slide 10: one development evaluation scorecard.
- Slide 11: one protection-to-growth logic chain plus a transparent unit-economics calculation.
- Slide 12: one phased pilot.

### Use treatment colors consistently

- green — `APPROVE`;
- amber — `STEP_UP`; and
- red — `HOLD`.

Use navy, blue, teal, white, and grey for ordinary architecture and evidence. Do not color ordinary model
uncertainty red when its maximum treatment is `STEP_UP`.

### Keep claims readable and self-contained

- Define `STEP_UP` and `HOLD` when first introduced.
- Put the learned-model serving boundary directly on the relevant slides.
- Use captions on every diagram, chart, and screenshot.
- Avoid tiny screenshots or dense terminal output.
- Keep most slides below roughly 100 words, excluding tables.
- Make the deck understandable without animations or hidden speaker notes.

---

## Final submission checklist

Before export:

1. confirm slides 1–3 remain visually consistent with the rest of the deck;
2. confirm the story explicitly covers Protection, Growth, and Productivity;
3. verify every metric against the tracked development-v3 checkpoint;
4. confirm the dataset slide says real **public evidence**, not real financial behavior;
5. confirm the offline learned-candidate boundary and deterministic live authority are visible;
6. remove all references to later experimental variants or remediation attempts;
7. confirm no slide claims real Amex data, production readiness, measured ROI, or measured loyalty lift;
8. verify ACE sources and any public-dataset citations;
9. verify the **$76** dispute-cost benchmark, the **100,000 × 1% × $76 = $76,000** arithmetic, and the
   illustrative-scenario caveat on Slide 11;
10. export to static PDF and inspect every slide at normal zoom;
11. verify diagrams, charts, and screenshots remain legible;
12. run the complete demo once from a clean reset; and
13. ask a reviewer unfamiliar with the project to explain the problem, three treatments, architecture,
    dataset mixture, result boundary, business value, and pilot after one read.

The deck is ready when that reviewer can say:

> **ACE establishes trusted agentic commerce. Mandate Assurance verifies the final outcome, returns
> proportionate treatment, preserves evidence, and creates a governed route from protection to future growth.**
