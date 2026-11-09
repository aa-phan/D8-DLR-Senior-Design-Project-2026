# Draft email to Power Systems (not sent as of 2026-11-08)

Fill in the recipient's name; "about two hours" is a guess; check the four study-scope bullets against docs/data-science/decisions/psse_study_definitions.md.

**Subject:** What we need from Power Systems to finish the PSS/E hookup (a saved case, a city-to-branch mapping, laptop session)

Hi [name],

The software is built and tested against a stand-in for PSS/E. The next step is running it on the real thing, and it's blocked on three items from you.

**1. A saved copy of the case (nothing to send)**
The 39-bus New England network is already on the laptop. Our job runs outside the PSS/E window and reads the case from a file on disk, so we need a `.sav` of the base case (File -> Save Case As) in a folder on the laptop outside our repository. Tell us the folder. Please confirm: the case solves (`fnsl` converges), the PSS/E version it was saved in (we run 36.4), and whether any generator or load data differs from the standard IEEE 39-bus case. The job never saves over your file (ratings change in memory only); nothing goes into our public GitHub repo.

**2. The city-to-branch mapping**
The 39-bus system has no Austin or El Paso, so please decide which branches stand in for AUSTIN, CORPUS_CHRISTI, MIDLAND and EL_PASO. For each city:
- Branches: from-bus, to-bus, circuit ID (e.g. 16, 19, "1"). PSS/E: Power Flow -> Network data. Easier: once on the laptop our probe prints the branch list and you pick from it.
- Both ends of a mapped line at the same nominal kV (no transformers or mixed voltages); the job converts amps to MVA with that kV.
- One or more sink (load) buses per city, named.
- A short table is fine; we turn it into JSON (shape: docs/data-science/schema/psse_mapping_example.json, fake numbers). Send the real mapping privately, never commit it.
Study-scope questions (docs/data-science/decisions/psse_study_definitions.md; we use the documented defaults and label results "not a full N-1 study" until answered): which rating set to write; overwrite the case's own ratings on mapped lines in memory only?; base-case violations before our ratings?; voltage and thermal limits.

**3. Laptop access and checklist** (about two hours first session, then a review session with you)
- Licence: local, dongle or network; VPN needed?
- Free Xplore edition bus limit (39-bus should fit)
- Can we register a Windows scheduled task under the user's own account (no admin needed)?
- Can it stay awake and plugged in at :15 (`powercfg /a`)?
- Can it reach the database pooler on port 5432?
- BitLocker, antivirus or application control that would block a new script folder?
- Which days, and a person to sit with us?

Everything is read-only against your system.

Thanks,
Tejaswini
