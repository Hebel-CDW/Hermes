# Hermes — ElevenLabs voiceover (manager demo)

**Audience:** a VP or non-tech manager  
**Tone:** first person, calm, specific. You are showing a working prototype, not pitching vapour.  
**Length:** ~4 minutes 30 seconds at 145–155 words/minute  
**Data:** synthetic demo people. Scoring ran on coded tokens. Names are a display overlay.

This file is the recording bible. Spoken words live in **Tracks**. Clicks live in **Director**. Do not read the director notes into ElevenLabs.

---

## Voice settings (ElevenLabs)

| Setting | Value | Why |
|---|---|---|
| Voice | A mid register, unhurried professional. Prefer a UK or measured US news-anchor voice over a “trailer guy.” | The content is evidence, not hype. |
| Model | Eleven Multilingual v2 or Eleven v3 | Stable narration, clean numbers. |
| Stability | 55–65 | Enough variation to sound human, not a radio advert. |
| Similarity | 75–80 | Keep timbre consistent across tracks. |
| Style exaggeration | 10–20 | Almost off. Specificity does the work. |
| Speed | 0.95–1.00 | Leave air after numbers. |
| Output | 48 kHz WAV, then duck under UI SFX in the edit | |

Generate **one track at a time**. Concatenate in the editor against the click sheet. If you generate the full script in one pass, export anyway, then split on the paragraph beats.

### Pronunciation dictionary

Add these in ElevenLabs → Voice → Pronunciation, or write them as shown.

| On screen | Say |
|---|---|
| Hermes | HER-meez |
| Casey Nguyen | Casey nwen |
| Kubernetes | koo-ber-NET-eez |
| CKA | C-K-A |
| EMP tokens | do not say them |
| `fitness_score` | fitness score |
| IaC | infrastructure as code |

### Do not claim on camera

Production-ready. SSO. Real-employee scoring. An LLM deciding ranks. A course catalogue. WORM / blockchain audit. Validated against the 2025 manager spreadsheet.

Do not use "he" or "she" for anyone. Say the person's name or "they": the data has no gender field.

---

## On-screen facts (rehearse once)

Role already selected: **Senior Cloud Engineer**.

Needs:

- Container orchestration — level 4, critical  
- Azure networking — level 4  
- Infrastructure as code — level 3  
- Coverage floor 60 percent, shortlist of three  

Typical shortlist on the synthetic DB (order is stable; percents drift slightly because freshness decays with calendar time):

| Person | Rank | About the score | Why |
|---|---|---|---|
| **Alex Rivera** | 1 | ~10.4–10.5% fitness today (drifts down over time), evidence for 2 of 3 | CKA plus two Kubernetes incidents. Azure networking is missing. Infrastructure as code is adjacent through Kubernetes, half credit. |
| **Sam Patel** | 2 | ~4% fitness, evidence for 3 of 3 | Broader coverage, thinner evidence — mostly one compute ticket, a lot of “close,” not “has it.” |
| **Riley Brooks** | 3 | 0% | Declared compute only. Declared-only volume is zero, so the contribution is zero. |
| **Jordan Lee** | excluded | below coverage | Not enough of the required skills. |
| **Casey Nguyen** | excluded | no evidence on any required skill | Honest miss, not a hidden rank. |

If a percent on screen is 10.5 instead of 10.7, keep talking. Do not freeze to match a decimal.

---

## Director — click sheet

Start on **Sign in**. 1280×800. Bookmarks hidden. `HERMES_TEST_MODE=1`. Sign out first so the welcome card appears.

Hold each shot until the VO for that track finishes, then click. Leave 0.4–0.6s of silence after every click so the UI can land.

| Time | Track | You do |
|---|---|---|
| 0:00 | 01 | Hold the Sign in screen. Do not hover. |
| 0:18 | 02 | Click **Continue as a manager**. Wait for the welcome card. |
| 0:38 | 03 | Click **Start looking**. |
| 0:55 | 04 | Confirm role is Senior Cloud Engineer. Click **Find people**. Wait for **Who fits**. |
| 1:25 | 05 | Pause on the shortlist. Cursor over Alex, do not click yet. |
| 1:55 | 06 | Click **Why** on Alex. |
| 2:25 | 07 | Click **How the score was made**. Slow scroll the ledger. |
| 3:10 | 08 | Click **3 Team skills** on the path rail. Hover one filled cell, then one empty. |
| 3:40 | 09 | Click **4 Learning**. Alex is already selected. Click **See what they should learn**. |
| 4:10 | 10 | Hold the gaps. Stop. Optional: fade to Sign in. |

Do not open Insights, Data quality, Workforce, or the command palette. Do not say an EMP token.

---

## Tracks — paste into ElevenLabs

Each block is one generation. No stage directions inside the quotes.

### Track 01 — Cold open  
*~18s · Sign in, still*

This is Hermes.

Not a spreadsheet. Not a guessing engine.

Hermes answers one question a delivery manager actually has.

Who on this team should do the work — based on skills they have already shown.

### Track 02 — Sign in  
*~18s · click Continue as a manager*

I am signing in as a manager.

That is the only hat this walkthrough needs.

No admin console. No search box full of hidden pages.

Just the path.

### Track 03 — Welcome  
*~18s · welcome card, then Start looking*

Home. Find people. Who fits. Team skills. Learning.

Four steps. Same five people all the way through.

I am not hunting the product. The product is walking me.

### Track 04 — Find people  
*~28s · Senior Cloud Engineer, then Find people*

I need a senior cloud engineer.

Hermes already knows what that role requires.

Container orchestration at four. Azure networking at four. Infrastructure as code at three.

Those are governed skills with behavioural definitions — not opinions from last year’s matrix.

I do not type names. I do not tune weights.

I click Find people.

Hermes ranks. I still choose.

### Track 05 — Who fits  
*~32s · shortlist, cursor on Alex*

Three people make the shortlist.

Alex Rivera is first.

Alex has evidence for two of the three skills this role needs. Fitness is a little over ten percent.

That is not a school grade. It is the mean of five multiplied factors, then scaled once for availability.

Sam Patel is second. Broader coverage, thinner evidence.

Riley Brooks is third, at zero. Riley's only evidence is a declared skill. A declaration alone carries no demonstrated work, so it does not move the score.

Two people are not here on purpose.

Jordan is under the sixty percent coverage floor.

Casey has no evidence on any required skill.

Exclusion is a first-class answer. Nobody disappears.

### Track 06 — Why this person  
*~30s · Why on Alex*

This is why Alex is first.

Container orchestration — Alex has it. Level four against a required four.

Certified Kubernetes administrator. Two incidents. A manager-confirmed declaration that carries only fifteen percent of the level vote.

Azure networking — missing. No evidence. Contribution is zero. It still sits in the denominator, so it pulls the mean down. That is deliberate.

Infrastructure as code — close. Not from Terraform tickets. From Kubernetes, at half credit, because the ontology says those skills are adjacent.

Has it. Close. Missing.

Nothing here is a language model. Nothing here is a vibe.

### Track 07 — How the score was made  
*~42s · derivation tab, slow scroll*

This is the part a sceptical VP should not skip.

Every score is the same five factors, multiplied.

Level ratio, capped at one, so an expert is not scored above the level the role needs.

Confidence — how many different kinds of evidence back the skill, not how many tickets someone filed.

Volume — quantity, and it saturates, so a noisy backlog cannot dominate.

Freshness — skills decay. Kubernetes has a one-hundred-and-twenty-day half-life.

Adjacency — half credit for a neighbour skill. Zero if there is no neighbour.

Then the mean. Then availability.

The formula is in the payload. The run id is in the payload. The config version is a hash of the tunable constants and the skill taxonomy, not a marketing label.

If those change, the version changes.

You can reproduce the final score from the payload, because every factor and the formula are in it.

### Track 08 — Team skills  
*~28s · matrix*

Same five people. Now as columns.

Alex. Jordan. Sam. Casey. Riley.

Rows are the governed skills, forty-nine of them.

A number means there is inferred evidence. An empty cell means there is none.

I can see the shape of the team without opening a workbook.

This is not a performance review. Baseline manager ratings never enter a score.

Client familiarity, culture fit and soft skills never enter a score.

### Track 09 — Learning  
*~28s · gaps for Alex*

Alex is the best fit. Alex is not complete.

Same person. Same role. Different question.

What should Alex learn next.

Azure networking — the missing skill. It pulled the average down.

Infrastructure as code — the adjacent one. Ranking may give half credit. A development plan does not. Close is not the skill to learn.

Hermes will not invent a course catalogue. We do not have one connected.

It ranks the gaps by demand weight times how far short the person is. In this demo the demand weights are fixed sample values.

### Track 10 — Close  
*~22s · hold gaps, then fade*

That is the loop.

Sign in. Find who fits. See why. See how the number was made. See the team. See what to learn.

When I am ready, I can choose someone. That decision is audited.

It is never fed back into scoring. The engine does not learn to please me.

Hermes recommends.

I decide.

---

## Full script (single paste)

Use this only if you want one ElevenLabs generation. Add 0.6s breaks between paragraphs in the editor.

This is Hermes. Not a spreadsheet. Not a guessing engine. Hermes answers one question a delivery manager actually has. Who on this team should do the work — based on skills they have already shown.

I am signing in as a manager. That is the only hat this walkthrough needs. No admin console. No search box full of hidden pages. Just the path.

Home. Find people. Who fits. Team skills. Learning. Four steps. Same five people all the way through. I am not hunting the product. The product is walking me.

I need a senior cloud engineer. Hermes already knows what that role requires. Container orchestration at four. Azure networking at four. Infrastructure as code at three. Those are governed skills with behavioural definitions — not opinions from last year’s matrix. I do not type names. I do not tune weights. I click Find people. Hermes ranks. I still choose.

Three people make the shortlist. Alex Rivera is first. Alex has evidence for two of the three skills this role needs. Fitness is a little over ten percent. That is not a school grade. It is the mean of five multiplied factors, then scaled once for availability. Sam Patel is second. Broader coverage, thinner evidence. Riley Brooks is third, at zero. Riley's only evidence is a declared skill. A declaration alone carries no demonstrated work, so it does not move the score. Two people are not here on purpose. Jordan is under the sixty percent coverage floor. Casey has no evidence on any required skill. Exclusion is a first-class answer. Nobody disappears.

This is why Alex is first. Container orchestration — Alex has it. Level four against a required four. Certified Kubernetes administrator. Two incidents. A manager-confirmed declaration that carries only fifteen percent of the level vote. Azure networking — missing. No evidence. Contribution is zero. It still sits in the denominator, so it pulls the mean down. That is deliberate. Infrastructure as code — close. Not from Terraform tickets. From Kubernetes, at half credit, because the ontology says those skills are adjacent. Has it. Close. Missing. Nothing here is a language model. Nothing here is a vibe.

This is the part a sceptical VP should not skip. Every score is the same five factors, multiplied. Level ratio, capped at one, so an expert is not scored above the level the role needs. Confidence — how many different kinds of evidence back the skill, not how many tickets someone filed. Volume — quantity, and it saturates, so a noisy backlog cannot dominate. Freshness — skills decay. Kubernetes has a one-hundred-and-twenty-day half-life. Adjacency — half credit for a neighbour skill. Zero if there is no neighbour. Then the mean. Then availability. The formula is in the payload. The run id is in the payload. The config version is a hash of the tunable constants and the skill taxonomy, not a marketing label. If those change, the version changes. You can reproduce the final score from the payload, because every factor and the formula are in it.

Same five people. Now as columns. Alex. Jordan. Sam. Casey. Riley. Rows are the governed skills, forty-nine of them. A number means there is inferred evidence. An empty cell means there is none. I can see the shape of the team without opening a workbook. This is not a performance review. Baseline manager ratings never enter a score. Client familiarity, culture fit and soft skills never enter a score.

Alex is the best fit. Alex is not complete. Same person. Same role. Different question. What should Alex learn next. Azure networking — the missing skill. It pulled the average down. Infrastructure as code — the adjacent one. Ranking may give half credit. A development plan does not. Close is not the skill to learn. Hermes will not invent a course catalogue. We do not have one connected. It ranks the gaps by demand weight times how far short the person is. In this demo the demand weights are fixed sample values.

That is the loop. Sign in. Find who fits. See why. See how the number was made. See the team. See what to learn. When I am ready, I can choose someone. That decision is audited. It is never fed back into scoring. The engine does not learn to please me. Hermes recommends. I decide.

---

## Ninety-second cut

If the room is impatient, generate these four tracks only. Skip the derivation tab. Click **Why**, then **Team skills**, then **Learning**.

**A.** This is Hermes. Who should do the work, from skills people have already shown. I sign in as a manager. Four steps. That is the whole product.

**B.** Senior cloud engineer. Hermes already knows the skills. I click Find people. Alex Rivera is first. Sam Patel next. Riley Brooks at zero, because a declaration alone carries no demonstrated work. Jordan and Casey are excluded, with reasons. Nobody disappears.

**C.** Why Alex. Alex has Kubernetes — certified, plus incidents. Azure networking is missing. Infrastructure as code is only close, through Kubernetes, at half credit. The number is five factors, multiplied. No model. No vibe. I still choose.

**D.** Same five people as a grid. Then learning: what Alex should learn next is the missing skill, not the adjacent one. Hermes recommends. I decide.

---

## Edit notes

- Underscore UI with a very low bed, or silence. Specific speech does not need music until the last five seconds.
- Cut on the click, not on the breath. Let the welcome card and the shortlist land before the next sentence.
- If ElevenLabs stresses “percent” oddly, regenerate Track 05 with “a little over ten percent fitness” as one phrase.
- If it says “Hermes” as “her-mees,” add the pronunciation dict and regenerate Track 01 and Track 10 only.
- Word count of the full spoken script is about 740 words. At 150 wpm that is 4:55 before click holds. With UI waits you will land near 5:30. Trim Track 07 if you need sub-five.
