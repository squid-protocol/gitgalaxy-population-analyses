#!/usr/bin/env python3
"""Run one agent-habits confirmation run (PREREGISTRATION.md section 4, deviations D1-D3).

    python run.py RUN_ID            # one run from cells.plan()
    python run.py --next            # the next not-yet-started run in the fixed shuffled order
    python run.py --order           # print the run order
    python run.py --smoke AGENT     # a 1-minute toy task in a scratch dir (not a study run)

Every agent session runs in a fresh container of image agent-habits-run:1 with the project at /work and the
checker at /check (read-only). The harness, not the agent, decides "done": after each session it runs
`/check/check TASK`; on FAIL it resumes the same session with the checker's output (at most MAX_NUDGES times)
while active time is under CAP_MIN. A usage-limit stop is resumed with "continue" after the reset (D3) and its
waiting time is not active time. A run directory that exists is never re-run.

Credentials: Claude Code reads CLAUDE_CODE_OAUTH_TOKEN from secrets/claude_token (made with `claude setup-token`);
Codex uses ~/.codex/auth.json, copied into the run's codex home and copied back after each session (token refresh).
"""

import argparse
import csv
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cells

KIT = Path(__file__).resolve().parent
CONFIRM = KIT.parent
RUNS = CONFIRM / "runs"
LOG = CONFIRM / "runs.csv"
SECRET = CONFIRM / "secrets" / "claude_token"
HOST_CODEX_AUTH = Path.home() / ".codex" / "auth.json"
IMAGE = "agent-habits-run:2"
ORDER_SEED = 20261101
LIMIT_RE = re.compile(r"usage limit|rate limit|limit reached|hit your limit|try again (?:at|in)|quota|"
                      r"too many requests|\b429\b", re.I)
LIMIT_POLL_S = 15 * 60
LIMIT_MAX_WAIT_S = 8 * 24 * 3600
FIELDS = ["run_id", "task", "lang", "agent", "rep", "cli", "model", "setting", "image", "started", "ended",
          "active_s", "sessions", "nudges", "limit_interruptions", "limit_wait_s", "cap_hit", "final_check",
          "session_id", "note"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def order() -> list[dict]:
    runs = cells.plan()
    random.Random(ORDER_SEED).shuffle(runs)
    # r1 is the run that happens first (D1: the primary tests use each agent's first run in a repeat cell).
    seen: dict[tuple, int] = {}
    for r in runs:
        k = (r["task"], r["lang"], r["agent"])
        seen[k] = seen.get(k, 0) + 1
        r["rep"] = seen[k]
        r["run_id"] = f"{r['task']}-{r['lang']}-{r['agent']}-r{r['rep']}"
    return runs


def render(task: str, lang: str) -> str:
    name, rule = cells.LANGS[lang]
    return (KIT / "prompts" / f"{task}.md").read_text().replace("{LANG_NAME}", name).replace("{LANG_RULE}", rule)


def image_id() -> str:
    return subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], capture_output=True,
                          text=True).stdout.strip()[:19]


def docker(rd: Path, agent: str, argv: list[str], name: str, timeout: float | None,
           check_dir: str = "check_public") -> tuple[int | None, str]:
    # D7: agent sessions see the practice checker (check_public: same code, practice puzzles and formulas);
    # only the harness's final check mounts the held-out set (check).
    cmd = ["docker", "run", "--rm", "--name", name, "-v", f"{rd / 'repo'}:/work",
           "-v", f"{KIT / check_dir}:/check:ro", "--cpus", "3", "--memory", "6g"]
    if agent == "claude":
        cmd += ["-v", f"{rd / 'agent-home'}:/home/agent/.claude", "-e", "CLAUDE_CODE_OAUTH_TOKEN"]
    else:
        cmd += ["-v", f"{rd / 'agent-home'}:/home/agent/.codex"]
    cmd += [IMAGE] + argv
    env = dict(os.environ)
    if agent == "claude":
        env["CLAUDE_CODE_OAUTH_TOKEN"] = SECRET.read_text().strip()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, p.stdout + "\n" + p.stderr
    except subprocess.TimeoutExpired as e:
        subprocess.run(["docker", "kill", name], capture_output=True)
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return None, out


def agent_argv(agent: str, message: str, session: str | None) -> list[str]:
    if agent == "claude":
        a = ["claude", "-p", message, "--model", cells.AGENTS["claude"]["model"], "--dangerously-skip-permissions",
             "--output-format", "json"]
        return a + (["--resume", session] if session else [])
    base = ["--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox", "-m", cells.AGENTS["codex"]["model"],
            "-c", "model_reasoning_effort=medium", "--json"]
    if session:
        return ["codex", "exec", "resume", session] + base + [message]
    return ["codex", "exec"] + base + [message]


def find_session(agent: str, out: str, rd: Path) -> str | None:
    keys = ("session_id",) if agent == "claude" else ("thread_id", "session_id", "conversation_id")
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        stack = [obj]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                for k in keys:
                    if isinstance(o.get(k), str) and len(o[k]) >= 8:
                        return o[k]
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return None


def codex_auth_in(rd: Path) -> None:
    shutil.copy2(HOST_CODEX_AUTH, rd / "agent-home" / "auth.json")


def codex_auth_out(rd: Path) -> None:
    src = rd / "agent-home" / "auth.json"
    if src.exists() and src.read_bytes() != HOST_CODEX_AUTH.read_bytes():
        shutil.copy2(src, HOST_CODEX_AUTH)


def check(rd: Path, task: str, agent: str, name: str) -> tuple[bool, str]:
    rc, out = docker(rd, agent, ["sh", "-c", f"cd /work && /check/check {task}"], name + "-check", 1500,
                     check_dir="check")
    return rc == 0 and out.lstrip().startswith("PASS"), out.strip()


def append_log(row: dict) -> None:
    new = not LOG.exists()
    with LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def run(r: dict, smoke_prompt: str | None = None) -> dict:
    rd = (RUNS if smoke_prompt is None else CONFIRM / "smoke") / r["run_id"]
    if rd.exists():
        raise SystemExit(f"{rd} exists: a run is never re-run (D3)")
    (rd / "repo").mkdir(parents=True)
    (rd / "agent-home").mkdir()
    (rd / "sessions").mkdir()
    os.chmod(rd / "repo", 0o777)
    os.chmod(rd / "agent-home", 0o777)
    subprocess.run(["git", "init", "-q", "-b", "main", str(rd / "repo")], check=True)
    prompt = smoke_prompt or render(r["task"], r["lang"])
    (rd / "prompt.txt").write_text(prompt)
    agent, task = r["agent"], r["task"]
    cap = (2 if smoke_prompt else cells.CAP_MIN) * 60
    row = {k: "" for k in FIELDS}
    row.update({"run_id": r["run_id"], "task": task, "lang": r["lang"], "agent": agent, "rep": r["rep"],
                "cli": cells.AGENTS[agent]["cli"], "model": cells.AGENTS[agent]["model"],
                "setting": cells.AGENTS[agent]["setting"], "image": image_id(), "started": now()})
    active, sessions, nudges, limits, waited = 0.0, 0, 0, 0, 0
    session, message, passed, last_check, cap_hit = None, prompt, False, "", False
    in_limit, limit_started = False, 0.0
    while True:
        left = cap - active
        if left <= 60:
            cap_hit = True
            break
        if agent == "codex":
            codex_auth_in(rd)
        t0 = time.time()
        rc, out = docker(rd, agent, agent_argv(agent, message, session), f"ah-{r['run_id']}-{sessions}", left)
        active += time.time() - t0
        if agent == "codex":
            codex_auth_out(rd)
        sessions += 1
        (rd / "sessions" / f"{sessions:02d}.log").write_text(out)
        session = session or find_session(agent, out, rd)
        if rc is None:
            cap_hit = True
            break
        if LIMIT_RE.search(out[-4000:]) and rc != 0:
            # D3: wait for the reset, then resume the same session with "continue" through the normal path, so
            # whatever the agent does next is timed and checked like any other session.
            if not in_limit:
                limits += 1
                limit_started = time.time()
            in_limit = True
            if time.time() - limit_started > LIMIT_MAX_WAIT_S:
                row["note"] = "gave up waiting for a usage-limit reset"
                break
            time.sleep(LIMIT_POLL_S)
            waited += LIMIT_POLL_S
            message = "continue"
            continue
        in_limit = False
        passed, last_check = check(rd, task if not smoke_prompt else "sat", agent, f"ah-{r['run_id']}")
        if passed or nudges >= cells.MAX_NUDGES or smoke_prompt:
            break
        nudges += 1
        head = "\n".join(last_check.splitlines()[:40])
        message = f"The check failed:\n{head}\n\nContinue until `/check/check {task}` prints PASS."
    row.update({"ended": now(), "active_s": int(active), "sessions": sessions, "nudges": nudges,
                "limit_interruptions": limits, "limit_wait_s": waited, "cap_hit": cap_hit,
                "final_check": "PASS" if passed else "FAIL", "session_id": session or ""})
    (rd / "final_check.txt").write_text(last_check + "\n")
    (rd / "run.json").write_text(json.dumps(row, indent=1) + "\n")
    if smoke_prompt is None:
        append_log(row)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--order", action="store_true")
    ap.add_argument("--smoke", choices=sorted(cells.AGENTS))
    ap.add_argument("--agent", choices=sorted(cells.AGENTS),
                    help="with --next: the next pending run of this agent only (D6); the order itself is unchanged")
    a = ap.parse_args()
    if a.order:
        for i, r in enumerate(order(), 1):
            print(f"{i:2} {r['run_id']}{'  (done)' if (RUNS / r['run_id']).exists() else ''}")
        return
    if a.smoke:
        msg = ("Create an executable file ./solver (a shell script is fine) that prints `s SATISFIABLE` and exits 10, "
               "and an executable ./build.sh that exits 0. Then stop.")
        r = {"run_id": f"smoke-{a.smoke}-{int(time.time())}", "task": "smoke", "lang": "-", "agent": a.smoke, "rep": 0}
        print(json.dumps(run(r, smoke_prompt=msg), indent=1))
        return
    if a.next:
        todo = [r for r in order() if not (RUNS / r["run_id"]).exists() and (not a.agent or r["agent"] == a.agent)]
        if not todo:
            print("all runs started" + (f" for {a.agent}" if a.agent else ""))
            return
        r = todo[0]
    else:
        r = next((x for x in cells.plan() if x["run_id"] == a.run_id), None)
        if r is None:
            raise SystemExit(f"unknown run {a.run_id}")
    print(json.dumps(run(r), indent=1))


if __name__ == "__main__":
    sys.exit(main())
