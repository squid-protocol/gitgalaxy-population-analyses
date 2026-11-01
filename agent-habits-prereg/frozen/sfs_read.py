"""Read the pooled sfs runs: does structure group by task+language (the pair partner) or by agent?

For each lens (structure, portable): profile_distance (lower = closer) and shared_structure (higher = closer).
  1. Partner rank: for each paired repo, the rank of its partner among all 38 others (1 = nearest).
  2. Agent signal at fixed language: among COBOL repos (10, five tasks) and among the 5 non-COBOL chess languages
     (portable lens only: cross-language), mean distance same-agent vs cross-agent, cross-task pairs only, with a
     label-permutation p (agent labels shuffled within the set, 10k draws).
  3. Redo: rust-cc-redo vs rust-cc and rust-codex.
"""

import csv
import json
import random
import statistics
from pathlib import Path

BASE = Path("/home/joe/gitgalaxy/chess-study")
import pooled  # noqa: E402

PAIRS = pooled.PAIRS
PARTNER = {}
for cc, cx in PAIRS.values():
    PARTNER[cc], PARTNER[cx] = cx, cc
AGENT = {}
for cc, cx in PAIRS.values():
    AGENT[cc], AGENT[cx] = "cc", "codex"
TASK = {r: fam for fam, pr in PAIRS.items() for r in pr}


def load(lens: str) -> dict:
    d = {}
    with open(BASE / f"sfs-{lens}" / "pairs.csv") as f:
        for row in csv.DictReader(f):
            for k in ("profile_distance", "shared_structure"):
                if k not in row:
                    continue
                v = float(row[k]) if row[k] not in ("", None) else None
                d.setdefault(k, {})[(row["a"], row["b"])] = v
                d[k][(row["b"], row["a"])] = v
    return d


def agent_test(dist: dict, repos: list[str], lower_is_closer: bool) -> dict:
    pairs = [(a, b) for i, a in enumerate(repos) for b in repos[i + 1:] if TASK[a] != TASK[b] and (a, b) in dist]
    labels = {r: AGENT[r] for r in repos}

    def gap(lab):
        same = [dist[p] for p in pairs if lab[p[0]] == lab[p[1]]]
        diff = [dist[p] for p in pairs if lab[p[0]] != lab[p[1]]]
        g = statistics.mean(diff) - statistics.mean(same)
        return g if lower_is_closer else -g, statistics.mean(same), statistics.mean(diff)

    obs, same, diff = gap(labels)
    rng = random.Random(7)
    keys, vals = list(labels), list(labels.values())
    hits = 0
    for _ in range(10000):
        rng.shuffle(vals)
        if gap(dict(zip(keys, vals)))[0] >= obs:
            hits += 1
    return {"same_agent_mean": round(same, 4), "cross_agent_mean": round(diff, 4), "pairs": len(pairs),
            "closer_by": round(obs, 4), "perm_p": round((hits + 1) / 10001, 4)}


def main() -> None:
    out = {}
    cobol = [r for fam, pr in PAIRS.items() if fam.endswith("COBOL") for r in pr]
    chess_other = [r for fam, pr in PAIRS.items() if fam.startswith("chess") and not fam.endswith("COBOL") for r in pr]
    for lens in ("structure", "portable"):
        d = load(lens)
        res = {}
        for metric, lower in (("profile_distance", True), ("shared_structure", False)):
            if metric not in d:
                continue
            dist = d[metric]
            ranks = {}
            for r in PARTNER:
                others = [(v, b) for (a, b), v in dist.items() if a == r and v is not None]
                others.sort(key=lambda t: t[0], reverse=not lower)
                ranks[r] = next((i + 1 for i, (_, b) in enumerate(others) if b == PARTNER[r]), None)
            m = {"partner_rank": ranks, "partner_is_nearest": sum(v == 1 for v in ranks.values()),
                 "of": len(ranks), "median_partner_rank": statistics.median(v for v in ranks.values() if v)}
            m["agent_within_cobol"] = agent_test(dist, cobol, lower)
            if lens == "portable":
                m["agent_within_chess_other_langs"] = agent_test(dist, chess_other, lower)
            redo = "agentic-chessengine-rust-cc-redo"
            m["redo"] = {b: dist.get((redo, b)) for b in ("agentic-chessengine-rust-cc", "agentic-chessengine-rust-codex")}
            res[metric] = m
        out[lens] = res
    (BASE / "sfs_pooled.json").write_text(json.dumps(out, indent=1) + "\n")
    for lens, res in out.items():
        for metric, m in res.items():
            print(f"[{lens} / {metric}] partner nearest {m['partner_is_nearest']}/{m['of']}, median partner rank "
                  f"{m['median_partner_rank']} of 38; redo {m['redo']}")
            for k in ("agent_within_cobol", "agent_within_chess_other_langs"):
                if k in m:
                    print(f"    {k}: {m[k]}")
        print("    partner ranks (profile_distance):",
              {k.replace('agentic-', '').replace('chessengine-', ''): v for k, v in res["profile_distance"]["partner_rank"].items()})


if __name__ == "__main__":
    main()
