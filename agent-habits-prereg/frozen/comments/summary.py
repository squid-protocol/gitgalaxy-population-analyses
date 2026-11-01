#!/usr/bin/env python3
"""Extra cuts for results.md: technique naming per pair, identifier lengths, COBOL
banners, Codex specifics, rust redo. Writes pair_summary.csv, identifiers.csv,
cobol_paragraph_comments.csv, codex_comment_kinds.csv and prints a digest."""
import collections
import csv
import os
import re
import statistics

OUT = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = "/tmp/gitgalaxy-scratch/claude/code_only"
MAIN = ["chess-c", "chess-cpp", "chess-java", "chess-python", "chess-rust", "chess-cobol", "cobol-compress", "cobol-doom", "cobol-pygame", "cobol-sat"]
KW = set("""if else for while return int void char const static struct break continue case switch default unsigned long short
double float bool true false null none self def class import from pub fn let mut impl use mod match enum type where as in not and or
public private protected final new this extends implements package interface throws try catch elif pass lambda yield with is
uint64_t uint8_t uint16_t uint32_t int64_t int32_t size_t auto std string vector include define ifdef endif ifndef
move to perform compute until varying from by add subtract display end-if end-perform pic value is when evaluate other then
exit section division working-storage procedure data identification program-id end-evaluate set of thru times call using""".split())


def load(n):
    return list(csv.DictReader(open(os.path.join(OUT, n))))


def write(n, rows):
    with open(os.path.join(OUT, n), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    blocks = load("blocks.csv")
    lab = {r["block_id"]: r for r in load("labels.csv")}
    for b in blocks:
        b.update({k: v for k, v in lab[b["block_id"]].items() if k != "block_id"})
    pres = load("technique_presence.csv")
    nb1 = load("technique_named_by_one.csv")
    defs = load("defs.csv")
    files = load("files.csv")
    repo_of = {(f["pair"], f["agent"]): f["repo"] for f in files}

    # ------------------------------------------------ per pair technique naming
    ps = []
    for p in MAIN + ["chess-ruby"]:
        row = dict(pair=p)
        for a in ("claude", "codex"):
            x = [r for r in pres if r["pair"] == p and r["agent"] == a and r["technique"] != "PVS zero-window re-search"]
            named = {r["technique"] for r in x if int(r["named_in_comments"]) > 0}
            impl = {r["technique"] for r in x if r["implemented"] == "y"}
            row[f"{a}_techniques_with_code_evidence"] = len(impl)
            row[f"{a}_of_those_named_in_comments"] = len(impl & named)
            row[f"{a}_distinct_named_all_vocab"] = len({t for b in blocks if b["pair"] == p and b["agent"] == a for t in b["techniques"].split(";") if t})
        y = [r for r in nb1 if r["pair"] == p]
        row["named_only_by_claude"] = sum(1 for r in y if r["named_only_by"] == "claude")
        row["..._codex_code_has_it"] = sum(1 for r in y if r["named_only_by"] == "claude" and r["other_implements"] == "y")
        row["..._codex_uses_library"] = sum(1 for r in y if r["named_only_by"] == "claude" and r["other_implements"] == "library")
        row["named_only_by_codex"] = sum(1 for r in y if r["named_only_by"] == "codex")
        row["..._claude_code_has_it"] = sum(1 for r in y if r["named_only_by"] == "codex" and r["other_implements"] == "y")
        ps.append(row)
    write("pair_summary.csv", ps)
    print("PAIR TECHNIQUES")
    for r in ps:
        print("  ", r)
    m = [r for r in ps if r["pair"] in MAIN]
    for a in ("claude", "codex"):
        ev = sum(r[f"{a}_techniques_with_code_evidence"] for r in m)
        nm = sum(r[f"{a}_of_those_named_in_comments"] for r in m)
        print(f"MAIN {a}: techniques with code evidence {ev}, named in a comment {nm} ({nm/ev:.0%})")
    print("MAIN named only by claude:", sum(r["named_only_by_claude"] for r in m), "codex code has it:", sum(r["..._codex_code_has_it"] for r in m),
          "library:", sum(r["..._codex_uses_library"] for r in m), "| named only by codex:", sum(r["named_only_by_codex"] for r in m),
          "claude code has it:", sum(r["..._claude_code_has_it"] for r in m))

    # ------------------------------------------------ vocabulary per agent (main pairs)
    voc = collections.Counter()
    for b in blocks:
        if b["pair"] in MAIN:
            for t in filter(None, b["techniques"].split(";")):
                voc[(b["agent"], t)] += 1
    print("VOCAB claude top:", [(t, n) for (a, t), n in voc.most_common() if a == "claude"][:25])
    print("VOCAB codex:", [(t, n) for (a, t), n in voc.most_common() if a == "codex"])
    print("distinct techniques named: claude", len({t for (a, t) in voc if a == "claude"}), "codex", len({t for (a, t) in voc if a == "codex"}))

    # ------------------------------------------------ identifiers
    idr = []
    tok = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*[A-Za-z0-9_]|[A-Za-z]")
    for (p, a), repo in sorted(repo_of.items()):
        t = open(os.path.join(CODE_DIR, repo + ".txt")).read()
        ids = {x for x in tok.findall(t) if x.lower() not in KW and not x.isupper() or (p.startswith("cobol") or p == "chess-cobol")}
        ids = {x for x in ids if x.lower() not in KW}
        L = [len(x) for x in ids]
        idr.append(dict(pair=p, agent=a, distinct_identifiers=len(ids), mean_len=round(statistics.mean(L), 1), median_len=statistics.median(L),
                        share_len_ge_15=round(sum(1 for x in L if x >= 15) / len(L), 3)))
    write("identifiers.csv", idr)
    print("IDENTIFIERS")
    for r in idr:
        print("  ", r)

    # ------------------------------------------------ COBOL paragraph comments
    cp = []
    for p in ["chess-cobol", "cobol-compress", "cobol-doom", "cobol-pygame", "cobol-sat"]:
        for a in ("claude", "codex"):
            repo = repo_of.get((p, a))
            ds = [d for d in defs if d["repo"] == repo and d["kind"] in ("para", "section")]
            bs = [b for b in blocks if b["repo"] == repo]
            tgt = {(b["file"], b["target_def"]): b for b in bs if b["target_def"]}
            framed = sum(1 for d in ds if (d["file"], d["line"]) in tgt and tgt[(d["file"], d["line"])]["framed"] == "1")
            spacer = sum(1 for b in bs if b["primary"] == "banner/divider" and int(b["content_words"]) == 0)
            col7 = 0
            cp.append(dict(pair=p, agent=a, paragraphs=len(ds), with_preceding_comment=sum(int(d["commented"]) for d in ds),
                           with_framed_banner=framed, banner_blocks=sum(1 for b in bs if b["primary"] == "banner/divider"),
                           empty_spacer_blocks=spacer, blocks=len(bs),
                           doc_api_blocks=sum(1 for b in bs if b["primary"] == "doc/API")))
    write("cobol_paragraph_comments.csv", cp)
    print("COBOL")
    for r in cp:
        print("  ", r)

    # ------------------------------------------------ what Codex's comments are
    ck = collections.Counter()
    for b in blocks:
        if b["agent"] != "codex" or b["pair"] not in MAIN:
            continue
        kind = b["primary"]
        ck[(b["pair"], kind, b["position"])] += 1
    rows = [dict(pair=p, primary=k, position=pos, blocks=n) for (p, k, pos), n in sorted(ck.items())]
    write("codex_comment_kinds.csv", rows)
    cx = [b for b in blocks if b["agent"] == "codex" and b["pair"] in MAIN]
    print("CODEX blocks", len(cx), "by pair", collections.Counter(b["pair"] for b in cx))
    print("CODEX test-tagged", sum(1 for b in cx if b["test"] == "1"), "tools-path", sum(1 for b in cx if re.search(r"(^|/)(tools|scripts)/", b["file"])))
    print("CODEX namespace-closers", sum(1 for b in cx if b["primary"] == "what/restates" and b["position"] == "trailing" and int(b["content_words"]) <= 3))
    print("CODEX words>=9", sum(1 for b in cx if int(b["words"]) >= 9))
    # step-label shape: inside-body, 1 line, <=6 words, what or technique
    for a in ("claude", "codex"):
        x = [b for b in blocks if b["agent"] == a and b["pair"] in MAIN]
        lab_ = [b for b in x if b["position"] == "inside_body" and b["lines"] == "1" and int(b["content_words"]) <= 6]
        print(f"{a}: inside-body one-line <=6-word step labels {len(lab_)}/{len(x)} = {len(lab_)/len(x):.2f}")

    # ------------------------------------------------ redo vs rust-cc
    for a, p in (("claude", "chess-rust"), ("claude-redo", "chess-rust-redo"), ("codex", "chess-rust")):
        x = [b for b in blocks if b["agent"] == a and b["pair"] == p]
        c = collections.Counter(b["primary"] for b in x)
        print("RUST", a, len(x), {k: round(v / len(x), 3) for k, v in c.most_common()})


if __name__ == "__main__":
    main()
