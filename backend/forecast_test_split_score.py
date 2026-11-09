"""
TEST-split scoring of the frozen artifacts and the signed TEST veto (SEL-03, D-02, D-11).

What this is. The 12 frozen per-city artifacts were fit on rows before 2026-03-17, so the rows from
2026-03-18T00:00:00Z up to, not including, 2026-09-30T00:00:00Z are out of sample for them. Scoring them there
gives one more check before any pick: a candidate that is worse than the plain forecast (`raw_forecast`) in most
cities on data it never saw is vetoed. It is descriptive and veto-only (D-02): it can never confirm a candidate or
name a winner, and the corridor-era result on this window was already read once, so the window is partly "already
seen". It is permitted only because the owner signed protocol v4 (owner item O7, option A); the scorer refuses to
run unless `forecast_shadow_eval_core.v4_signed()` is true.

Window and data (signed registry rows `test.*`). `TEST_WINDOW_START` <= valid_time < `TEST_WINDOW_END_EXCLUSIVE`,
exact 24 h lead, 784 six-hourly slots per city. The first TEST day (2026-03-17) is excluded because its anchors sit
inside the fit window (the port refuses an anchor before 2026-03-17T00:00Z). The only data is the cached
`_2024-01-20_2026-09-29_` frame of each city, read through `forecast_experiment.anchored_pair_frame` as a cache hit
(no network; a missing cache is a refusal naming the path). The FRESH-dated cache files are never opened: the
provider checks its path with `assert_not_fresh_experiment_cache`, asserts that no row of the frame is on or after
2026-09-30T00:00:00Z, and `run_test_split` refuses any window outside the TEST window, so the guard in
`run_confirmation` always sees a development basis. Archive weather is the frame's own truth columns.

Veto (`evaluate_test_vetoes`). A candidate is vetoed when its per-city MAE is strictly higher than `raw_forecast`'s,
on complete-case pairs, in at least `VETO_MIN_CITIES` (3) of the cities with data. Equal MAE is not losing and a city
without data is not counted.

Conductor bases (`--conductor-basis`). `frozen-drake`: the 12 frozen artifacts under the frozen Drake point (every
city on Drake). `production`: the headline of 07-09 on TEST: each city's production point (AUSTIN at Drake 100 C
under the signed O4), the hash-verified refit cooling and reference artifacts for the differing cities and the frozen
wind artifact; it is refused when no city differs from Drake. The signing copy requires this production re-score
before read 1 is run (`test.rescore_gate = before_read1_run`). The refit root is cwd-relative, so run from the
repository root.

Run by a human offline (the real TEST and ABLATION runs belong to plan 07-11)::

    PYTHONPATH=backend .venv/bin/python backend/forecast_test_split_score.py --conductor-basis frozen-drake
    PYTHONPATH=backend .venv/bin/python backend/forecast_test_split_score.py --conductor-basis production

Truth is reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

import pandas as pd

import city_point
import config
import forecast_conductor_refit
import forecast_experiment
import forecast_experiment_audit
import forecast_shadow_confirm as confirm
import forecast_shadow_eval_core as core
import forecast_shadow_pipeline

TEST_WINDOW_START = pd.Timestamp("2026-03-18T00:00:00Z")
TEST_WINDOW_END_EXCLUSIVE = pd.Timestamp("2026-09-30T00:00:00Z")
TEST_SLOTS_PER_CITY = 784
VETO_MIN_CITIES = 3
EVIDENCE_SUBDIR = "v4-test"
CONDUCTOR_BASES = ("frozen-drake", "production")
# Signed registry `test.rescore_gate` (O4): when Power Systems values are adopted, TEST is re-scored under the production
# conductors (`--conductor-basis production`) before read 1 is RUN. It is a process gate, recorded here and in the
# runbook; this module cannot enforce it.
RESCORE_GATE = "before_read1_run"

# The only cache the TEST provider may open: the frozen window, never a FRESH-dated file.
CACHE_START = forecast_experiment_audit.FROZEN_WINDOW_START
CACHE_END = forecast_experiment_audit.FROZEN_WINDOW_END

VETO_RULE = "mae_strictly_higher_than_raw_forecast_in_at_least_min_cities_of_the_cities_with_data"
RAW = core.FALLBACK_CHOICE
_TRUTH_FIELDS = ("air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity")
DECISION_NOTE = "TEST vetoes only (D-02): no pick or decision is made from this basis"


class ScoringScopeError(ValueError):
    """A TEST run did not cover the signed number of slots in a city (named in the message)."""


# --------------------------------------------------------------------------
# The cached-frame provider
# --------------------------------------------------------------------------

def _cache_path(city: str) -> str:
    return forecast_experiment._cache_path_for(city, CACHE_START, CACHE_END, lead_hours=core.LEAD_HOURS)


def cached_test_provider(city: str, *, evidence_dir: str):
    """
    The frame provider of `run_confirmation` for the TEST window: (frame, archive_weather, meta).

    Reads the city's `_2024-01-20_2026-09-29_` cache through `forecast_experiment.anchored_pair_frame`, which is a
    cache hit; the file must already exist, otherwise this raises `FrameFetchError` naming the path (nothing is
    fetched or written). The path is checked with `core.assert_not_fresh_experiment_cache` before anything is
    opened, and the frame is refused if it holds any row on or after 2026-09-30T00:00:00Z. Archive weather is built
    from the frame's own truth columns. `meta` carries the cache path and its sha256.

    Raises:
        core.EvaluationGuardError: the cache path carries FRESH dates or the frame holds a FRESH row.
        confirm.FrameFetchError: the cache file is absent.
    """
    path = _cache_path(city)
    core.assert_not_fresh_experiment_cache(path)
    if not os.path.isfile(path):
        raise confirm.FrameFetchError(
            f"{city}: the TEST cache {path!r} does not exist; the TEST scorer reads only the cached "
            f"{CACHE_START}..{CACHE_END} frame and never fetches (no network call was made)")
    frame = forecast_experiment.anchored_pair_frame(city, CACHE_START, CACHE_END, lead_hours=core.LEAD_HOURS)
    times = pd.to_datetime(frame["datetime_utc"], utc=True)
    if (times >= TEST_WINDOW_END_EXCLUSIVE).any():
        raise core.EvaluationGuardError(
            f"{city}: the cached frame {path!r} holds a row on or after {TEST_WINDOW_END_EXCLUSIVE.isoformat()}; "
            f"refusing to score it (FRESH rows are never in the TEST basis)")
    weather = frame[["datetime_utc"] + [f"truth_{field}" for field in _TRUTH_FIELDS]].copy()
    weather.columns = ["datetime_utc", *_TRUTH_FIELDS]
    meta = {
        "city": city, "provider": "cached_test_provider", "cache_path": path,
        "cache_sha256": core.sha256_file(path), "fetch_window": [CACHE_START, CACHE_END],
    }
    return frame, weather, meta


def _preflight_caches(cities) -> None:
    """Refuse before any evidence directory exists when a city's TEST cache is absent (all missing paths named)."""
    missing = []
    for city in cities:
        path = _cache_path(city)
        core.assert_not_fresh_experiment_cache(path)
        if not os.path.isfile(path):
            missing.append(path)
    if missing:
        raise confirm.FrameFetchError(
            "the TEST cache is missing for " + "; ".join(missing)
            + ": the TEST scorer reads only the cached frozen-window frames and never fetches")


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def _resolve_test_window(window) -> confirm.ScoredWindow:
    if window is None:
        return confirm.ScoredWindow(TEST_WINDOW_START, TEST_WINDOW_END_EXCLUSIVE)
    if isinstance(window, confirm.ScoredWindow):
        start, end = window.start, window.end
    else:
        start, end = window
    start, end = core.to_utc(start), core.to_utc(end)
    if not (TEST_WINDOW_START <= start < end <= TEST_WINDOW_END_EXCLUSIVE):
        raise ValueError(
            f"window {start.isoformat()}..{end.isoformat()} is outside the TEST window "
            f"{TEST_WINDOW_START.isoformat()}..{TEST_WINDOW_END_EXCLUSIVE.isoformat()} (end exclusive); "
            f"the TEST scorer never scores a FRESH row")
    return confirm.ScoredWindow(start, end)


def _production_basis(cities) -> dict:
    try:
        basis = confirm.conductor_basis(cities)
    except KeyError as exc:      # a city without a usable production table entry
        raise ValueError(f"conductor basis: {exc.args[0] if exc.args else exc}") from exc
    if not basis["differing"]:
        raise ValueError(
            "conductor basis production: no city differs from the frozen Drake configuration, so there is nothing "
            "to re-score under production conductors; use --conductor-basis frozen-drake")
    if basis["problems"]:
        raise core.EvaluationGuardError(
            "conductor basis production: a city's production conductor differs from Drake but its artifacts are not "
            "sound; refusing before any scoring: " + "; ".join(basis["problems"]))
    return basis


def run_test_split(cities, *, evidence_root: str, conductor_basis: str = "frozen-drake", now=None,
                   params: Optional[dict] = None, provider: Callable = cached_test_provider, window=None,
                   expected_slots: Optional[int] = TEST_SLOTS_PER_CITY,
                   model_loader: Optional[Callable] = None) -> dict:
    """
    Score the five candidates per city on the TEST split with the frozen artifacts out of sample, through
    `forecast_shadow_confirm.run_confirmation` with an injected provider and an explicit loader.

    Refuses (nothing created, no provider call) unless the v4 signing copy is signed, the basis is known and the
    window lies inside the TEST window. `conductor_basis` "frozen-drake" scores the frozen artifacts under the frozen
    Drake point; "production" scores under `city_point.production_city_point` with the hash-verified refit
    artifacts for the differing cities, and is refused when no city differs or an artifact is unsound.

    `expected_slots` (default 784) is asserted per city against both `n_in_scope` and `n_with_truth`; `None` skips
    it (development windows). `model_loader` and `provider` are test hooks; the CLI passes neither. The report is
    run_confirmation's, with `report["conductor_basis"]["name"]` set, `report["decision"]` None (TEST never picks)
    and report.json / report.md rewritten to say so.
    """
    cities = list(cities)
    if conductor_basis not in CONDUCTOR_BASES:
        raise ValueError(f"conductor basis {conductor_basis!r} is not one of {list(CONDUCTOR_BASES)}")
    if not core.v4_signed():
        raise core.EvaluationGuardError(
            "protocol v4 is not signed; scoring the frozen artifacts on the TEST split is permitted only by the "
            "signed v4 (owner item O7)")
    win = _resolve_test_window(window)

    run_kwargs: dict = {}
    if conductor_basis == "production":
        basis = _production_basis(cities)
        basis = {**basis, "name": "production"}
        version, root_dir = basis["config_version"], forecast_conductor_refit.REFIT_ROOT
        run_kwargs["point_resolver"] = city_point.production_city_point
        loader = model_loader or forecast_conductor_refit.make_headline_loader(
            version, set(basis["differing"]), root=root_dir, frozen_manifest=forecast_conductor_refit.FROZEN_MANIFEST)
    else:
        basis = {
            "name": "frozen-drake", "config_version": config.RATING_CONFIG_VERSION, "differing": [],
            "headline": "the 12 frozen artifacts under the frozen Drake configuration (every city on Drake)",
        }
        loader = model_loader or forecast_conductor_refit.make_headline_loader(
            config.RATING_CONFIG_VERSION, frozenset(), root=forecast_conductor_refit.REFIT_ROOT,
            frozen_manifest=forecast_conductor_refit.FROZEN_MANIFEST)

    if provider is cached_test_provider:
        _preflight_caches(cities)

    report = confirm.run_confirmation(
        cities=cities, guard_cfg=core.GuardConfig(), evidence_root=evidence_root, protocol_status="signed",
        now=now, params=params, frame_provider=provider, model_loader=loader, window=win, vetoes=None,
        conductor_basis=basis, **run_kwargs)

    report["decision"] = None
    report["decision_note"] = DECISION_NOTE
    report["report_paths"] = core.write_report(report, report["evidence_dir"])

    if expected_slots is not None:
        problems = []
        for city in cities:
            block = report["per_city"][city]
            if block["n_in_scope"] != expected_slots or block["n_with_truth"] != expected_slots:
                failed = block.get("failed")
                problems.append(
                    f"{city}: n_in_scope {block['n_in_scope']}, n_with_truth {block['n_with_truth']}, expected "
                    f"{expected_slots}" + (f" (city failed at {failed['stage']}: {failed['error']})" if failed else ""))
        if problems:
            raise ScoringScopeError(
                "the TEST run did not cover the signed slot count: " + "; ".join(problems)
                + f"; evidence kept at {report['evidence_dir']}")
    return report


# --------------------------------------------------------------------------
# The veto
# --------------------------------------------------------------------------

def _raw_comparison(family: dict, candidate: str) -> dict:
    for comparison in family["comparisons"]:
        if (comparison.get("a"), comparison.get("b")) == (candidate, RAW):
            return comparison
    raise ValueError(
        f"evaluate_test_vetoes: the family has no ({candidate}, {RAW}) comparison; a veto cannot be skipped by omission")


def evaluate_test_vetoes(report: dict, min_cities: int = VETO_MIN_CITIES) -> dict:
    """
    Apply the signed TEST veto to a `run_test_split` report: a real candidate is vetoed when its per-city MAE is
    strictly higher than `raw_forecast`'s, on complete-case pairs, in at least `min_cities` of the cities with data.

    A city loses when its (candidate, raw_forecast) margin (MAE of raw minus MAE of the candidate) is below 0; equal
    MAE is not losing; a city with no margin has no data and is not counted. Returns
    {candidate: {"vetoed": bool, "cities_losing_to_raw": [city, ...], "per_city_mae": {city: (candidate MAE, raw
    MAE)}, "reasons": [str]}} for the three real candidates (`reasons` is empty unless vetoed).

    Raises:
        ValueError: the report has no family or lacks a (candidate, raw_forecast) comparison.
    """
    family = report.get("family")
    if not isinstance(family, dict) or not isinstance(family.get("comparisons"), list):
        raise ValueError("evaluate_test_vetoes: the report has no family of comparisons to read")
    result = {}
    for candidate in core.REAL_CANDIDATES:
        comparison = _raw_comparison(family, candidate)
        margins = comparison.get("per_city_margins") or {}
        per_city = comparison.get("per_city") or {}
        losing, with_data, maes = [], [], {}
        for city, margin in margins.items():
            detail = per_city.get(city) or {}
            maes[city] = (detail.get("mae_a"), detail.get("mae_b"))
            if margin is None or margin != margin:       # no data (None or NaN)
                continue
            with_data.append(city)
            if margin < 0.0:
                losing.append(city)
        vetoed = len(losing) >= min_cities
        reasons = []
        if vetoed:
            reasons.append(
                f"{candidate} has a higher MAE than {RAW} on the TEST window in {len(losing)} of {len(with_data)} "
                f"cities with data ({', '.join(sorted(losing))}); the veto needs at least {min_cities}")
        result[candidate] = {"vetoed": vetoed, "cities_losing_to_raw": sorted(losing), "per_city_mae": maes,
                             "reasons": reasons}
    return result


# --------------------------------------------------------------------------
# Report files
# --------------------------------------------------------------------------

def _standing(verdict: dict):
    """(cities where the candidate beats raw, cities where it loses) from the complete-case MAE pairs."""
    beats, loses = [], []
    for city, (mae_c, mae_r) in verdict["per_city_mae"].items():
        if mae_c is None or mae_r is None:
            continue
        if mae_c < mae_r:
            beats.append(city)
        elif mae_c > mae_r:
            loses.append(city)
    return sorted(beats), sorted(loses)


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def summary_markdown(report: dict, vetoes: dict) -> str:
    """The plain-English TEST summary first, then the per-city MAE table. Nothing here names a winner."""
    basis_name = (report.get("conductor_basis") or {}).get("name", "unspecified")
    window = report.get("scored_window") or [TEST_WINDOW_START.isoformat(), TEST_WINDOW_END_EXCLUSIVE.isoformat()]
    lines = [
        "# TEST-split re-score (SEL-03)", "",
        "## In plain English", "",
        f"The frozen models were fitted on rows before 2026-03-17, so the rows from {window[0]} up to, not "
        f"including, {window[1]} are data they never saw. Conductor basis: {basis_name}. This check can only veto a "
        f"method; it never picks one or confirms one. A method is vetoed when its average error is strictly higher "
        f"than the plain forecast's (raw_forecast), on the rows both have, in at least {VETO_MIN_CITIES} of the "
        f"cities with data; a tie is not a loss.", "",
    ]
    for candidate, verdict in vetoes.items():
        beats, loses = _standing(verdict)
        tail = (f" It beats raw_forecast in {len(beats)} city(ies)" + (f" ({', '.join(beats)})" if beats else "")
                + f" and has a higher error in {len(loses)}" + (f" ({', '.join(loses)})" if loses else "") + ".")
        if verdict["vetoed"]:
            lines.append(f"- {candidate}: WOULD BE VETOED.{tail}")
            lines.extend(f"  - {reason}" for reason in verdict["reasons"])
        else:
            lines.append(f"- {candidate}: not vetoed.{tail}")
    lines += ["", "## Mean absolute error by city (amps, complete-case pairs)", "",
              "| candidate | city | MAE candidate | MAE raw_forecast | result |", "|---|---|---|---|---|"]
    for candidate, verdict in vetoes.items():
        for city, (mae_c, mae_r) in verdict["per_city_mae"].items():
            if mae_c is None or mae_r is None:
                result = "no data"
            elif mae_c < mae_r:
                result = "better than raw"
            elif mae_c > mae_r:
                result = "worse than raw"
            else:
                result = "tie"
            lines.append(f"| {candidate} | {city} | {_fmt(mae_c)} | {_fmt(mae_r)} | {result} |")
    lines += ["", f"Veto rule: `{VETO_RULE}` with min_cities = {VETO_MIN_CITIES} (signed registry `test.veto_min_cities`).",
              "", "TEST can only veto. The window is partly already seen (the corridor-era result on it was read once).",
              ""]
    return "\n".join(lines)


def write_test_report(report: dict, vetoes: dict, out_dir: str) -> dict:
    """
    Write `test_split.json` (the report plus the veto evaluation) and `test_split.md` (a plain-English summary first)
    into a NEW directory. Refuses an existing `out_dir` (FileExistsError) and any directory that is or lies inside
    the frozen model directory (ValueError). Returns the two paths.
    """
    frozen = os.path.realpath(forecast_shadow_pipeline.SHADOW_MODEL_DIR)
    target = os.path.realpath(out_dir)
    if target == frozen or target.startswith(frozen + os.sep):
        raise ValueError(f"refusing to write the TEST report inside the frozen directory {frozen}")
    if os.path.lexists(out_dir):
        raise FileExistsError(f"refusing to overwrite the existing TEST report directory {out_dir}")
    os.makedirs(out_dir)
    body = {
        **report, "cities": list(report.get("per_city") or {}), "vetoes": vetoes,
        "veto_rule": {"rule": VETO_RULE, "min_cities": VETO_MIN_CITIES}, "decision": None,
        "decision_note": DECISION_NOTE,
    }
    json_path = os.path.join(out_dir, "test_split.json")
    md_path = os.path.join(out_dir, "test_split.md")
    with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(core.dumps(body, indent=2) + "\n")
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(summary_markdown(report, vetoes))
    return {"json": json_path, "markdown": md_path}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _default_out_dir(evidence_root: str, now=None) -> str:
    stamp = (datetime.now(timezone.utc) if now is None else core.to_utc(now)).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(evidence_root, f"report_{stamp}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forecast_test_split_score",
        description="TEST-split re-score of the frozen artifacts and the signed TEST veto (SEL-03); veto only, "
                    "permitted only by signed protocol v4.")
    parser.add_argument("--conductor-basis", choices=CONDUCTOR_BASES, default="frozen-drake",
                        help="frozen-drake: the frozen artifacts under Drake; production: each city's production "
                             "conductor with the refit artifacts (refused when no city differs) (default %(default)s)")
    parser.add_argument("--cities", nargs="+", choices=sorted(config.LOCATIONS), default=list(config.LOCATIONS),
                        metavar="CITY")
    parser.add_argument("--evidence-root", default=os.path.join(core.EVIDENCE_ROOT_DEFAULT, EVIDENCE_SUBDIR),
                        help="the evidence run directory is created here (default %(default)s)")
    parser.add_argument("--out-dir", default=None,
                        help="new report directory (default: <evidence-root>/report_<UTC yyyymmddTHHMMSSZ>)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = args.out_dir or _default_out_dir(args.evidence_root)
    try:
        if os.path.lexists(out_dir):
            raise FileExistsError(f"refusing to overwrite the existing TEST report directory {out_dir}")
        report = run_test_split(args.cities, evidence_root=args.evidence_root, conductor_basis=args.conductor_basis)
        vetoes = evaluate_test_vetoes(report)
        paths = write_test_report(report, vetoes, out_dir)
    except (core.EvaluationGuardError, ValueError, FileExistsError, confirm.FrameFetchError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except core.LeakageProbeError as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    except forecast_conductor_refit.ArtifactIntegrityError as exc:
        print(f"failed: an artifact failed its hash check: {exc}", file=sys.stderr)
        return 1
    print(f"TEST report written to {out_dir} ({paths['json']}, {paths['markdown']})")
    print(f"conductor basis {args.conductor_basis}; veto rule {VETO_RULE}; min cities {VETO_MIN_CITIES}")
    for candidate, verdict in vetoes.items():
        print(f"  {candidate}: {'VETOED' if verdict['vetoed'] else 'not vetoed'} "
              f"(higher MAE than raw_forecast in {len(verdict['cities_losing_to_raw'])} city(ies))")
        for reason in verdict["reasons"]:
            print(f"    - {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
