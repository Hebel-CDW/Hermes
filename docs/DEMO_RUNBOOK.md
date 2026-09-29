# Hermes demo runbook — managers' walkthrough

**Audience:** non-technical managers. **Length:** about 8 minutes. **Data:** synthetic (5 invented people). The sidebar always says *Synthetic demo data*.

## Before the room fills (2 minutes)

```bash
cd /Users/hebel/Hermes
scripts/run_demo.sh
```

That single command builds the app if needed, creates a **fresh** demo database, starts Hermes, runs a 55-check automatic self-test, resets to a clean state, and opens `http://127.0.0.1:8000`. If it prints `SELF-CHECK FAILED`, do not demo. Otherwise you will see `Hermes is ready`.

- Run it again right before you present. Every run starts clean, so earlier rehearsals leave no trace.
- Full-screen the browser, zoom to 110%, close other tabs, silence notifications.
- Have a second terminal ready with `python -m scripts.demo_svp --verify` in case someone wants proof the numbers are reproducible.

## The story in one sentence

> "Hermes looks at real work — tickets, certificates, and skills a manager has confirmed — and shows who is a good fit for a job and why. It suggests. You decide."

## Walkthrough

| # | Click | Say | What they should see |
|---|---|---|---|
| 1 | **Continue as a manager** | "I'm signing in as a manager." | Welcome card with four steps. Click **Start looking**. |
| 2 | (lands on **Find people**) Leave *Senior Cloud Engineer*. Click **Find people**. | "I need a senior cloud engineer. Hermes checks what people have actually done." | Shortlist appears: **Alex Rivera**, **Sam Patel**, **Riley Brooks**. |
| 3 | Point at the *Fit* column | "Fit is for comparing people, not a pass mark. Scores are modest because this is a small demo with little history on file." | Alex about 10%, Sam about 4%, Riley 0%. The percentages drift down slowly as evidence ages, so a decimal may differ from these. |
| 4 | Point at **Not a fit this time** | "Nobody just disappears. Jordan has too few of the needed skills. Casey has no proof for any of them." | Two people, each with a reason. |
| 5 | Click **Why** on Alex | "Here is the evidence. Container skills: has it. Azure networking: missing. Infrastructure as code: close, because it is related to what Alex has done." | Table of *Has it / Close / Missing* with skill bars. |
| 6 | Click **How the score was made** (optional) | "Every number can be traced. Nothing is a guess." | Step-by-step calculation. |
| 7 | Go back. Under **Choose someone** pick *This person* → **Choose this person** | "I make the call. Hermes records it, and it never feeds back into the scoring." | A green **Accepted** tag, and a Decision card showing who you chose, who approved it, and when. |
| 8 | **Team skills** | "Everyone in the demo on one page. Darker means stronger. No spreadsheet." | Grid of names by skills. It shows everyone in the database, not only your direct reports. |
| 9 | **Learning** → pick Alex → **See what they should learn** | "If someone isn't there yet, this shows the gap." | Azure Networking and Infrastructure as Code as gaps. |
| 10 | **Update skills** → pick a person, pick a skill, **Record this skill** | "If you have seen someone do something that isn't in a ticket yet, you can add it. It counts, but less than real work." | Confirmation. |
| 11 | Account menu → **Sign out** → **View as an employee** | "This is what a team member sees: only their own skills, with a way to say 'this looks wrong'." | Profile with skill names. Sidebar shows only Learning. |
| 12 | Type a reason → **Send to my manager** | "They can flag anything that looks wrong. Their manager then confirms or dismisses it." | "Sent to your manager to review." |

Skip **Workforce**, **Skills**, and **Insights** unless asked. They are the analyst views under *Explore*.

## Questions to expect, and honest answers

| They ask | Say |
|---|---|
| **Is this our real data?** | No. Five invented people so nothing sensitive is on screen. The real workbook can be loaded through a governed path, but scoring has deliberately not been run on real employees yet. |
| **Why is the best score only 10%?** | Fit is a *comparison*, not a grade. Each part of the score is below one, and a missing skill counts as zero in the average. Alex has two tickets, an older certificate that lowers the freshness, one missing skill, and one related skill at half credit. The score also drifts down slowly as evidence ages. |
| **Why is Sam below Alex when Sam has "evidence for 3 of 3"?** | Sam has one ticket. Two of the three skills are credited only through a *related* skill at half credit, and the third is at level 2 of 3. Alex has direct evidence on the critical skill. |
| **Is this AI? Can it be biased?** | No AI model decides. The rules are fixed and visible, and the same evidence on the same date always gives the same answer. A fairness-audit script and methodology exist in the project. |
| **Does it pick people for us?** | No. It ranks and explains. The manager decides, and the decision is recorded. |
| **Can I game it by claiming skills?** | Only managers can add a skill, and a declared skill on its own scores zero, because the score needs demonstrated work behind it (Riley in this demo). A certificate on its own scores zero too. |
| **Who can see what?** | Employees see only themselves. In this demo, managers can see everyone's skills and the rankings. They can update skills and view learning gaps only for their direct reports, and only the owning manager can open or decide a request. This is enforced by the server, not just hidden in the screen. |
| **Where do the numbers come from?** | Tickets, certificates, and manager confirmations. |
| **Can we host this for everyone?** | Yes with a few changes: company sign-in, a managed database, and a hosting slot. See `docs/HOSTING.md` for the exact list. |
| **When can we retire the Excel?** | Overview → *Technical details* shows the retirement gate. It is **Open** today, at 80% pilot coverage. |

If you don't know an answer, say: "Good question — I'll come back to you with the exact answer." Do not guess numbers.

## Say this, avoid that

- Say **"proof from real work"**, not "inferred evidence".
- Say **"related skill"**, not "adjacency".
- Say **"suggests"**, not "recommends" or "decides".
- Say the person's name or **"they"**. The data has no gender field, so don't say "he" or "she".
- Don't open Insights, Data Quality, or the API docs page.
- Don't click **Sign out** mid-story except at step 11.

## If something goes wrong

| Symptom | Fix |
|---|---|
| Page won't load | In the terminal, press Ctrl+C, then run `scripts/run_demo.sh` again (about 30 seconds). |
| "Port already in use" | `PORT=8001 scripts/run_demo.sh` and open port 8001. |
| Shortlist looks different from above | You probably clicked **Choose** or **Update skills** in a rehearsal. Re-run `scripts/run_demo.sh` for a clean start. |
| Signed out unexpectedly | Click **Continue as a manager** again. Data is unaffected. |
| Everything is broken | Fallback: `python -m scripts.demo_svp` prints the whole pipeline in the terminal. |

## Test everything yourself, any time

```bash
python -m scripts.live_smoke                       # 55 end-to-end checks against a running instance
source .venv/bin/activate && python -m pytest      # backend: full suite + coverage gate
cd web && npm test && npm run build                # frontend: unit tests, type check, production build
```
