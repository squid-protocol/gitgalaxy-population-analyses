"""README section 5: what GitGalaxy's COBOL debt and dead-code readings count on these systems.

    python scoring_checks.py --repos WORK/repos --scans WORK/scans

1. Every paragraph GitGalaxy marks unreferenced (usage_status 1): is it the first paragraph after a PROCEDURE
   DIVISION header, the program's entry point by fall-through?
2. Every comment line GitGalaxy's COBOL dead_code rule matches (rule 12 in its cobol.py, copied verbatim below),
   printed, so a reader can see whether it is commented-out code or prose. Comment lines only, no code is shown.
"""

import argparse
import re
import sqlite3
from pathlib import Path

from measure import PAIRS, scan_db

DEAD_CODE_RULE = re.compile(r"^(?:.{6}\*|[ \t]*\*>)[ \t]*(?:MOVE|COMPUTE|IF|PERFORM|CALL|EXEC)\b", re.I | re.M)
PROCEDURE_DIVISION = re.compile(r"PROCEDURE\s+DIVISION", re.I)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repos", type=Path, required=True)
    ap.add_argument("--scans", type=Path, required=True)
    a = ap.parse_args()
    repos = [r for pair in PAIRS.values() for r in pair]
    print("1. unreferenced paragraphs")
    for repo in repos:
        con = sqlite3.connect(f"file:{scan_db(a.scans, repo)}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT d.file_path, f.func_name, f.start_line FROM function_data f JOIN file_data d ON d.id = f.file_id"
            " WHERE lower(d.language) = 'cobol' AND f.usage_status = 1 AND coalesce(f.def_shape, '') != 'main_line'"
        ).fetchall()
        con.close()
        for path, name, start in rows:
            lines = (a.repos / repo / path).read_text(errors="replace").splitlines()
            prev = next((ln for ln in reversed(lines[: start - 1]) if ln.strip() and not ln.strip().startswith("*")), "")
            print(f"   {repo}:{path}:{start} {name}  entry paragraph: {bool(PROCEDURE_DIVISION.search(prev))}")
    print("2. comment lines the dead_code rule matches")
    for repo in repos:
        root = a.repos / repo
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() in {".cob", ".cbl", ".cpy"} and ".gitgalaxy" not in p.parts:
                for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                    if DEAD_CODE_RULE.match(line):
                        print(f"   {repo}:{p.relative_to(root)}:{n}: {line.strip()[:100]}")


if __name__ == "__main__":
    main()
