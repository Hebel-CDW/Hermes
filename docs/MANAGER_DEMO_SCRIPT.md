# Manager demo — 2-minute recording script

> Running the demo live? Use [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) (8 minutes, with a Q&A cheat sheet and `scripts/run_demo.sh`). This page is the short recording script.

**Audience:** a non-tech manager  
**Runtime:** ~2 minutes live; for ElevenLabs use [`docs/ELEVENLABS_VOICEOVER.md`](ELEVENLABS_VOICEOVER.md) (ten tracks, ~4:30, plus a 90-second cut).  
**Data:** synthetic demo people (Alex, Sam, Riley). Scoring still ran on coded tokens; names are a display overlay.

Say this out loud. Do not lead with an EMP token.

---

## Setup (off camera)

1. App running locally: UI at `http://localhost:5173`, API at `http://127.0.0.1:8000`.
2. `HERMES_TEST_MODE=1`.
3. Browser at the Sign in screen. Hide bookmarks. 1280×800 is enough.

---

## Script

**0:00 — Sign in**

> “This is Hermes. It helps me see who on the team should do a piece of work, based on skills they have already shown.”

Click **Continue as a manager**.

> “I’m signing in as a manager. That’s the only hat I need for this walkthrough.”

**0:15 — Welcome**

A welcome card lists the four steps. Click **Start looking**.

> “Home, find people, who fits, team skills, learning. That’s the whole path.”

**0:25 — Find people**

The role is already **Senior Cloud Engineer**. Leave it. Click **Find people**. Wait for the shortlist.

> “I’ll look for a senior cloud engineer. Hermes ranks who fits. I still choose.”

**1:00 — Shortlist**

You should see **Alex Rivera**, **Sam Patel**, and **Riley Brooks**, with a fit percent and “evidence for N of 3 skills”.

> “Alex is first. He has real proof for most of what this role needs. Sam and Riley are next. If I want the why, I open any row.”

Click **Why** on Alex.

> “This is the evidence behind the rank — which skills he has, and where there are gaps. Nothing here is a guess.”

Go back (browser back or the request link).

**1:25 — Team skills**

Click **Team skills** in the left nav.

> “Same five people, as columns. Rows are skills. I can see who has evidence without opening a spreadsheet.”

Confirm column headers show names, not only codes.

**1:40 — Learning**

Click **Learning**. Pick **Alex Rivera**. Keep Senior Cloud Engineer. Click **See what they should learn**.

> “And if Alex is close but not quite there: this is what he should learn next. Hermes does not invent a course catalogue — it only shows the skill gaps.”

**1:55 — Close**

> “That’s the loop. Sign in, find who fits, see why, see the team, see what to learn. I can record a decision when I’m ready. Hermes recommends. I decide.”

Stop recording.

---

## If something looks wrong

| You see | Likely cause |
|---|---|
| Only `EMP-…` codes, no names | Database is not synthetic, or directory was refused. Stay on the test-mode demo DB. |
| “Identity protected” on the shortlist | Real-data mode. This script is for the synthetic demo. |
| Empty matrix | Evidence has not been ingested. Re-run the local fixture ingest. |
| Login shows five principals | Click **Continue as a manager**. Ignore **More roles**. |
