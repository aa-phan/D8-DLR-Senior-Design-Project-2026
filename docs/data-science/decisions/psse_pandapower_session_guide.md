# PSS/E reference session: guide for the teammate and the owner

**Date:** 2026-11-17
**From:** pandapower-solver Phase 1 (plan 01-04: PSE-01, PSE-02; the session itself is plans 01-02 and 01-03)
**To:** the person at the licensed laptop (the teammate), and the project owner
**Status:** written and rehearsed on the Mac against a stand-in for PSS/E. Nothing here has run on the real laptop yet, so every statement below about what the real PSS/E does is **UNVERIFIED until the session**. If the real run disagrees with this guide, the run is right and the guide gets corrected.

## What the session is for

We are building a second load-flow solver (pandapower) and we need to prove that it gives the same answers as PSS/E. Only the licensed laptop can run PSS/E. So we make one visit to the laptop. The session copies out three things:

1. **The network.** PSS/E writes out the power system it has loaded, as a plain text file, so the owner can build the same network in pandapower.
2. **PSS/E's own answers.** For each of the four cities, PSS/E solves the load flow. The session saves what PSS/E says: every bus voltage, every line flow, and what happens when a line is switched off, and how far the transfer can be pushed before voltages collapse.
3. **How PSS/E is set up.** Which load-flow settings PSS/E is using, and a few short experiments that show how PSS/E scales load and generation. Nobody has written these down for this version of PSS/E, so the session measures them. The owner works out what they mean later, on the Mac.

All of this goes into one zip file on your Desktop. You send the zip to the owner. That is the whole job.

## What it does and never does

**It does:**

- Read from PSS/E and from the case file, and nothing else.
- Write one zip file on your Desktop.
- Delete its own temporary folder when it finishes, and delete the private mapping copy you give it.
- Print a short summary made of counts, version numbers and a few fixed words.

**It never:**

- Saves, changes or overwrites the case file, or any PSS/E setting. Every experiment works on a copy that exists only in memory.
- Opens a network connection or touches a database.
- Writes anywhere except its own temporary folder and the final zip.
- Prints a bus number, a line name, a value from the network, a folder path, your user name or your computer's name.

The zip itself does hold the real network data, so treat it as private. Send it only by the private channel the owner names, and delete it after it is sent.

## Words and placeholders

The commands below use these placeholders. Replace each with the real value on the laptop; never paste the real value anywhere else.

| Placeholder | Meaning |
|---|---|
| `<PYTHON>` | The Python that goes with PSS/E, the same one used in the earlier laptop session. Put it in quotes if its path has a space. |
| `<REPO>` | The folder holding this project's copy on the laptop. |
| `<CONFIG>` | The settings file from the earlier laptop session (it tells the program where PSS/E and the case file are). You do not need to change it. |
| `<MAPPING COPY>` | The private mapping file the owner sends you. The session deletes it when it ends. |
| `<ZIP>` | The name of the zip file the session leaves on the Desktop. |
| `<SESSION>` | The folder, on the owner's computer, where the zip is unpacked. |

A **section** is one part of the session. There are four, always in this order: `network` (the text copy of the network), `reference` (PSS/E's answers), `settings` (PSS/E's load-flow settings) and `scaling` (the load and generation scaling experiments). If one section fails, the others still run and still go into the zip.

## Before the session (the owner)

1. Push the branch so the laptop can pull it.
2. Send the teammate the mapping copy by the private channel (the same channel the mapping came in on). Do not email it and do not put it in the repository.
3. Tell the teammate which private channel to use for the zip coming back.

## The teammate's steps

Run these in PowerShell. Nothing needs administrator rights. Do not edit any file in `<REPO>`.

1. **Update the project.** In `<REPO>`, run `git pull`.
2. **Put the mapping copy somewhere private.** Use a folder only you use, outside `<REPO>` and outside Downloads.
3. **Optional trial run.** This checks that PSS/E starts, that the case loads, that the mapping fits the case, and that one city solves. It writes no zip and does not delete the mapping copy.

   ```
   powershell -ExecutionPolicy Bypass -File "<REPO>\docs\data-science\ops\psse_pandapower_session.ps1" -Python "<PYTHON>" -Config "<CONFIG>" -Mapping "<MAPPING COPY>" -Check
   ```

   A good result prints `session: checked`, `check case index: ok`, `check base solve: ok` and `Exit code: 0`.

4. **The real run.** The same command without `-Check`. Leave the laptop plugged in, awake and signed in, and do not close the window. The longest part of the session has a six-hour time limit. How long it really takes is not known until the first run [UNVERIFIED until the session].

   ```
   powershell -ExecutionPolicy Bypass -File "<REPO>\docs\data-science\ops\psse_pandapower_session.ps1" -Python "<PYTHON>" -Config "<CONFIG>" -Mapping "<MAPPING COPY>"
   ```

5. **Paste the summary back.** The window prints a line `==== copy from the next line ====` and later a line `==== copy up to the line above ====`. Copy everything between those two lines, including the line that starts `Exit code:`, and paste it to the owner. It is safe to paste: it has no names, paths or values in it. If you see anything in it that looks like a name or a path, do not paste it; tell the owner instead.
6. **Send the zip.** The zip is on your Desktop and its name starts with `psse_pp_session_`. Send it to the owner by the private channel. Wait for the owner to confirm it arrived.
7. **Delete the zip** from your Desktop (and empty the Recycle Bin).
8. **Check the mapping copy is gone.** The summary line `mapping copy:` should say `deleted`. If it says `not deleted`, delete the file by hand now.

Underneath, the wrapper makes exactly one call, which you never need to type yourself. `DESKTOP` stands for your Desktop folder:

```
<PYTHON> -I -X utf8 -B <REPO>\backend\psse_pandapower_session.py run --config <CONFIG> --mapping <MAPPING COPY> --out-dir DESKTOP
```

The wrapper also removes the temporary folder if PSS/E's log file kept it from being deleted. It only ever removes a folder that appeared during this run.

## What the summary says

| Line | Meaning |
|---|---|
| `session:` | The outcome: `complete`, `partial` (the zip was written but a section failed), `failed`, `interrupted`, or `checked` (a trial run). |
| `mode:` | `run` or `check`. |
| `python:` and `psse:` | The Python and PSS/E version numbers. |
| `section <name>:` | `ok`, `failed` or `skipped` for each of the four sections. |
| `section <name> counts:` | Whole numbers only: how many buses, outages, solves and so on were handled. The owner compares these with what the owner's computer finds in the zip. |
| `section <name> detail:` | A short word saying why a section failed, such as the kind of error. It never holds a name or a path. |
| `members:` | How many files are inside the zip. |
| `zip:` | `written` or `not written`. |
| `mapping copy:` | `deleted` (good), `kept` (a trial run keeps it on purpose) or `not deleted` (delete it by hand). |
| `work folder:` | `deleted`, or `left for the wrapper` (the wrapper removes it; nothing for you to do). |

The last line of the window is `Exit code:` and a number.

| Exit code | What to do |
|---|---|
| 0 | Everything worked. Send the zip. |
| 1 | The session ran, but a section failed or a trial check failed. If `zip: written`, **still send the zip**; the owner needs it to see what failed. Paste the summary either way. If `zip: not written`, there is nothing to send; paste the summary. |
| 2 | Nothing ran. A setting, the mapping file or a flag was wrong, and the window shows a short message. **Stop** and paste the message. The mapping copy is still where you put it. |
| 6 | PSS/E could not be started. **Stop** and paste the summary. |
| 7 | An unexpected error. **Stop** and paste the summary. |
| 130 | Someone interrupted the run (Ctrl+C). No zip was written. Tell the owner. |

## When to stop

- Nobody edits code, settings or the configuration file on the laptop to make something pass.
- Never run a failing command again with different arguments unless the owner tells you the exact new command.
- Use `-Only <section>` (one of `reference`, `settings`, `scaling`; the `network` section always runs) only when the owner asks for it. It runs just that section and writes a new zip.
- Never paste the zip, a file from the zip, or anything from PSS/E's own windows or logs. Only paste the summary between the two `====` lines.
- If something sensitive was pasted by mistake, stop and tell the owner at once.

## After the session (the owner)

1. Put the zip in `data/private/pandapower/incoming/`, and put the mapping copy at `data/private/pandapower/mapping.json`. Both folders are git-ignored; nothing from them is ever committed.
2. Unpack and check the zip, then compare it with the case:

   ```
   .venv/bin/python backend/pandapower_net_check.py ingest --zip data/private/pandapower/incoming/<ZIP>
   .venv/bin/python backend/pandapower_net_check.py check --session data/private/pandapower/sessions/<SESSION> --mapping data/private/pandapower/mapping.json
   ```

   These two commands are built in a later plan of this phase (plan 01-09). Until they exist, the zip simply waits in the private folder.
3. Check that the counts in the pasted summary equal what `ingest` prints. A difference means the zip is not the one the session wrote; ask for it again.
4. Keep a backup of the zip and the mapping copy wherever the mapping is kept (decision D-08). The reference answers never go into a GitHub secret or into CI.
5. Ask the teammate to confirm the zip and the mapping copy are deleted from the laptop.

## What is still UNVERIFIED

Everything about the real PSS/E is unknown until the first real run. In particular: which of the program's ways of writing the network text works and which file revision it writes; whether the calls that read the load-flow settings exist under the names used; whether the settings experiments mean what the notes assume; whether Windows lets the temporary folder be deleted while PSS/E's log is open (the wrapper handles it either way); and how long the session takes. Each of these is written down in the session's code as an assumption, not a fact.
