"""Diff two truth fetches (truth vs truth only; no predictions). Usage: compare_truth.py FILE_A FILE_B
Prints per variable: hours compared, hours changed, max abs change."""
import sys, json
a, b = (json.load(open(f)) for f in sys.argv[1:3])
print("fetched:", a["fetched_at_utc"], "->", b["fetched_at_utc"])
ha, hb = a["response"]["hourly"], b["response"]["hourly"]
ia = {t: i for i, t in enumerate(ha["time"])}
common = [t for t in hb["time"] if t in ia]
print("hours in A:", len(ha["time"]), "in B:", len(hb["time"]), "common:", len(common))
for k in ha:
    if k == "time": continue
    diffs = []
    for t in common:
        x, y = ha[k][ia[t]], hb[k][hb["time"].index(t)]
        if x is None or y is None:
            if x is not y: diffs.append((t, float("inf")))
        elif x != y: diffs.append((t, abs(x - y)))
    mx = max((d for _, d in diffs), default=0.0)
    print(f"{k}: changed {len(diffs)}/{len(common)}, max abs change {mx}", ("first changed: " + diffs[0][0]) if diffs else "")
