"""The output and comment signals behind README section 5, per 100 COBOL coding lines, per system.

    python signals.py --scans WORK/scans

GitGalaxy's `debt` family is planned_debt (TODO-style markers) + fragile_debt (HACK-style) + debug_prints (in
COBOL: DISPLAY / EXHIBIT) + duplicates; its `dead_code` family is commented-out statements + units unreferenced
by name. Printing the parts separately shows what the families measure on these systems.
"""

import argparse
import sqlite3
from pathlib import Path

from measure import PAIRS, scan_db

COLS = ["state_planned_debt", "state_fragile_debt", "state_print_hits", "state_slop_duplicates", "sec_dead_code",
        "state_unreferenced"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scans", type=Path, required=True)
    a = ap.parse_args()
    print(f"{'family':24}{'agent':13}" + "".join(f"{c.split('_', 1)[1]:>17}" for c in COLS))
    for fam, pair in PAIRS.items():
        for agent, repo in zip(("Claude Code", "Codex"), pair, strict=True):
            con = sqlite3.connect(f"file:{scan_db(a.scans, repo)}?mode=ro", uri=True)
            r = con.execute(f"SELECT sum(coding_loc), {', '.join(f'sum(coalesce({c}, 0))' for c in COLS)} "  # noqa: S608
                            "FROM file_data WHERE lower(language) = 'cobol'").fetchone()
            con.close()
            loc = r[0] or 1
            print(f"{fam:24}{agent:13}" + "".join(f"{100.0 * (v or 0) / loc:17.2f}" for v in r[1:]))


if __name__ == "__main__":
    main()
