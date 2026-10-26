# Rentrail — *Every lease leaves a trail.*

**A tenant-side AI team for first-time U.S. renters in Connecticut.** Rentrail reads your lease,
records your home's condition from photos and walkthrough videos, turns every lease and CT-law
deadline into a calendar, protects **both sides of a sublet** with a deposit escrow, and fights
unfair deposit deductions with a letter that cites your evidence, your lease pages, and Connecticut law.

Built by **Yonghyuk Choi** (Yale SOM) for MGT 409 *AI Foundations for Managers*, Fall 2026.

> **Repository (public):** https://github.com/Yonghyuk-Yale/rentrail · **Report:** [`report.html`](report.html) ·
> **Slides:** [`slides.html`](slides.html) (self-contained; rebuild with `python docs/build.py`)

### For graders — the short version

| | |
|---|---|
| **Run** | Copy-paste steps for macOS/Linux and Windows: [How to run it](#how-to-run-it-graders-copy-and-paste-about-3-minutes). Clone → make a venv → install → `run.py` → press **▶ 2-minute guided tour**. Needs only `PORTKEY_API_KEY` in a `.env` in the repo folder **or one folder up**. Fresh-clone test: install ≈ 2.5 min, start ≈ 10 s. |
| **No key? / no time?** | The demo year is pre-loaded from real agent runs, so every page works without a key; only *new* AI runs need it. `.venv/bin/python -m unittest discover tests -v` (Windows: `.venv\Scripts\python ...`) runs 12 code-only tests (≈ 6 s, no key). |
| **Agents** | 6 × `gpt-6-luna` (Boss with 14 tools + 5 specialists) behind a code-only **Checkpoint**. Every run's agent-to-agent trace, tokens and cost: **Agents** page (Agent Room). |
| **Evidence** | Token logs and cost at scale: Agent Room · Attacks actually blocked + 7/7 self-test: **Safety** page · Six evaluate → improve rounds and cost-cut experiments: [`eval/README.md`](eval/README.md) · How AI assistance was used: [`docs/AI_prompts_eng.md`](docs/AI_prompts_eng.md) (Korean original: [`docs/AI_prompts.md`](docs/AI_prompts.md)) |
| **Cost** | The whole demo year (18 AI runs) cost **$0.031**; about $0.0075 per renter per month. |

---

## How to run it (graders: copy and paste, about 3 minutes)

**You need:** Python **3.10 or newer** and git. Nothing else — no Node.js, no database, no other service
(the web app is already built in `frontend/dist`; data is a local SQLite file created on first start).

**The key.** Rentrail needs one key, `PORTKEY_API_KEY` (model `gpt-6-luna`). It reads a `.env` file from
**the repo folder first, then the folder one level above it**, so the course's standard layout works as is:

```
submissions/
├── .env          <- contains the line  PORTKEY_API_KEY=...
└── rentrail/     <- this repo, cloned here
```

(Or put a `.env` inside `rentrail/`: copy `.env.example` to `.env` and paste the key.)

### macOS / Linux

```bash
cd submissions
git clone https://github.com/Yonghyuk-Yale/rentrail.git
cd rentrail
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

### Windows (PowerShell or Command Prompt)

```bat
cd submissions
git clone https://github.com/Yonghyuk-Yale/rentrail.git
cd rentrail
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py
```

(`python` instead of `py -3` also works. There is **no need to activate** the virtual environment —
the commands call the `.venv` Python directly, which avoids PowerShell's script-execution prompt.)

**What you should see** — the install takes about 2.5 minutes (it downloads OpenCV and the PDF tools),
then the app starts in about 10 seconds and opens your browser:

```
Rentrail - tenant-side lease agent (Connecticut)
  model: gpt-6-luna via Portkey
  PORTKEY_API_KEY found: True  (.env checked: ['submissions/.env'])

  Rentrail is starting at  http://127.0.0.1:8460   <- open this in your browser (Ctrl+C to stop)
```

If the browser does not open, open the address it prints. If port 8460 is busy, Rentrail picks the next
free port (8461, 8462, ...) and prints it. `Ctrl+C` stops it; run the last command again to restart.

**Then:** on the login page press **"▶ 2-minute guided tour"**. No password needed. The tour moves the time
machine through Alex's year and opens each page for you. A full fictional year of renting is pre-loaded
from real agent runs, so every page has content immediately (even without a key), and any **Run** /
**Run again** button or a chat question calls the live agents.

Demo accounts (password `rentrail-demo`): `alex@demo.rentrail` (tenant; switch the top bar to
**"Subletting my place"** to open the sublet), `jordan@demo.rentrail` (summer subtenant — sees only the
sublet side), `minji@demo.rentrail`. Or create your own account.

---

## A 5-minute tour

| Page | Try this |
|---|---|
| **▶ Guided tour** | On the login page press **2-minute guided tour**: 11 steps move the time machine, switch roles and open each page for you (no AI calls). Alex can restart it from the top bar. |
| **Home** | A dashboard: next task, money due in 30 days, deposit, records; up to 3 alerts; the **Next up** table; progress. **Deposit Shield** (0–100, plain code) scores how well the deposit is protected today — photos, video, key rooms covered, recorded within 48 h, insurance, precheck, move-out record — and levels up from paper to gold. **Chief Justice Dan** lives in the bottom-right chat on every page: he answers, asks his teammates and *acts* (opens pages, checks off tasks, moves the time machine, starts inspections, comparisons, the precheck, the deposit case). |
| **Lease** | Clerk Dan's Lease Card: key clauses with exact quotes and page numbers, red flags, who pays/bills each utility, and the calendar built from the lease + CT law. Ask a lease question. |
| **Inspections** | Alex's clean move-in (Aug 1 2026), the sublet hand-off where Alex's own floor gouge and wall chip are recorded (Jun 1 2027), the return with Jordan's new wall crack (Jul 28), and Alex's move-out (Jul 31). Photos and **videos** (keyframes are extracted). Detective Dan's findings are a draft: press **Not damage** to dismiss a false alarm with a reason. Click a thumbnail → *Verify* the SHA-256 fingerprint. **Before vs. after** pairs each later frame with the same spot before (e.g. the clean bedroom wall in the move-in video vs. the crack). The *Safety test* video shows text addressed to the AI being ignored. |
| **Move-out precheck** | Set the date to **Jul 29 2027** (two days before move-out) → **Deposit**: *Fix it or pay for it?* The Detective compares move-in with the latest record, Counsel Dan picks the repair type and whether DIY is safe, and **code prices every item** from `backend/repair_costs.json`: patch the hallway chip yourself ($12 vs. ~$138 deducted), hire a pro for the floor, and claim Jordan's crack from the sublet escrow — about **$275 saved**. |
| **Deposit** | The landlord's statement hides white text telling the AI to approve everything. The Checkpoint strips it; Counsel Dan argues each item; Chief Justice Dan rules; Rentrail computes the 21-day deadline (the statement was **3 days late**), interest, and the refund; the letter cites exhibits, lease pages, and statutes. |
| **Time machine** | Every record has the date it happens (lease Jul 10 2026 → move-in Aug 1 → sublet listed Apr 15 2027 → sublease May 10 → deposit May 20 → hand-off Jun 1 → June bill Jul 6 → return Jul 28 → move-out Jul 31 → statement Aug 24). Pick a date in the 🕰️ menu: only what exists on that day is shown, and every payment or upload is stamped with that day. |
| **Sublet & Escrow** | Switch to **"Subletting my place"**. Under CT §47a-21(a)(7) a tenant who sublets is a "landlord". The subtenant's deposit sits in Rentrail escrow (simulated card/ACH); steps are dated; **Reset ledger** replays the money flow. Log in as **Jordan**: *My sublease* (its own fictional contract: $1,950/month, electricity reimbursed by days), *Bills* (pay the pro-rated electricity share), *Deposit Court* (Counsel Dan appeals the escrow proposal on Jordan's side, the Chief Justice rules again). |
| **Bills & Insurance** | Bills checked against the lease's utility clause (Conservice, a third-party electricity contract that expires), and the renter's policy checked against the lease's $100,000 liability requirement. |
| **Community** | Reviews, Q&A and stories from renters; Counsel Dan can answer Q&A posts from the law pack. Phone numbers and emails are hidden automatically. |
| **Agent Room** | The team diagram, every run's agent-to-agent trace (input, output, tokens, cost), cost by agent, and cost at scale. |
| **Safety Center** | One-click self-test of the code defenses (no AI, $0) and the log of what was actually blocked. |

Everything in the demo is fictional (Alex Kim, "77 Bulldog Lane", Elm City Residences LLC). The
photos/videos are the author's own, with all EXIF/GPS removed. The move-in floor/wall photos are
**digitally edited** copies with the defect removed (files named `EDITED_...`), because in the story the
damage happens later.

---

## How it works

```
You (lease PDF, photos, videos, bills, questions)
        │
        ▼
CHECKPOINT   — not an agent: an always-on gate in plain code that no AI (not even the Boss) can skip:
               visible-text-only PDFs, instruction detection, EXIF/GPS strip,
        │      face blur, name/address/account masking, encrypted storage, token limits
        ▼
Chief Justice Dan (Boss, gpt-6-luna) ── plans, rules, answers chat, delegates ──┐
   ├─ Clerk Dan        — Lease Card with page citations, lease Q&A            │
   ├─ Detective Dan    — damage in photos/video keyframes, before vs. after   │  one shared
   ├─ Counsel Dan      — each deduction vs. evidence, lease, CT law pack      │  Tenancy Record
   ├─ Escrow Sheriff   — sublet consent letter, sublease draft, escrow claims │  (SQLite)
   └─ Treasurer Dan    — bills and insurance vs. the lease                    ┘
Code does every date and dollar: deadlines, interest (0.49% in 2026), refunds, utility proration, escrow split,
repair prices (repair_costs.json) and the Deposit Shield score.
```

- **Model**: `gpt-6-luna` through Portkey for every agent (fixed in `backend/config.py`; the app refuses any other model name).
- **Structured outputs + validators**: agents return typed objects (`backend/models.py`); answers citing a page, an evidence id, or a law id that does not exist are rejected and retried.
- **Law**: only the excerpts in `backend/law/ct.json` (Conn. Gen. Stat. §47a-21, §47a-11, CT Dept. of Banking guidance). Adding a state = adding one JSON file.
- **Tokens**: every agent call stores input / cached / output tokens and cost; see the Agent Room or `/api/tokens`.
- **Evaluation**: `eval/` holds six evaluate → improve rounds scored against a hand-labelled answer key (`python eval/score.py`) and the cost-cut experiments (did cutting tokens hurt quality?).
- **Tests**: `python -m unittest discover tests -v` (code-only: deadlines, interest, statement parsing, hidden-text removal, masking, citation validators, precheck pricing, safety self-test).

## Project layout

```
run.py                  start the app (one process, one port)
backend/app.py          FastAPI routes (+ serves the built React app)
backend/cases.py        workflows: lease, inspect, compare, deposit case, sublet, bills, calendar
backend/agents.py       the bulldog bench + output validators     backend/prompts/  role prompts
backend/copilot.py      Boss chat with delegation tools            backend/guard.py  the Checkpoint
backend/privacy.py      EXIF/GPS strip, face blur, keyframes, masking
backend/storage.py      encrypted files + SHA-256 fingerprints    backend/law/ct.json  CT law pack
backend/demo.py         demo accounts and fixtures (sample_data/fixtures = real runs)
backend/selftest.py     safety self-test                           eval/  improvement rounds
frontend/               React + TypeScript source; frontend/dist is the built app
scripts/                sample-document generator, full demo pipeline driver
tests/                  code-only unit tests (no key needed)
docs/                   report and slide sources, screenshots, build script, AI prompts log
report.html, slides.html  the submitted report and slides (self-contained)
```

## Troubleshooting

- **No key found** — the demo data still opens; new AI runs show an error. Put `.env` in the repo or one folder up and restart.
- **Port in use** — Rentrail moves to the next free port automatically; or choose one: `.venv/bin/python run.py --port 8470`.
- **Reset the demo** — stop the app and delete the `instance/` folder (or `python backend/demo.py reseed`); the demo is rebuilt on the next start.
- **Rebuild the UI after editing it** — `cd frontend && npm install && npm run build` (Node 20+; not needed to run the app).
- **Browser did not open** — open the address printed in the terminal (`run.py --no-browser` skips opening it).
- **`Missing package`** — the install step was skipped or ran with another Python; run `.venv/bin/python -m pip install -r requirements.txt` (Windows: `.venv\Scripts\python -m pip install -r requirements.txt`).
- **`python3`/`py` not found** — install Python 3.10+ from python.org; on Windows tick "Add python.exe to PATH".
- **Slow first AI call** — a vision or deposit run takes 10–60 s; each agent call has a hard 5-minute limit and a per-run token budget.

*Information, not legal advice. Connecticut only. Payments are simulated.*
