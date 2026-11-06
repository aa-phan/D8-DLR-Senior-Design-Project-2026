# 03-07 Laptop record (session A)

Versions, types and outcomes only. No path, host, user name, case or file name, connection string or key.

## Laptop facts

| Item | Value |
|------|-------|
| Windows | 10 |
| PSS/E | 36.4, free Xplore edition (bus limit not yet confirmed; matters for plan 03-08) |
| PSS/E Python bindings folders | PSSPY313 and PSSPY314, plus psspy |
| Python | 3.14.0, 64-bit (matches PSSPY314) |
| Administrator rights | yes |
| Sleep states | Standby (S0 low power idle, network connected), hibernate, fast startup |
| Clock source | time.windows.com (type 0x9) |
| Licence type, VPN need | open |
| Pooler port 5432 reachable | open |
| BitLocker, antivirus or application control | open |
| Can the user register a scheduled task | open |

## psycopg pin and wheel hashes

Pin: `psycopg[binary]==3.3.6` (the repository pin in requirements.txt). The guide's decision table stops at Python 3.12; Python 3.14 is not in it. PyPI lists a `cp314-cp314-win_amd64` wheel for psycopg-binary 3.3.6, and `requires_python` is 3.10 or newer.

Wheelhouse for this laptop: three packages, not five. typing-extensions is a dependency of psycopg 3.3.6 only for Python before 3.13, and backports.zoneinfo only applies before 3.9, so neither is needed on 3.14. tzdata is needed on Windows.

Package check on PyPI (task 3, blocking-human): approved by the user. Hashes noted from PyPI before any download:

| Package | Version | File | sha256 from PyPI | Wheel as downloaded |
|---------|---------|------|------------------|---------------------|
| psycopg-binary | 3.3.6 | cp314-cp314-win_amd64 | 1fbd30e537dab22cafdf080608f10148fe2a5f3a61294ddb5113caac8a623840 | matched |
| psycopg | 3.3.6 | py3-none-any | a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631 | matched |
| tzdata | 2026.6 | py2.py3-none-any | 0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec | matched |

The wheelhouse held exactly these three files, nothing else.

## Step results

| Step | Status |
|------|--------|
| Step 1 | pass: wheelhouse hashes matched, psycopg 3.3.6 imports from the site folder, config file limited to one account (icacls lists only the user) |
| Step 2 | stopped: selftest exit nonzero, "PSS/E could not be started: PsseUnavailable: psspy could not be imported (ImportError)"; see "Finding from step 2" |
| Step 3 | pending |
| Step 4 | pending |
| Step 5 | pending |
| Step 6 | pending |

## Finding from step 2 (gap-closure item, C-4: no code edited on the laptop)

Importing `psspy` directly, as the launcher does, fails on PSS/E 36.4 with Python 3.14:
`ImportError: DLL load failed while importing psscommon: The specified module could not be found.`

Evidence, all read-only experiments run by hand on the laptop:

1. Appending the PSSPY314 and PSSBIN folders to `sys.path` and importing `psspy`: same ImportError.
2. Additionally registering both folders with `os.add_dll_directory`: same ImportError. So the launcher's current handling (append to the path, register PSSE_BIN_DIR as a DLL folder) is not enough.
3. Appending the PSSPY314 folder, then `import psse3604`, then `import psspy`: `psspy` imported. The PSS/E 36.4 helper `psse3604.py` documents this as the way to set the PSS/E environment before `psspy` from any interpreter ("Use import psse3604 to set PSSE 36.4.x Environment"); it delegates to `psseloc`.

Consequence: the launcher and the Phase 2 adapter (and the probe) must import the version helper (psse3604 for 36.4) before `psspy`. That is a code change for a gap-closure plan (`/gsd-plan-phase 3 --gaps`), not something to edit on the laptop. Steps 2 to 6 wait for it. Open: how the launcher should choose the helper module for other PSS/E versions (the name follows the version, for example psse3604 for 36.4).

Also found: PSS/E 36.4 ships bindings for Python 3.13 and 3.14 (PSSPY313, PSSPY314), not 3.11 as the runbook assumed (U01); the PSS/E program folder is PSSBIN and the bindings folder PSSPY314, both under the install's 36.4 folder.

## Claims cleared

pending

## Claims still UNVERIFIED

pending

## Open questions

- Licence type and whether a VPN is needed.
- Bus limit of the free Xplore edition against the size of Power Systems' real case.
- Whether a scheduled task can be registered for the user's own account.
- Whether the laptop sleeps at :15 (S0 low power idle is available).
