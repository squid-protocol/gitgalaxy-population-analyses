#!/usr/bin/env python3
"""Rule-based classifier for comment blocks (blocks.csv -> labels.csv).

One primary class per block (priority order below) plus multi-label flags, and the
named techniques each block mentions. Rules are keyword / shape rules; accuracy is
measured by hand on a random sample (see handcheck.csv and results.md).
"""
import csv
import json
import os
import re

OUT = os.path.dirname(os.path.abspath(__file__))
TEXT_CACHE = "/tmp/gitgalaxy-scratch/claude/comment_blocks_text.jsonl"

# --------------------------------------------------------------- technique vocabulary
# name -> regex over comment text (case-insensitive). Algorithms, heuristics, protocols,
# formats and named data structures; plain game rules (castling, en passant) are
# "domain terms" and listed separately.
TECH = {
    # chess search
    "alpha-beta": r"alpha[- ]?beta|\bnegamax\b|\bminimax\b|beta[- ]cut",
    "PVS / principal variation": r"\bpvs\b|principal[- ]variation|\bpv[- ](node|move|line|search|table)|null[- ]window|zero[- ]window",
    "iterative deepening": r"iterative[- ]deepening|\bID loop",
    "aspiration window": r"aspiration",
    "quiescence search": r"quiescen|\bqsearch\b|q-search",
    "transposition table": r"transposition|\bTT\b",
    "zobrist hashing": r"zobrist",
    "null-move pruning": r"null[- ]?move",
    "late move reductions (LMR)": r"\blmr\b|late[- ]move[- ]reduc",
    "late move pruning (LMP)": r"\blmp\b|late[- ]move[- ]prun",
    "futility pruning": r"futility",
    "reverse futility / static null": r"reverse[- ]futility|static[- ]null",
    "razoring": r"razor",
    "delta pruning": r"delta[- ]prun",
    "mate distance pruning": r"mate[- ]distance",
    "check extension": r"check[- ]extension",
    "singular extension": r"singular",
    "IID / IIR": r"internal[- ]iterative|\biid\b|\biir\b",
    "MVV-LVA": r"mvv|lva\b",
    "SEE (static exchange)": r"(?-i:\bSEE\b)|static[- ]exchange",
    "killer moves": r"killer",
    "history heuristic": r"history[- ](heuristic|table|score|bonus|malus|gravity)|butterfly|capture[- ]history|continuation[- ]history",
    "countermove heuristic": r"counter[- ]?move",
    "magic bitboards": r"magic",
    "bitboards": r"bitboard",
    "0x88 board": r"0x88",
    "mailbox": r"mailbox",
    "piece-square tables (PST)": r"piece[- ]square|\bpst\b",
    "tapered eval": r"tapered|taper(ed)? eval|\bmg\b.*\beg\b|midgame.*endgame|middlegame.*endgame|game[- ]phase",
    "perft": r"perft|kiwipete",
    "UCI protocol": r"\buci\b",
    "FEN / EPD": r"\bfen\b|\bepd\b",
    "PGN / SAN": r"\bpgn\b|\bsan\b",
    "polyglot book": r"polyglot",
    "Elo / SPRT stats": r"\belo\b|\bsprt\b|wald|fisher",
    "x-ray attacks": r"x-?ray",
    "carry-rippler": r"carry[- ]rippler",
    "repetition detection": r"repetition|threefold",
    "time management": r"time[- ]management|time[- ]control|movestogo",
    "king safety / pawn shield": r"king[- ]safety|pawn[- ]shield|king[- ]zone|tropism",
    "pawn structure terms": r"passed[- ]pawn|isolated|doubled[- ]pawn|backward[- ]pawn",
    "mobility": r"mobility",
    "bishop pair": r"bishop[- ]pair",
    "zugzwang": r"zugzwang",
    # compression
    "LZ77 / LZ": r"\blz77\b|\blz\b|\blzss\b|sliding[- ]window|back-?reference",
    "Huffman": r"huffman",
    "CRC32": r"\bcrc",
    "RLE": r"\brle\b|run[- ]length",
    "delta / zigzag / varint": r"\bdelta[- ](encod|cod)|zig-?zag|varint",
    "hash chains": r"hash[- ]chain|hash[- ]head",
    # SAT
    "DPLL": r"\bdpll\b",
    "CDCL / clause learning": r"\bcdcl\b|clause[- ]learn|learn(ed|t) clause|conflict[- ]analysis|\b1-?uip\b|first[- ]uip",
    "unit propagation / BCP": r"unit[- ]propagat|\bbcp\b|propagat",
    "watched literals": r"watch",
    "VSIDS / activity": r"vsids|activity",
    "restarts (Luby)": r"\bluby\b|restart",
    "backjumping": r"backjump|non-chronological",
    "phase saving": r"phase[- ]sav",
    "Jeroslow-Wang": r"jeroslow",
    "DIMACS": r"dimacs",
    "pure literal": r"pure[- ]literal",
    # graphics / games
    "raycasting / DDA": r"ray[- ]?cast|\bdda\b|ray[- ]march",
    "fisheye correction": r"fish[- ]?eye",
    "z-buffer / depth buffer": r"z[- ]buffer|depth[- ]buffer",
    "BSP": r"\bbsp\b",
    "sprites / billboards": r"sprite|billboard",
    "fixed-point math": r"fixed[- ]point",
    "double buffering / framebuffer": r"double[- ]buffer|framebuffer|frame[- ]buffer|back[- ]buffer",
    "AABB collision": r"aabb|bounding[- ]box",
    "PRNG / LCG": r"\bprng\b|\blcg\b|xorshift|linear congruential|splitmix",
}
TECH_RE = {k: re.compile(v, re.I) for k, v in TECH.items()}
# protocol / format names: counted in the vocabulary, but a short label that only names
# them ("Print UCI info") is a what-comment, not a technique reference
PROTOCOL_ONLY = {"UCI protocol", "FEN / EPD", "PGN / SAN", "time management", "DIMACS"}
STRONG_WHY = re.compile(r"\bbecause\b|\bso that\b|\bto avoid\b|\botherwise\b|\bdeliberately\b|\bintentionally\b|\bon purpose\b|\bworkaround\b|\bin order to\b|\binstead of\b|\brather than\b", re.I)

# patterns over CODE (comments removed) that show a technique is implemented even when
# uncommented. Only for techniques with distinctive identifiers.
CODE_TECH = {
    "zobrist hashing": r"zobrist|ZOBRIST|zkey|hash_?key|HASH-KEY|HS-[A-Z]*KEY|piece_?keys?|side_?key",
    "transposition table": r"\btt\b|TT[-_]|transposition|TTEntry|tt_|-TT\b|TT-",
    "null-move pruning": r"null_?move|NULL-MOVE|nullmove|NullMove|make_null|makeNull",
    "late move reductions (LMR)": r"lmr|LMR|reduction|REDUCTION",
    "late move pruning (LMP)": r"lmp|LMP|late_move_prun",
    "futility pruning": r"futil|FUTIL",
    "reverse futility / static null": r"rfp|RFP|reverse_futility|static_null",
    "razoring": r"razor|RAZOR",
    "delta pruning": r"delta|DELTA",
    "mate distance pruning": r"mate_dist|MATE-DIST|mateDist",
    "MVV-LVA": r"mvv|MVV|lva|LVA",
    "SEE (static exchange)": r"\bsee\b|SEE[-_(]|see_|static_exchange|staticExchange|\bsee\(",
    "killer moves": r"killer|KILLER|Killer",
    "history heuristic": r"history|HISTORY|History",
    "countermove heuristic": r"counter_?move|COUNTER-?MOVE|counterMove|countermove",
    "quiescence search": r"quiesc|QUIESC|qsearch|QSEARCH|Quiesc",
    "aspiration window": r"aspir|ASPIR|ASPIRATION",
    "iterative deepening": r"iterative|ITERATIVE|for\s*\(?\s*\w*depth\w*\s*(=|in)\s*1|ID-LOOP|ITER-DEPTH",
    "PVS / principal variation": r"pvs|PVS|is_?pv|isPv|IS-PV|pv_node|PV-NODE|pvNode",
    "check extension": r"extension|EXTENSION|extend|EXTEND",
    "singular extension": r"singular|SINGULAR",
    "magic bitboards": r"magic|MAGIC|Magic",
    "0x88 board": r"0x88|& 136|AND 136|136\)|X88|x88",
    "piece-square tables (PST)": r"pst|PST|psqt|PSQT|piece_square|PIECE-SQUARE",
    "perft": r"perft|PERFT|Perft",
    "repetition detection": r"repetit|REPETIT|threefold|Repetit",
    "polyglot book": r"polyglot|POLYGLOT|Polyglot",
    "carry-rippler": r"&\s*\(?\w+\s*-\s*\w+\)?\s*&|subset",
    "tapered eval": r"phase|PHASE|taper|TAPER|\bmg\b|\beg\b|_mg|_eg|MG-|EG-",
    "x-ray attacks": r"xray|x_ray|XRAY|X-RAY",
    "CRC32": r"crc|CRC",
    "LZ77 / LZ": r"lz|LZ|match_?len|MATCH-LEN|window|WINDOW",
    "Huffman": r"huff|HUFF",
    "RLE": r"rle|RLE|run_?len|RUN-LEN",
    "hash chains": r"chain|CHAIN|hash_?head|HASH-HEAD",
    "watched literals": r"watch|WATCH",
    "VSIDS / activity": r"vsids|VSIDS|activity|ACTIVITY|WS-ACT\b",
    "restarts (Luby)": r"luby|LUBY|restart|RESTART",
    "backjumping": r"backjump|BACKJUMP|back-jump|BACK-JUMP",
    "CDCL / clause learning": r"learn|LEARN|conflict|CONFLICT",
    "phase saving": r"phase|PHASE",
    "Jeroslow-Wang": r"jeroslow|JEROSLOW|JW-|jw_",
    "unit propagation / BCP": r"propagat|PROPAGAT|unit|UNIT",
    "raycasting / DDA": r"ray|RAY|dda|DDA|side-dist|SIDE-DIST|delta-dist|DELTA-DIST",
    "fisheye correction": r"fish|FISH|perp|PERP|cos\(|COS",
    "z-buffer / depth buffer": r"zbuf|ZBUF|z-buf|Z-BUF|depth-buf|DEPTH-BUF|wall-dist|WALL-DIST",
    "sprites / billboards": r"sprite|SPRITE",
    "double buffering / framebuffer": r"framebuf|FRAMEBUF|frame-buf|FRAME-BUF|back-?buf|BACK-?BUF|SDL_RenderPresent|present|PRESENT",
    "PRNG / LCG": r"rand|RAND|seed|SEED|lcg|LCG|xorshift",
}
CODE_TECH_RE = {k: re.compile(v) for k, v in CODE_TECH.items()}

DOMAIN = r"castl|en[- ]passant|\bep\b|promot|stalemate|checkmate|insufficient material|50-move|fifty|draw"

WHY = re.compile(
    r"\bbecause\b|\bso that\b|\bso (we|it|the|that|no|a|only)\b|\bto avoid\b|\bavoid|\botherwise\b|\bnote\b|\bnb\b|\bsince\b|\bprevent|\bensure"
    r"|\bin order to\b|\binstead\b|\brather than\b|\bwould\b|\bcan't\b|\bcannot\b|\bwon't\b|\bwe (need|must|want|only|don't|do not|keep|use|skip|can)\b"
    r"|\bnot feasible\b|\bmatches \S+ (reader )?behaviou?r|\blenient\b|^fix:|\benables?\b|\ballows? (us|the|it|a|for)\b|\brequired (by|for|so)|\bworkaround|\bwhy\b|\bintent|\bhelps?\b|\bsafer\b|\bfor safety\b|\bguard(s)? against|\bfor (correctness|speed|performance|robustness|determinism)"
    r"|\bkeeps? (it|the|them)\b|\bto keep\b|\bto reduce\b|\bto prevent\b|\bto make sure\b|\bto allow\b|\bdon't\b|\bdo not\b|\bnever\b|\bimportant\b|\bcaveat|\bunlike\b|\bwhereas\b|\bthis way\b"
    r"|\bso\b(?! far| on\b)|\bwill be (caught|handled|checked|done|fixed)|\bdeliberately\b|\bintentionally\b|\bon purpose\b|\bmay\b|\bsilence|\bwarnings?\b|\bfound by\b|\bwell-known\b|\btaken from\b|\bper (the )?(spec|reference)\b|\bmatches?\b.*\b(spec|reference|c version|python|stockfish|gnucobol|ibm)\b|\b(gnucobol|cobc)\b.*\b(bug|quirk|limit|requires|does not|doesn't|can't)",
    re.I,
)
STRONG_INVAR = re.compile(
    r"\bshould (not|never) happen\b|\bmatches (the )?c struct\b|\bexactly the\b|\((ms|centipawns|cp|bytes|bits|seconds|plies)\)|\b\d+ (bytes?|bits?|ms|plies|entries|centipawns)\b|^\[[\w ,]+\]$|\[\d\]\s*=|\bmust\b|\balways\b|\bnever\b|\bassum|\binvariant|\balready\b|\bmeans\b|\b\d+ fields\b|\[\w+\]\s*\[\w+\]|(\b[a-h][1-8]\s*=\s*\d+\b.*){2,}",
    re.I,
)
INVAR = re.compile(
    r"\bmust\b|\balways\b|\bassum|\binvariant|\balready\b|\bmeans\b|\b\d+ fields\b|\[\w+\]\s*\[\w+\]|(\b[a-h][1-8]\s*=\s*\d+\b.*){2,}|\bguarantee|\bprecondition|\bpostcondition|\bexpects?\b|\bnon-?negative|\b0-based|\b1-based|\bzero-based|\bone-based"
    r"|\bin (ms|milliseconds|centipawns|cp|bytes|bits|seconds|plies|nodes)\b|\b(ms|centipawns|milliseconds|cp)\)|\bcentipawn|\bunits?\b|\bindexed\b|\bindex(ed)? (by|from)\b"
    r"|\b\d+\s*\.\.\s*\d+\b|\[\s*\d+\s*-\s*\d+\s*\]|\b0 = |\b-1 = |=\s*(none|empty|unlimited|unknown|infinite)\b|\bbits? \d|\bbit \d|\bmax(imum)? \d|\bat most\b|\bat least\b|\bfrom (white|black|side)[- 'a-z]*(pov|perspective|point of view)|\bperspective\b|\bpov\b|\b(lsb|msb)\b|\bbig-?endian|\blittle-?endian|\bsigned\b|\bunsigned\b|\boverflow",
    re.I,
)
TODO = re.compile(
    r"\btodo\b|\bfixme\b|\bxxx\b|\bhack\b|\bnot (yet )?(implemented|supported|handled)|\bunsupported\b|\bfor now\b|\blimitation|\bplaceholder\b|\bstub\b"
    r"|\bapproximat|\bvery rough|\b\(rough\)|\bsimplified\b|\bnaive\b|\bignores?\b|\bnot exact|\bcrude\b|\bbaseline engine\b|\bknown issue|\bkludge",
    re.I,
)
BOILER = re.compile(
    r"frozen_string_literal|\bnoqa\b|\bpylint:|\btype: ?ignore|^#!|-\*- coding|\bcopyright\b|\blicen[cs]e\b|\bspdx\b|\bmit license|\bclippy::|\brustfmt|\beslint|\bnolint\b|\bauthor:\b|generated by|\bpragma\b",
    re.I | re.M,
)
CODE_LIKE = {
    "c": re.compile(r"(^(?!.*\b[a-z]+ [a-z]+ [a-z]+\b).*[=(].*;\s*$)|(^\s*(if|for|while|return)\s*\(.*\)\s*[{;]?\s*$)|(^\s*[a-z_]\w*\s*(\[[^\]]*\])?\s*[+\-*/|&^]?=\s*[^=].*;\s*$)|(^\s*[a-z_]\w*\(.*\);\s*$)|(^\s*[{}]\s*$)", re.M),
    "python": re.compile(r"(^\s*(if|for|while|return|def|import|from)\b.*[:)]\s*$)|(^\s*[a-z_]\w*\s*=\s*[^=].*$)|(^\s*print\()|(^\s*[a-z_][\w.]*\(.*\)\s*$)", re.M),
    "ruby": re.compile(r"(^\s*(if|unless|return|def|puts|end)\b)|(^\s*@?[a-z_]\w*\s*=\s*[^=])", re.M),
    "cobol": re.compile(r"^\s*(MOVE\s+\S+\s+TO\b|PERFORM\s+[A-Z0-9-]+(\s+(UNTIL|VARYING|THRU|TIMES)\b|\s*$)|COMPUTE\s+[A-Z0-9-]+\s*=|IF\s+[A-Z0-9-]+\s*(=|>|<|NOT)|DISPLAY\s+[\"'A-Z]|ADD\s+\S+\s+TO\s+[A-Z]|CALL\s+[\"']|END-(IF|PERFORM)\b|\d\d\s+[A-Z0-9-]+\s+PIC\b)", re.M),
}
CODE_LIKE["cpp"] = CODE_LIKE["java"] = CODE_LIKE["rust"] = CODE_LIKE["c"]
DOC_TALK = re.compile(
    r"\breturns?\b|\bcomputes?\b|\bcalculates?\b|\bgenerates?\b|\bchecks? (if|whether)\b|\bwhether\b|\bparses?\b|\bconverts?\b|\bgiven\b|\btakes?\b|\bupdates?\b"
    r"|\binput:|\boutput:|\bon entry\b|\bon exit\b|\b(in|out)puts?\b|\bsets? (ws|the)\b|\bresult in\b|\bused (by|with|to|for|as|in|when)\b|\bcalled (by|from|when)\b|@param|@return|\bargs?:|\breturns:|\bthis (module|file|paragraph|function|method|struct|class|copybook)\b|\bmodule\b|\bowned by\b|\bdispatch|\bimplements?\b|\bprovides?\b|\bholds?\b|\bstores?\b|\bentry point\b",
    re.I,
)
BANNER_LINE = re.compile(r"^[\s*/#=\-_~+.:<>!─━═┄·•]*$")
FRAME_CHARS = re.compile(r"([=\-*#_~─━═]{3,})")


def body_lines(txt):
    out = []
    for l in txt.split("\n"):
        s = l.strip()
        s = re.sub(r'^(///?|//!|/\*+!?|\*/|\*>|\*+|#+|"""|\'\'\'|/)', "", s)
        s = re.sub(r"(\*+/|\"\"\"|''')\s*$", "", s)
        out.append(s.strip())
    return out


def classify(row, txt):
    lang = row["lang"]
    lines = body_lines(txt)
    content = [l for l in lines if l and not BANNER_LINE.match(l)]
    # strip decorative runs inside content lines ("---- Pawn moves ----")
    clean = [FRAME_CHARS.sub(" ", l).strip(" -=*#") for l in content]
    clean = [c for c in clean if c]
    joined = " ".join(clean)
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]*", joined)
    nwords = len(words)
    has_frame = bool(re.search(r"[=\-*#_~─━═]{5,}", txt)) or bool(FRAME_CHARS.search(" ".join(lines)))
    techs = [k for k, r in TECH_RE.items() if r.search(joined)]
    flags = dict(
        why=bool(WHY.search(joined)),
        invariant=bool(INVAR.search(joined)),
        todo=bool(TODO.search(joined)),
        technique=bool(techs),
        domain=bool(re.search(DOMAIN, joined, re.I)),
        framed=has_frame,
    )
    pos = row["position"]
    doc = row["doc_form"] == "1"
    # ---- primary class, priority order
    if not clean:
        primary = "banner/divider"
    elif re.match(r"^(anonymous )?namespace\b|^end (of )?(namespace|class|module)\b", joined, re.I):
        primary = "what/restates"
    elif BOILER.search(txt) and nwords <= 12:
        primary = "licence/boilerplate"
    elif CODE_LIKE[lang].search("\n".join(clean)) and not (lang == "cobol" and nwords > 12 and not re.search(r"\b(MOVE|PERFORM|COMPUTE)\b", joined)):
        primary = "commented-out code"
    elif re.search(r"\b(todo|fixme|xxx)\b", joined, re.I):
        primary = "TODO/limitation"
    elif has_frame and len(clean) <= 1 and not doc and (nwords <= 8 or (nwords <= 14 and FRAME_CHARS.search(content[0] if content else ""))):
        primary = "banner/divider"
    elif re.match(r"^(caller|callers|inputs?|outputs?|on entry|on exit|returns?|form|format|syntax|usage|args?|params?)\s*:", joined, re.I):
        primary = "doc/API"
    elif pos in ("header", "preceding_def") and not doc and STRONG_WHY.search(" ".join(words[:30])):
        primary = "why/rationale"
    elif re.search(r"\b[A-Z][A-Z0-9]*(-[A-Z0-9]+)+\s+(inputs?|outputs?|arguments|parameters)\b", joined):
        primary = "doc/API"
    elif (doc or pos in ("preceding_def", "header")) and (nwords >= 4 or doc or (pos == "header" and nwords >= 2)) and not (flags["why"] and not doc and nwords < 12 and pos == "preceding_def" and not DOC_TALK.search(joined)):
        # function / module documentation (incl. banner-framed paragraph docs)
        if has_frame and nwords <= 6 and len(clean) <= 1 and not doc:
            primary = "banner/divider"
        else:
            primary = "doc/API"
    elif flags["todo"]:
        primary = "TODO/limitation"
    elif pos == "other" and nwords >= 8 and DOC_TALK.search(joined):
        # documentation of a data area / declaration group
        primary = "doc/API"
    elif nwords >= 20 and pos not in ("inside_body", "trailing") and re.search(r"\b[A-Z]{2,}(-[A-Z0-9]+)+\b|\b[a-z]+_[a-z_]+\b", joined):
        primary = "doc/API"
    elif flags["why"]:
        primary = "why/rationale"
    elif STRONG_INVAR.search(joined):
        primary = "invariant/assumption/units"
    elif techs and nwords <= 10 and not set(techs) <= PROTOCOL_ONLY:
        primary = "algorithm/domain reference"
    elif flags["invariant"]:
        primary = "invariant/assumption/units"
    elif techs and not set(techs) <= PROTOCOL_ONLY:
        primary = "algorithm/domain reference"
    elif pos == "preceding_def" and nwords >= 3:
        primary = "doc/API"
    elif nwords <= 12 or pos in ("inside_body", "trailing", "other"):
        primary = "what/restates"
    else:
        primary = "other"
    return primary, flags, techs, nwords


def main():
    texts = {j["block_id"]: j["text"] for j in map(json.loads, open(TEXT_CACHE))}
    rows = list(csv.DictReader(open(os.path.join(OUT, "blocks.csv"))))
    out = []
    for r in rows:
        p, f, t, nw = classify(r, texts[int(r["block_id"])])
        r2 = dict(block_id=r["block_id"], primary=p, content_words=nw, techniques=";".join(t), **{k: int(v) for k, v in f.items()})
        out.append(r2)
    with open(os.path.join(OUT, "labels.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    import collections
    print(collections.Counter(o["primary"] for o in out).most_common())


if __name__ == "__main__":
    main()
