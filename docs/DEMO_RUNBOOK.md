# Hermes demo runbook

Everything below uses the built-in demo organisation: 36 invented people across all 8 skill areas,
10 role templates (one per scenario), and one pre-filed evidence dispute. It is synthetic data only.

## Start

**Presenting: double-click `start-all.command`** (or run `./start-all.command`). It checks Python, the
environment and the web build, starts Hermes through `scripts/run_demo.sh`, waits for the backend health check and
the web app, prints a banner with the URL, then opens the browser. Keep its window open; **Ctrl+C** stops it.

- It installs nothing. If something is missing it prints the exact command to run (first-time setup: `./start.command`).
- If the default port 8000 is busy (Docker, another app) it uses the next free one and prints it; it never stops another program.
- Clicking it twice does not start a second server: the second click just reopens the running one.
- Demo data lives in `.demo-data/` (git-ignored) and **survives restarts**: whatever you did in a rehearsal is still there.
  It is seeded only when empty: 36 people plus one synthetic Azure-certified engineer, and two opportunities
  (one at intake for the live walkthrough, one "completed example" already approved and matched).
- **Reset to the clean starting state (explicit, demo-only):** stop the demo (Ctrl+C), run `scripts/reset_demo.sh`, then start again.
  It deletes only the demo database and encrypted demo documents inside `.demo-data/`, refuses to run while the demo is up,
  and is never called automatically.
- **Two opportunities, on purpose.** "Cloud Platform Modernisation (live walkthrough)" is at intake with an uploaded SOW:
  present the journey on this one. "Cloud Platform Modernisation (completed example)" is already extracted, approved and
  internally matched, so you can show a finished result without waiting. The RFP/SOW and Scenario Optimizer pickers show the stage.
- **Say these two things out loud (known limitations).**
  1. *No maker-checker rule.* The person who extracted a document can also approve its requirements, and the creator of a scenario
     can approve their own lane. The approver is recorded in the audit trail, but independent review is not enforced. Do not
     present this as separation of duties; it is listed as a next-milestone control.
  2. *Opportunity matches are ranking only.* An internal match creates ordinary Hermes staffing requests (IDs starting `hoi-`).
     They show as "Open" (ranked, awaiting a person's decision) on Overview and Requests, labelled "ranking only". No one is assigned
     or approved for staffing by Hermes; approving a scenario records the decision, it does not allocate anyone.
- Clean-room run with an automatic 64-check self-check and a throwaway database each time:
  `./start.command` (or `scripts/run_demo.sh`).

Sign in with **Continue as a manager** (Alex Rivera, manages 17 people). The employee view is
**View as an employee** (Sam Patel).

## The 60-second story

1. **Overview**: who we have and how well each area is covered.
2. **Find people**: pick a role, press Find people.
3. **Who fits**: the coloured box at the top says who to pick and why, in one sentence. Open anyone below it to see what is strong, what falls short, and why they are not ahead of the first choice. "How to read these numbers" explains every figure.
4. **Choose someone**: you decide, Hermes only ranks. The decision is audited.
5. **Learning / My skills**: the same evidence tells each person how to grow.
6. **Ask Hermes** (bottom right): ask in plain English; it answers only from the data on screen.

## The 10 manager scenarios

Find people, choose the role template, press **Find people**.

| # | Scenario | Role template | What happens | What to say |
|---|---|---|---|---|
| 1 | Clear winner | Senior Cloud Engineer | Priya Nair scores 52.8%, next is 21.7%. Banner: "clear first choice". | "When the evidence is strong the answer is obvious, and Hermes says so." |
| 2 | Too close to call | Platform SRE Lead | Marcus Webb 0.230 vs Elena Petrova 0.229. Banner: "Too close to call". Marcus has more tickets, Elena has a certificate. | "Hermes will not pretend a 0.001 gap is a decision. It tells you to use judgement and shows what differs." |
| 3 | Missing a critical skill | Firewall and Security Lead | Callum Reid is first. Tomas Herrera, strong in security, is **not shortlisted**: no proof of Firewall Administration. | "A role can name a skill it cannot do without. No amount of other skill replaces it." |
| 4 | Stale proof | Data Protection Engineer | Hannah Kim beats Walter Okafor, who has the bigger CV but proof that is two to three years old (about 16% fresh). | "Skills fade. Old proof counts for less." |
| 5 | Claimed, not proven | Automation Engineer | Nina Rossi (real tickets) is first. Dev Malhotra's confirmed claims of Python and Ansible score 0.000 beside her. | "Confirmed claims count, but far less than real work." |
| 6 | Related-skill credit | Azure Platform Engineer | Priya, Omar, then Sam Patel. Lower down, Elena and Alex get partial credit for a close skill, labelled as such. | "Close cousins earn partial credit, always labelled." |
| 7 | Single point of failure | IBM i Support Engineer | Only Gregory Baptiste qualifies. Banner warns there is no backup. | "Hermes spots the person the business cannot lose." |
| 8 | Nobody fits | Multi-Cloud Architect | Empty shortlist. Banner: "No one fits this role right now" with reasons. Then open Learning for the closest people. | "An honest 'no one' is a result, and it points to training or hiring." |
| 9 | Grow someone | Senior Cloud Engineer, then Learning | Mei Tanaka is one skill (Azure Networking) from the role. Learning shows the exact gap and its priority. | "Instead of hiring, here is the single skill to grow." |
| 10 | Employee disputes evidence | Update skills | Sam Patel has an open dispute about Infrastructure as Code ("Terraform work done outside tickets"). Confirm or dismiss it; confirming adds a manager-confirmed claim, and Sam's confidence on that skill rises from 35% to 70% because two kinds of proof now agree. | "People can challenge their record, and a manager decides, with an audit trail." |

Also worth showing once: **Team skills** (the whole matrix), **Workforce** (everyone by area), **Skills** (the 49 governed skills; pick one for who holds it), **Insights**, and **Requests** after you have made a decision.

## The employee view (sign in as the employee)

**My skills** opens with a plain-English summary ("Hermes holds proof of 6 skills for you...") and four figures. Then:

- **Your skills, explained**: level in words, how sure Hermes is, what proof backs it, how recent it is, and one concrete tip to strengthen each skill.
- **Roles you could grow into**: how close Sam is to each role, with the exact gaps ("Azure Networking: you are at level 2, the role needs level 3").
- **Your open disputes**: the Infrastructure as Code dispute, marked "With your manager".
- **Something look wrong?**: send a new dispute to the manager.
- **How to read these numbers**: the same guide the manager sees.

## The Excel replacement: employees propose, managers decide

This is the part that answers "so what replaces the skill matrix spreadsheet?". Rehearse it end to end (about 4 minutes).

1. Sign in **as an employee** (Sam Patel) and open **My growth**. Pick a goal, for example **Azure Platform Engineer**. The ring and the bars show exactly which skills are one level short.
2. Under a short skill press **I have this now**, add a note, and **Send to my manager**. It appears under **What I have sent** as *Waiting for your manager*, and on **Your timeline**. It changes nothing on Sam's record yet.
3. Sign out, **Continue as a manager**. The sidebar **Approvals** badge and the Overview banner show what is waiting.
4. Open **Approvals**. Choose the level you confirm, add a note, **Approve**. Only now does it count (as a manager-confirmed claim, at declared weight). Sam's dispute sits in the same list.
5. **Bulk update** is the spreadsheet replacement for the manager: edit levels in the grid, or **Paste from Excel** (`Person, Skill, Level`). Rows that do not match exactly are listed, never guessed. One **Save** records everything, each row audited.
6. **Role lab**: change a level or flag a skill as critical and watch the shortlist re-order live (▲ and ▼ against the saved role). Nothing is stored. **Save as a role** keeps it, and it appears in Find people and on employees' goal lists.
7. On any **Who fits** page press **Compare people** for the radar, fit bars and skill-by-skill table. **Download CSV** or **Print or save as PDF** hands it to anyone still on Excel.

What to say: *"Nothing an employee types counts until their manager approves it, tickets and certificates still outweigh claims, and every step is in the audit trail."*

## Copilot questions that work well

Manager: "Who should I pick for my latest request, and why?" · "Walter Okafor has the most experience. Why is he not first?" · "Which skills have only one person who can do them?" · "Are there any disputes waiting for me?"

Employee: "Which role am I closest to, and what is missing?" · "Why is my confidence not higher?" · "Do I have a dispute waiting?"

Answers come from a local model (Ollama, `qwen2.5:7b-instruct`) given only the facts the signed-in person may see. The label under each answer says whether the model or the offline fallback produced it. If Ollama is not running the copilot still answers from the data, and says so. The first question after a cold start can take up to 20 seconds; start.command pre-loads the model.

## If someone asks

- **What is "fit"?** A comparison between people for this role, not a pass mark. It stays low for everyone when little proof is on file.
- **What is "confidence"?** How many kinds of proof agree: tickets alone 35%, tickets plus a certificate about 90%.
- **Who decides?** The manager, always. Hermes ranks and explains; every decision is audited and never fed back into scoring.
- **Where do names come from?** Demo names are invented. With real data only coded identities show, and names open only through an audited, owner-scoped lookup.
- **Is the copilot allowed to change anything?** No. It reads, explains, and advises.

## Troubleshooting

- Port in use: start.command picks the next free port; read the address it prints.
- Copilot says "model offline": run `ollama serve`, then ask again. The product keeps working without it.
- Want a clean slate: stop (Ctrl+C) and run `start.command` again.

## Re-running the checks

Both need a running instance on a freshly seeded database (they write real requests and decisions):

    python -m scripts.scenario_tests --base http://127.0.0.1:8001            # 92 outcome checks: the 10 scenarios, roles, security, approvals, bulk update, what-if, custom roles
    python -m scripts.stress_demo --base http://127.0.0.1:8001 --db <demo.db>  # load, races, soak, integrity (about 3 minutes)

Seed a database to test against with `python -m scripts.seed_demo_org --db /tmp/test.db`, then serve it with
`HERMES_TEST_MODE=1 HERMES_DB_PATH=/tmp/test.db PYTHONPATH=src:. uvicorn api.main:app --port 8001`.
