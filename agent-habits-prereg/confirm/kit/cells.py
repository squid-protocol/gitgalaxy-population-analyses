"""The agent-habits confirmation plan (PREREGISTRATION.md section 4 as amended by D1-D2): 10 cells (2 tasks x 5
languages), one run per agent per cell, plus a second run per agent in the two repeat cells: 24 runs."""

TASKS = ("chess", "sat")
LANGS = {
    "c": ("C", "The program must be written in C (C17), built with gcc, using only the C standard library and POSIX."),
    "java": ("Java", "The program must be written in Java 17, built with javac, using only the Java standard library."),
    "python": ("Python", "The program must be written in Python 3, using only the Python standard library."),
    "rust": ("Rust", "The program must be written in Rust (stable), built with cargo, with no external crates."),
    "cobol": ("COBOL", "The program must be written in COBOL, built with GnuCOBOL 3.1 (`cobc`)."),
}
REPEAT_CELLS = {("chess", "rust"), ("sat", "python")}
AGENTS = {
    "claude": {"cli": "Claude Code 2.1.316", "model": "claude-sonnet-5-5", "setting": "default effort"},
    "codex": {"cli": "Codex CLI 0.166.0", "model": "gpt-6-luna", "setting": "model_reasoning_effort=medium"},
}
# D9 (exploratory arm, owner 2026-11-01): Claude Code on Haiku 5.5, same cells and repeats (12 runs). Kept out of
# AGENTS so plan() -- and with it the frozen D5 order of the registered runs -- is unchanged; it gets its own order.
EXTRA_AGENTS = {
    "haiku": {"cli": "Claude Code 2.1.316", "model": "claude-haiku-5-5", "setting": "default effort", "kind": "claude"},
}
ALL_AGENTS = {**AGENTS, **EXTRA_AGENTS}
CAP_MIN = 60          # active minutes per run, all sessions together
MAX_NUDGES = 2        # follow-ups after a failed check, each carrying the check's output


def plan() -> list[dict]:
    runs = []
    for task in TASKS:
        for lang in LANGS:
            reps = 2 if (task, lang) in REPEAT_CELLS else 1
            for rep in range(1, reps + 1):
                for agent in AGENTS:
                    runs.append({"run_id": f"{task}-{lang}-{agent}-r{rep}", "task": task, "lang": lang,
                                 "agent": agent, "rep": rep})
    return runs


def plan_extra(agent: str) -> list[dict]:
    """D9: the same cells and repeats for one exploratory agent."""
    runs = []
    for task in TASKS:
        for lang in LANGS:
            reps = 2 if (task, lang) in REPEAT_CELLS else 1
            for rep in range(1, reps + 1):
                runs.append({"run_id": f"{task}-{lang}-{agent}-r{rep}", "task": task, "lang": lang,
                             "agent": agent, "rep": rep})
    return runs


if __name__ == "__main__":
    p = plan()
    for r in p:
        print(r["run_id"])
    print(len(p), "runs")
