#!/usr/bin/env python3
"""Does each engine implement a technique, commented or not?

Strict identifier patterns over comment-stripped code (strings included). With --show,
prints the distinct matching identifiers per repo (terminal only, for the hand check);
the CSV holds only counts and the hand-confirmed verdict.
Writes technique_presence.csv: pair, technique, agent, named_in_comments (blocks),
code_identifier_hits, distinct_identifiers, implemented (hand-confirmed y/n/?).
"""
import collections
import csv
import os
import re
import sys

OUT = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = "/tmp/gitgalaxy-scratch/claude/code_only"
IDENT = r"[A-Za-z0-9_-]*"

# technique -> identifier fragment (case-insensitive, matched inside identifiers / strings)
# technique -> (pattern on the lower-cased identifier, optional case-sensitive camelCase pattern)
B = r"(^|[_-])"
E = r"($|[_-])"
CHESS = {
    "zobrist hashing": (r"zobrist|^zkey|hash_?key|hashkey|piece_?keys?$|side_?key|castl\w*_?keys?$|^ep_?keys?$|^hs-\w*key", None),
    "transposition table": (B + "tt" + E + r"|transposition|^tt_?entry|hash_?table|^tt\d|probe_?tt|tt_?probe|store_?tt", r"^tt[A-Z]|[a-z]TT|^TT[A-Z]"),
    "null-move pruning": (r"null_?move|null-move|nullmove|make_?null|null_?ok|do_?null|allow_?null", r"allowNull|doNull"),
    "late move reductions (LMR)": (r"lmr|reductions?" + E + r"|^red$", None),
    "late move pruning (LMP)": (r"lmp|late_?move_?prun", None),
    "futility pruning": (r"futil", None),
    "reverse futility / static null": (B + "rfp" + E + r"|reverse_?futil|static_?null", None),
    "razoring": (r"razor", None),
    "delta pruning": (r"delta_?(prun|margin)|delta-(prun|margin)|^delta$", None),
    "mate distance pruning": (r"mate_?dist|mate-dist|matedist", None),
    "check extension": (r"check_?ext|check-ext|extension|" + B + "ext" + E, None),
    "singular extension": (r"singular|excluded", None),
    "IID / IIR": (B + "(iid|iir)" + E + r"|internal_?iter", None),
    "MVV-LVA": (r"mvv|lva", None),
    "SEE (static exchange)": (B + "see" + E + r"|static_?exchange|staticexchange|^see_?ge$", r"^see[A-Z]"),
    "killer moves": (r"killer", None),
    "history heuristic": (r"^(?!.*(hash|game|key|pos|undo|state|rep|ply_?hist|move_?hist$)).*hist", None),
    "countermove heuristic": (r"counter_?move|counter-move|countermove|cont(inuation)?_?hist", None),
    "quiescence search": (r"quiesc|qsearch|q_search|" + B + "qs" + E, None),
    "PVS / principal variation": (B + "pv" + E + r"|pvs|is_?pv|pv_?node|pvnode|null_?window|zero_?window|^pv_|_pv$|^pv-", r"^pv[A-Z]|isPv|[a-z]Pv[A-Z]"),
    "aspiration window": (r"aspir|^asp_|^asp-|window", None),
    "magic bitboards": (r"magic", None),
    "piece-square tables (PST)": (r"pst|psqt|piece_?square|piecesquare", None),
    "tapered eval": (B + "(mg|eg)" + E + r"|phase|taper", r"^(mg|eg)[A-Z]|[a-z](Mg|Eg)($|[A-Z])"),
    "perft": (r"perft", None),
    "repetition detection": (r"repetit|threefold|rep_?count|is_?draw|isdraw|repet", None),
}
RAW = {  # techniques better seen in statement shape than in a name
    "PVS zero-window re-search": r"-\s*\(?\s*alpha\s*\+\s*1\s*\)?|-\s*alpha\s*-\s*1\b|ALPHA\s*\+\s*1\b|ALPHA\s*-\s*1\b",
    "iterative deepening": r"(?i)iterative|iter_?deep|for\s*\(?\s*(int\s+|let\s+|var\s+)?\w*depth\w*\s*=\s*1\b|for\s+\w*depth\w*\s+in\s+(range\s*\(\s*1|1\s*\.\.)|VARYING\s+[\w-]*DEPTH[\w-]*\s+FROM\s+1|IntStream.rangeClosed\(1",
}
DOMAIN_SETS = {
    "cobol-compress": {
        "LZ77 / LZ": (r"lz77|lzss|" + B + "lz" + E + r"|match-?len|back-?ref|window", None),
        "RLE": (r"rle|run-?len", None),
        "CRC32": (r"crc", None),
        "Huffman": (r"huff", None),
        "hash chains": (r"hash-?chain|hash-?head|chain", None),
        "delta / zigzag / varint": (r"zigzag|varint|delta", None),
    },
    "cobol-sat": {
        "CDCL / clause learning": (r"learn|conflict|analy[sz]e|uip|resolvent", None),
        "watched literals": (r"watch", None),
        "VSIDS / activity": (r"vsids|activity|^ws-act$|bump|decay", None),
        "restarts (Luby)": (r"luby|restart", None),
        "backjumping": (r"backjump|bjump|back-jump", None),
        "phase saving": (r"phase", None),
        "Jeroslow-Wang": (r"jeroslow|" + B + "jw" + E, None),
        "unit propagation / BCP": (r"propagat|unit", None),
        "DIMACS": (r"dimacs|cnf", None),
        "DPLL": (r"dpll", None),
    },
    "cobol-doom": {
        "raycasting / DDA": (r"ray|dda|side-?dist|delta-?dist", None),
        "fisheye correction": (r"fish|perp", None),
        "z-buffer / depth buffer": (r"zbuf|z-buf|depth-?buf|wall-?dist|col-?dist|dist-?buf|zdepth", None),
        "sprites / billboards": (r"sprite|billboard", None),
        "double buffering / framebuffer": (r"framebuf|frame-?buf|back-?buf|screen-?buf|^fb-", None),
        "fixed-point math": (r"fixed|^fp-", None),
        "PRNG / LCG": (r"rand|seed|lcg", None),
    },
    "cobol-pygame": {
        "AABB collision": (r"collid|collision|overlap", None),
        "double buffering / framebuffer": (r"present|flip|framebuf|back-?buf", None),
        "PRNG / LCG": (r"rand|seed|lcg", None),
        "sprites / billboards": (r"sprite|blit|image", None),
    },
}
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
# hand verdicts after reading the --show output (y = implemented, n = not, ? = unclear)
# key: (pair, agent, technique). Default = 'y' if distinct identifiers > 0 else 'n'.
OVERRIDE = {
    # read in the code (comment-free): ordering by victim value * k - attacker value
    ("chess-java", "codex", "MVV-LVA"): "y",
    ("chess-rust", "codex", "MVV-LVA"): "y",
    # Codex Rust takes board, move generation and Zobrist keys from the `chess` crate
    ("chess-rust", "codex", "zobrist hashing"): "library",
    # threefold detection through a key history / seen-keys set
    ("chess-cpp", "codex", "repetition detection"): "y",
    # `materialvalue` is not an LVA identifier; fixed above by the y for java-codex
}


def main():
    show = "--show" in sys.argv
    blocks = list(csv.DictReader(open(os.path.join(OUT, "blocks.csv"))))
    labels = {r["block_id"]: r for r in csv.DictReader(open(os.path.join(OUT, "labels.csv")))}
    files = list(csv.DictReader(open(os.path.join(OUT, "files.csv"))))
    repos = sorted({(f["pair"], f["agent"], f["repo"]) for f in files})
    named = collections.Counter()
    for b in blocks:
        for t in filter(None, labels[b["block_id"]]["techniques"].split(";")):
            named[(b["pair"], b["agent"], t)] += 1
    rows = []
    for pair, agent, repo in repos:
        text = open(os.path.join(CODE_DIR, repo + ".txt")).read()
        techs = CHESS if pair.startswith("chess") else DOMAIN_SETS.get(pair, {})
        toks = collections.Counter(m.group(0).rstrip("-") for m in TOKEN.finditer(text))
        items = list(techs.items()) + (list(RAW.items()) if pair.startswith("chess") else [])
        for t, spec in items:
            if isinstance(spec, str):
                hits = [m.group(0) for m in re.finditer(spec, text)]
                distinct = collections.Counter(h.strip().lower()[:30] for h in hits)
            else:
                lo, camel = spec
                lre = re.compile(lo)
                cre = re.compile(camel) if camel else None
                distinct = collections.Counter()
                for tok, n in toks.items():
                    if lre.search(tok.lower()) or (cre and cre.search(tok)):
                        distinct[tok.lower()] += n
                hits = list(distinct.elements())
            ov = OVERRIDE.get((pair, agent, t))
            verdict = ov if ov else ("y" if distinct else "n")
            rows.append(dict(pair=pair, agent=agent, technique=t, named_in_comments=named[(pair, agent, t)],
                             code_identifier_hits=len(hits), distinct_identifiers=len(distinct), implemented=verdict))
            if show:
                print(f"{pair:15s} {agent:11s} {t:32s} named={named[(pair, agent, t)]:3d} hits={len(hits):4d} ids={', '.join(k for k, _ in distinct.most_common(7))}")
    # PVS: a principal-variation search shows as a zero-window re-search (-alpha-1 / alpha+1)
    zw = {(r["pair"], r["agent"]): r["code_identifier_hits"] for r in rows if r["technique"] == "PVS zero-window re-search"}
    for r in rows:
        if r["technique"] == "PVS / principal variation":
            r["implemented"] = "y" if zw.get((r["pair"], r["agent"]), 0) > 0 else "n"
    # pair summary: techniques named by exactly one agent's comments, and whether the
    # other agent's code implements it anyway
    summ = []
    by = {(r["pair"], r["agent"], r["technique"]): r for r in rows}
    for (pair, agent, t), r in sorted(by.items()):
        if agent not in ("claude", "codex"):
            continue
        other = "codex" if agent == "claude" else "claude"
        o = by.get((pair, other, t))
        if not o:
            continue
        if r["named_in_comments"] > 0 and o["named_in_comments"] == 0:
            summ.append(dict(pair=pair, named_only_by=agent, technique=t, namer_implements=r["implemented"], other_implements=o["implemented"]))
    with open(os.path.join(OUT, "technique_named_by_one.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0].keys()))
        w.writeheader()
        w.writerows(summ)
    c = collections.Counter((x["named_only_by"], x["other_implements"]) for x in summ)
    print("named by one agent only -> other agent's code:", sorted(c.items()))
    own = collections.Counter(r["implemented"] for r in rows if r["named_in_comments"] > 0)
    print("techniques an agent names -> identifier evidence in its OWN code (regex recall proxy):", sorted(own.items()))
    for a in ("claude", "codex"):
        x = [r for r in rows if r["agent"] == a and r["pair"].startswith("chess") and r["technique"] != "PVS zero-window re-search"]
        impl = [r for r in x if r["implemented"] == "y"]
        nm = [r for r in impl if r["named_in_comments"] > 0]
        print(f"{a}: chess technique slots with identifier evidence {len(impl)}; of those named in a comment {len(nm)} ({len(nm)/max(1,len(impl)):.0%})")
    with open(os.path.join(OUT, "technique_presence.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
