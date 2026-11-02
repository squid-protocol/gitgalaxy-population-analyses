"""Exploratory (not registered): can the structural fingerprint alone tell which model wrote a program?
For each run, its nearest neighbour by sfs profile distance among the other runs of the SAME task+language is taken;
a hit = same model. Chance = the share of same-model candidates; significance by permuting model labels within cells.
Usage: python identify_model.py PAIRS_CSV   (sat-c-codex-r1 left out: no function of >= 3 lines)
"""
import csv, json, random, re, sys
MODEL = {"claude": "sonnet", "sonnet-b": "sonnet", "codex": "codex", "haiku": "haiku", "haiku-b": "haiku"}
RX = re.compile(r"(chess|sat)-(c|java|python|rust|cobol)-(claude|codex|haiku|haiku-b|sonnet-b)-r(\d)")
d = {}
for r in csv.DictReader(open(sys.argv[1])):
    d[(r["a"], r["b"])] = d[(r["b"], r["a"])] = float(r["profile_distance"])
ids = sorted({a for a, _ in d} - {"sat-c-codex-r1"})
cell = {i: "-".join(RX.fullmatch(i).group(1, 2)) for i in ids}
model = {i: MODEL[RX.fullmatch(i)[3]] for i in ids}
def hits(m):
    h = t = 0
    for i in ids:
        cand = [j for j in ids if j != i and cell[j] == cell[i]]
        if any(m[j] == m[i] for j in cand):
            t += 1; h += m[min(cand, key=lambda j: d[(i, j)])] == m[i]
    return h, t
h, t = hits(model)
chance = []
for i in ids:
    cand = [j for j in ids if j != i and cell[j] == cell[i]]
    if any(model[j] == model[i] for j in cand):
        chance.append(sum(model[j] == model[i] for j in cand) / len(cand))
rng = random.Random(7); null = []
for _ in range(2000):
    m2 = dict(model)
    for c in set(cell.values()):
        mem = [i for i in ids if cell[i] == c]; lab = [model[i] for i in mem]; rng.shuffle(lab); m2.update(zip(mem, lab))
    null.append(hits(m2)[0])
print(json.dumps({"hits": h, "of": t, "accuracy": round(h / t, 3), "chance": round(sum(chance) / len(chance), 3),
                  "permutation_p": round((sum(x >= h for x in null) + 1) / 2001, 4)}))
