"""Aggregate fleet timing telemetry from a batch run's per-repo scanlogs.

batch_process_restored.py (with timing ON, its default) persists each repo's
full engine stdout as <repo>/<name>_galaxy_scanlog.txt[.gz]. This script walks a
batch output directory, parses the --file-speed / --splicing-speed charts out of
every scanlog, and writes one JSON line per repo to fleet_timing.jsonl, then
prints a fleet report:

  1. Fleet-wide per-phase CPU totals and shares (which phase dominates the
     population, not just curl/ALR).
  2. Rule x language CPU ranking (the gate-work target list for #3182/#3171,
     measured on the real population).
  3. The scan-rate-vs-size line fit (log-log slope of LOC/s vs LOC) and each
     phase's share-vs-size trend -- the direct decomposition of the
     "scan rate degrades with repo size" question (#3175 lineage).

Caveats baked into the data (see the harness commit): --splicing-speed samples
rule timing over the first 5000 files per repo and the chart prints only the
top-15 rules, so rule totals are a top-K union -- robust for ranking heavy
hitters, not a complete census. Wall times ride whatever else the batch box was
doing; per-phase/per-rule SHARES are the trustworthy signal.

Usage:
    python aggregate_fleet_timing.py /srv/storage_16tb/projects/gitgalaxy-raw-output/v2.9.0
    python aggregate_fleet_timing.py <batch_output_dir> --jsonl fleet_timing.jsonl --top 25
"""

import argparse
import gzip
import json
import math
import re
import sys
from pathlib import Path

# --- Engine log signatures (must track galaxyscope's chart renderers) ---
RE_TELEMETRY = re.compile(r"Processed\s+([\d,]+)\s+lines of code at\s+([\d,]+)\s+LOC/s")
RE_PIPELINE = re.compile(r"PIPELINE_SUCCESS:\s+([\d,]+)\s+files mapped in\s+([\d.]+)s")
RE_BAR_LINE = re.compile(r"^\s*([\d.]+)s\s*\|.*\|\s*(.+?)\s*$")
RE_AVG_SUFFIX = re.compile(r"\s*\(Avg: [\d.]+ms/file\)\s*$")

HDR_FILE_SPEED = "FILE SPEED (MACRO PHASE) TELEMETRY REPORT"
HDR_SPLICING = "SPLICING SPEED TELEMETRY REPORT"
HDR_PHASES = "[ CUMULATIVE TIME SPENT ACROSS"
HDR_SLOW_FILES = "[ TOP 10 SLOWEST FILES"
HDR_REGEX = "[ CUMULATIVE REGEX EXECUTION TIME"


def read_scanlog(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            return f.read()
    return path.read_text(encoding="utf-8", errors="replace")


def parse_scanlog(text: str) -> dict:
    """Extract telemetry + both timing charts from one repo's engine stdout."""
    rec = {
        "loc": None,
        "rate_loc_s": None,
        "files_mapped": None,
        "engine_wall_s": None,
        "phases_s": {},       # phase label -> cumulative worker seconds
        "rules_s": {},        # "lang::rule" -> cumulative seconds (top-15 sample)
        "slow_files": [],     # [ [seconds, path], ... ] (top-10)
        "sampled_files": None,
    }
    section = None
    for line in text.splitlines():
        m = RE_TELEMETRY.search(line)
        if m:
            rec["loc"] = int(m.group(1).replace(",", ""))
            rec["rate_loc_s"] = int(m.group(2).replace(",", ""))
            continue
        m = RE_PIPELINE.search(line)
        if m:
            rec["files_mapped"] = int(m.group(1).replace(",", ""))
            rec["engine_wall_s"] = float(m.group(2))
            continue

        if HDR_PHASES in line:
            section = "phases"
            continue
        if HDR_SLOW_FILES in line:
            section = "slow_files"
            continue
        if HDR_REGEX in line:
            section = "rules"
            sm = re.search(r"Sampled (\d+) Files", line)
            if sm:
                rec["sampled_files"] = int(sm.group(1))
            continue
        # Any other bracket header / report banner ends the current section.
        if line.strip().startswith("[") or "TELEMETRY REPORT" in line or line.strip().startswith("="):
            if HDR_FILE_SPEED not in line and HDR_SPLICING not in line:
                section = None
            continue

        if section:
            m = RE_BAR_LINE.match(line)
            if not m:
                continue
            seconds, label = float(m.group(1)), m.group(2)
            if section == "phases":
                rec["phases_s"][RE_AVG_SUFFIX.sub("", label)] = seconds
            elif section == "rules":
                rec["rules_s"][label] = seconds
            elif section == "slow_files":
                rec["slow_files"].append([seconds, label])
    return rec


def find_scanlogs(batch_dir: Path):
    """Yield (repo_output_name, scanlog_path); prefers .txt over .txt.gz when both exist."""
    for repo_dir in sorted(p for p in batch_dir.iterdir() if p.is_dir()):
        hits = sorted(repo_dir.glob("*_galaxy_scanlog.txt")) + sorted(repo_dir.glob("*_galaxy_scanlog.txt.gz"))
        if hits:
            yield repo_dir.name, hits[0]


def linefit_loglog(xs, ys):
    """Least-squares slope/intercept of log10(y) on log10(x). Returns (slope, r)."""
    pts = [(math.log10(x), math.log10(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    n = len(pts)
    if n < 3:
        return None, None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    if sxx == 0 or syy == 0:
        return None, None
    slope = sxy / sxx
    r = sxy / math.sqrt(sxx * syy)
    return slope, r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("batch_dir", type=Path, help="batch output dir (contains one folder per scanned repo)")
    ap.add_argument("--jsonl", type=Path, default=None,
                    help="output path for fleet_timing.jsonl (default: <batch_dir>/fleet_timing.jsonl)")
    ap.add_argument("--top", type=int, default=25, help="rows to show in the rule ranking")
    args = ap.parse_args(argv)

    out_path = args.jsonl or (args.batch_dir / "fleet_timing.jsonl")
    records = []
    skipped = 0
    for name, log_path in find_scanlogs(args.batch_dir):
        rec = parse_scanlog(read_scanlog(log_path))
        if rec["loc"] is None and not rec["phases_s"]:
            skipped += 1  # crashed/partial scan -- log kept on disk, nothing parseable
            continue
        rec["repo"] = name
        records.append(rec)

    if not records:
        print(f"No parseable scanlogs under {args.batch_dir} ({skipped} skipped). "
              f"Was the batch run with timing enabled (the default)?")
        return 1

    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    # ---------------- FLEET REPORT ----------------
    print(f"fleet_timing.jsonl: {len(records)} repos -> {out_path}  ({skipped} unparseable skipped)")

    # 1. Per-phase fleet totals.
    phase_totals: dict[str, float] = {}
    for rec in records:
        for phase, s in rec["phases_s"].items():
            phase_totals[phase] = phase_totals.get(phase, 0.0) + s
    grand = sum(phase_totals.values()) or 1.0
    print("\n[ FLEET PER-PHASE CUMULATIVE WORKER CPU ]")
    for phase, s in sorted(phase_totals.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {s:10.1f}s  {s / grand * 100:5.1f}%  {phase}")

    # 2. Rule x language ranking (top-K union; see module docstring caveat).
    rule_totals: dict[str, float] = {}
    rule_repos: dict[str, int] = {}
    for rec in records:
        for rule, s in rec["rules_s"].items():
            rule_totals[rule] = rule_totals.get(rule, 0.0) + s
            rule_repos[rule] = rule_repos.get(rule, 0) + 1
    print(f"\n[ TOP {args.top} RULES BY FLEET CPU (top-15-per-repo union) ]")
    for rule, s in sorted(rule_totals.items(), key=lambda kv: kv[1], reverse=True)[: args.top]:
        print(f"  {s:9.2f}s  in {rule_repos[rule]:4d} repos  {rule}")

    # 3. Scan-rate-vs-size line fit + per-phase share trend.
    sized = [r for r in records if r["loc"] and r["rate_loc_s"]]
    slope, r_coef = linefit_loglog([r["loc"] for r in sized], [r["rate_loc_s"] for r in sized])
    print("\n[ SCAN RATE vs SIZE ]")
    if slope is None:
        print(f"  need >=3 sized repos for a fit (have {len(sized)})")
    else:
        print(f"  log10(LOC/s) ~ {slope:+.3f} * log10(LOC)   (r={r_coef:.2f}, n={len(sized)})")
        print("  slope < 0 means scan rate degrades with repo size; 0 = size-neutral.")
        # Which phase's SHARE grows with size? The degradation decomposition.
        print("  per-phase share-vs-size slope (share pts per decade of LOC):")
        for phase in sorted(phase_totals, key=phase_totals.get, reverse=True):
            pts = [
                (math.log10(r["loc"]), r["phases_s"][phase] / tot)
                for r in sized
                if phase in r["phases_s"] and (tot := sum(r["phases_s"].values())) > 0
            ]
            if len(pts) < 3:
                continue
            n = len(pts)
            mx = sum(p[0] for p in pts) / n
            my = sum(p[1] for p in pts) / n
            sxx = sum((p[0] - mx) ** 2 for p in pts)
            if sxx == 0:
                continue
            ph_slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
            print(f"    {ph_slope * 100:+7.2f} pts/decade  {phase}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
