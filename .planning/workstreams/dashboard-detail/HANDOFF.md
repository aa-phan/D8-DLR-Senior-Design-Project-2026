# Handoff: city detail view

You own the per-city detail view of the operator dashboard, in this workstream (`dashboard-detail`). Aaron owns the `software-dashboard` workstream next to it: the shared foundation, the four-card overview, and the final usability review. Your build work starts when software-dashboard Phase 1 is complete; design work can start now.

This file gets you from a fresh clone to your first piece of work. What to build is in [`ROADMAP.md`](ROADMAP.md) and [`REQUIREMENTS.md`](REQUIREMENTS.md); this file does not repeat it.

## 1. Get the code running

1. Clone the repository and check out the dashboard branch:

   ```
   git clone https://github.com/aa-phan/D8-DLR-Senior-Design-Project-2026.git
   cd D8-DLR-Senior-Design-Project-2026
   git checkout feature/dashboard
   ```

2. Create your own branch for this workstream; open pull requests into `feature/dashboard`, never into `main`:

   ```
   git checkout -b feature/dashboard-detail
   ```

3. Set up Python 3.12 for the Django app:

   ```
   cd frontend
   python3.12 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

   `requirements.txt` is saved as UTF-16. If pip cannot read it, convert a local copy to UTF-8 and install from that; do not commit the conversion (the fix belongs to software-dashboard Phase 1).

4. Get the two connection values from Aaron in person: `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. Put them in a `.env` file at the repository root. The file is git-ignored; never commit it, paste it into a chat, or let Claude read it.

5. Run the app and open http://127.0.0.1:8000/?category=Austin:

   ```
   .venv/bin/python manage.py runserver
   ```

   The home page should show a thermal limit and an age for Austin. The History page crashes at the moment; that is a known bug, listed in the findings below.

## 2. Install the tools

### Required

**GSD (Get Shit Done)** runs every `/gsd-*` command this workstream uses.

- Install: run `npx get-shit-done-cc@latest` in a terminal, choose Claude Code and a global install, then run `/gsd-help` in Claude Code to check it worked.
- Docs: https://www.mintlify.com/gsd-build/get-shit-done/installation
- Aaron is on GSD 1.17.0; tell him if your version is far off, since the planning files are shared.

### Recommended design tools

These follow ch. 8 of the requirements document. None is mandatory.

| Tool | Use it for | Get it |
|---|---|---|
| `frontend-design` (Anthropic's official plugin) | Choosing a deliberate visual direction | In Claude Code: `/plugin marketplace add anthropics/claude-plugins-official`, then `/plugin install frontend-design@claude-plugins-official`. Source: https://github.com/anthropics/claude-plugins-official |
| `impeccable` | Designing, critiquing and polishing: hierarchy, typography, colour, states, accessibility | https://github.com/pbakaus/impeccable (install per its README) |
| `accessibility-review` (Anthropic) | WCAG 2.1 AA review; covers UI-16 | Skill `accessibility-review` in https://github.com/anthropics/knowledge-work-plugins |
| `ux-heuristics` | Critique against Nielsen's 10 usability heuristics | Skill `ux-heuristics` in https://github.com/wondelai/skills |
| `design-is` | A restraint check against Dieter Rams' ten principles | Skill `design-is` in https://github.com/thedotmack/claude-mem |
| `dataviz` | Chart colours and marks that read as one system; supports UI-09 | Built into some Claude Code installs; skip it if you don't have it |
| `/gsd-sketch`, `/gsd-ui-phase`, `/gsd-ui-review` | Mock-ups, the UI design contract, and the visual audit | Included with GSD |

Before installing any third-party skill, open its `SKILL.md` and read it: a skill is a set of instructions Claude will follow.

The requirements document also names `craft`, `accessibility`, `ux-heuristics-review`, `cognitive-load-conversion` and `dieter-rams-principles`. Those are Aaron's own copies and are not published on GitHub. The table above lists the closest public equivalents; `frontend-design` and `impeccable` cover most of what `craft` and `cognitive-load-conversion` do.

## 3. Read first

In this order:

1. [`ROADMAP.md`](ROADMAP.md), [`REQUIREMENTS.md`](REQUIREMENTS.md) and [`STATE.md`](STATE.md) in this folder.
2. [`../software-dashboard/docs/DASHBOARD-REQUIREMENTS.md`](../software-dashboard/docs/DASHBOARD-REQUIREMENTS.md), especially ch. 2.3 (plain-language rule), ch. 5.6 (the detail view), ch. 6 (UI rules), ch. 7 (data access) and ch. 8 (design tools).
3. [`../software-dashboard/docs/COLUMN-GUIDE.md`](../software-dashboard/docs/COLUMN-GUIDE.md): every database column in plain language.
4. [`../software-dashboard/ROADMAP.md`](../software-dashboard/ROADMAP.md): Aaron's workstream. Your work depends on its Phase 1.
5. [`../software-dashboard/grounding/findings.md`](../software-dashboard/grounding/findings.md) and [`coverage.md`](../software-dashboard/grounding/coverage.md): known bugs, contract breaches and the status of every requirement in the current code.
6. [`../../../docs/integration/rest-api.md`](../../../docs/integration/rest-api.md): the database contract. Where the code and the contract disagree, the contract wins.

## 4. Ground rules

- **What you own:** DET-01 to DET-06, DATA-03, DATA-04, UI-09 and UI-10. Everything else belongs to software-dashboard.
- **Where your code goes:** the detail view is its own Django app inside `frontend/` (for example `frontend/citydetail/`), with its own views, templates and URL include. That keeps the two workstreams out of each other's files.
- **What you reuse and do not edit:** the shared data layer, the city-state rules and the browser script that software-dashboard Phase 1 builds. If you need a change in them, write it down for Aaron rather than editing them.
- **Decisions already made:**
  - Django renders on the server, and a small browser script keeps ages counting and turns a card to "Data late" at 90 minutes.
  - Times in Central Time, labelled CST or CDT.
  - Whole amps, labelled "per wire".
  - No "dynamic" or "static" wording on operator screens (ch. 2.3).
  - ISO 9241 is required: software-dashboard Phase 1 writes a traceability list from the standard's principles to requirement IDs. Each of your phases must pass the items that list assigns to the detail view. The usability review in software-dashboard Phase 3 covers your pages too.
- **Secrets:** never commit `.env`, never paste the key anywhere, and the dashboard only ever uses the publishable key.

## 5. What to do first

Until software-dashboard Phase 1 is complete, do design work only:

1. Mock up the detail page with `/gsd-sketch`. It should show:
   - the city's current state and headline
   - the three weather drivers
   - the next-hour forecast
   - the history chart with a 24-hour and 7-day switch
   - the day-ahead outlook
   - the collapsed Technical details

   Follow ch. 5.6 and ch. 6.
2. Settle the visual direction with `frontend-design` or `impeccable`, consistent with the overview's rules in ch. 6.
3. Draft the chart choices for UI-09.
4. Collect questions for Aaron, especially anything in ch. 11 of the requirements that affects the detail view.

Once Aaron says Phase 1 is done:

```
/gsd-discuss-phase 1 --ws dashboard-detail
/gsd-ui-phase 1 --ws dashboard-detail
/gsd-plan-phase 1 --ws dashboard-detail
```

## 6. Starter prompt for Claude Code

Paste this into Claude Code from the repository root once the tools above are installed:

```text
I'm joining the DLR senior design project to build the operator dashboard's per-city
detail view, in my own GSD workstream that runs alongside Aaron's. Read
.planning/workstreams/dashboard-detail/HANDOFF.md first and follow it: it covers setup,
what to read, the ground rules and what to do first.

Then:
1. Check my setup: the branch is feature/dashboard-detail off feature/dashboard, the
   venv in frontend/.venv has the requirements installed, and the app runs. Don't
   read, print or commit .env.
2. Read the documents in section 3 of the handoff, in order, and summarize in a few
   lines what my two phases must deliver and what I depend on from Aaron's Phase 1.
3. Start the design work in section 5: mock up the detail page with /gsd-sketch,
   following DASHBOARD-REQUIREMENTS.md ch. 5.6 and ch. 6.
4. List any questions for Aaron, especially from ch. 11 of the requirements.

Stay inside my scope (DET-01..06, DATA-03, DATA-04, UI-09, UI-10) and my own Django
app; never edit the shared data layer, city-state rules or browser script, and never
push to main.
```
