#!/usr/bin/env python3
"""Record the hand check of the classifier and score it.

Samples were drawn by stratified random choice (up to 9-10 blocks per repo, seeds 44
and 45, disjoint from the two tuning samples, seeds 42 and 43). The reviewer read every
block; HAND lists the blocks where the reviewer's class differs from the rule label the
classifier gave AT THE TIME the sample was judged. Blocks not listed were judged correct.

  s3 (seed 44, 135 blocks): judged after tuning rounds 1-2; fixes from it went into round 3.
  s4 (seed 45, 150 blocks): held out -- judged on the round-3 rules before any change,
      then round 4 fixed some of its misses. Its pre-fix score is the reported accuracy.

Writes handcheck.csv (block_id, sample, repo, position, rule_label_at_judging,
hand_label, rule_label_now) and prints accuracies.
"""
import csv
import os

OUT = os.path.dirname(os.path.abspath(__file__))
SCR = "/tmp/gitgalaxy-scratch/claude/cm/"

W, Y, I, D, A, B = "why/rationale", "what/restates", "invariant/assumption/units", "doc/API", "algorithm/domain reference", "banner/divider"
HAND = {
    "s3": {"50": I, "2099": W, "1242": I, "1432": A, "1754": Y, "1667": Y, "2446": I, "2465": W, "2161": W,
           "2238": W, "2267": W, "2236": Y, "2273": W, "2395": D},
    "s4": {"22": D, "1770": I, "2113": W, "2047": W, "2075": Y, "590": Y, "1123": W, "1652": I, "2511": I,
           "2596": W, "2187": Y, "2376": I, "2424": I, "2409": W},
}


def main():
    blocks = {r["block_id"]: r for r in csv.DictReader(open(os.path.join(OUT, "blocks.csv")))}
    now = {r["block_id"]: r["primary"] for r in csv.DictReader(open(os.path.join(OUT, "labels.csv")))}
    rows = []
    for s in ("s3", "s4"):
        for line in open(SCR + s + ".tsv"):
            f = line.rstrip("\n").split("\t")
            bid, rule = f[0], f[3]
            hand = HAND[s].get(bid, rule)
            b = blocks[bid]
            rows.append(dict(block_id=bid, sample=s, repo=b["repo"], agent=b["agent"], position=b["position"],
                             rule_label_at_judging=rule, hand_label=hand, rule_label_now=now[bid]))
    with open(os.path.join(OUT, "handcheck.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for s in ("s3", "s4"):
        x = [r for r in rows if r["sample"] == s]
        a = sum(r["rule_label_at_judging"] == r["hand_label"] for r in x)
        b = sum(r["rule_label_now"] == r["hand_label"] for r in x)
        print(f"{s}: n={len(x)} at-judging {a}/{len(x)} = {a/len(x):.1%}; final rules {b}/{len(x)} = {b/len(x):.1%}")
    import collections
    conf = collections.Counter((r["hand_label"], r["rule_label_at_judging"]) for r in rows if r["sample"] == "s4" and r["hand_label"] != r["rule_label_at_judging"])
    print("s4 misses (hand <- rule):", conf.most_common())
    # per-class recall / precision on s4 at judging
    for c in sorted({r["hand_label"] for r in rows}):
        x = [r for r in rows if r["sample"] == "s4"]
        tp = sum(r["hand_label"] == c and r["rule_label_at_judging"] == c for r in x)
        h = sum(r["hand_label"] == c for r in x)
        p = sum(r["rule_label_at_judging"] == c for r in x)
        print(f"  {c:28s} hand={h:3d} rule={p:3d} tp={tp:3d}")


if __name__ == "__main__":
    main()
