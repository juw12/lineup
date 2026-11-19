"""Lineup - a self-tuning team of role agents for OpenCode.

    python lineup.py install      copy the six role agents into OpenCode
    python lineup.py tune         score every model on every role, keep the best one per role
    python lineup.py tune --hard     also ask the harder third question of every role
    python lineup.py tune --resume   continue a run that a usage limit stopped
    python lineup.py status       show the current lineup
    python lineup.py report       write and open the score page
    python lineup.py uninstall    remove the agents again

Standard library only. Runs on Windows, macOS and Linux; the full tuning run is measured on Windows.
"""
import argparse
import concurrent.futures
import datetime
import functools
import html
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

VERSION = "0.2.0"
# In the packaged lineup.exe the agents, tasks and fixtures are unpacked next to the program at start.
HERE = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent)
PROGRAM = "lineup" if getattr(sys, "frozen", False) else "python lineup.py"  # how the user started it
AGENT_SOURCE = HERE / "agents"
FIXTURES = HERE / "fixtures"
TASKS_FILE = HERE / "tasks.json"
PREFIX = "lineup-"
MODEL_LINE = re.compile(r"^model:.*\n", re.MULTILINE)
ANSI = re.compile(r"\x1b\[[0-9;]*m")
FIXTURE_PATH = re.compile(r"\{fixtures\}(?:[\\/]([\w\-]+(?:[\\/.][\w\-]+)*))?")
LOGGED_ERROR = re.compile(r'error\.error="([^"]+)"|level=ERROR.*?message="([^"]+)"')
LIMIT = re.compile(r"usage limit|rate limit|quota|too many requests|\b429\b", re.IGNORECASE)
ROLL_CALL = "Reply with the single word: ready"
ROLL_CALL_SECONDS = 60
RESUME_DAYS = 7


# ------------------------------------------------------------------ places

def home_folder():
    """Lineup's own data: results, the chosen lineup, backups, the report."""
    return Path(os.environ.get("LINEUP_HOME") or Path.home() / ".lineup")


def opencode_agents_folder():
    config = os.environ.get("OPENCODE_CONFIG_DIR") or Path.home() / ".config" / "opencode"
    return Path(config) / "agents"


def find_opencode(explicit=None):
    executable = explicit or os.environ.get("LINEUP_OPENCODE") or shutil.which("opencode")
    if not executable:
        sys.exit("OpenCode was not found. Install it (https://opencode.ai) or pass --opencode <path>.")
    return str(executable)


def roles():
    return sorted(path.stem[len(PREFIX):] for path in AGENT_SOURCE.glob(PREFIX + "*.md"))


# ------------------------------------------------------------------ talking to OpenCode

def final_answer(json_lines):
    """The text OpenCode wrote after its last tool call (`opencode run --format json` output)."""
    answer = []
    for line in json_lines.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        part = event.get("part") or {}
        if event.get("type") == "tool_use" or part.get("type") == "tool":
            answer = []
        elif part.get("type") == "text" and part.get("text"):
            answer.append(part["text"])
    return "\n".join(answer).strip()


def version_flags(version_text):
    """OpenCode 2 answers through a background service; --standalone gives each question its own server."""
    match = re.search(r"(\d+)\.\d+", version_text)
    return ["--standalone"] if match and int(match.group(1)) >= 2 else []


@functools.lru_cache(maxsize=None)
def run_flags(executable):
    try:
        version = subprocess.run([executable, "--version"], capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ()
    return tuple(version_flags(version.stdout.decode("utf-8", "replace")))


def ask(executable, agent, model, prompt, timeout):
    """One question to one agent. Returns (answer, seconds, error)."""
    command = [executable, "run", *run_flags(executable), "--print-logs", "--agent", agent, "--format", "json"]
    if model:
        command += ["--model", model]
    command.append(prompt)
    started = time.time()
    process = subprocess.Popen(
        command, cwd=FIXTURES, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=os.name != "nt",  # its own process group, so a timeout can stop the helpers too
    )
    timed_out = False
    try:
        output, errors = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":  # OpenCode starts helper processes; stop the whole tree
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()
        output, errors = process.communicate()
    seconds = time.time() - started
    output = output.decode("utf-8", "replace")
    answer = "" if timed_out else final_answer(output)
    if answer:
        return answer, seconds, ""
    reason = failure_reason(output, errors.decode("utf-8", "replace"))
    if timed_out:  # OpenCode 1 retries a refused request in silence, so the reason is only in its log
        reason = f"no answer in {timeout} s" + ("" if reason == "empty answer" else f": {reason}")
    return "", seconds, reason[:200]


def failure_reason(json_lines, log_text):
    """Why there is no answer: OpenCode's error event, then the last error in its log, then its last plain line."""
    for line in json_lines.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "error":
            error = event.get("error") or {}
            return str(
                error.get("message") or (error.get("data") or {}).get("message")
                or error.get("name") or error.get("type") or "error"
            )
    log_text = ANSI.sub("", log_text)
    logged = LOGGED_ERROR.findall(log_text)
    if logged:
        return logged[-1][0] or logged[-1][1]
    plain = [line.strip() for line in log_text.splitlines() if line.strip() and not line.startswith("timestamp=")]
    return plain[-1].lstrip("! ") if plain else "empty answer"


def list_models(executable):
    output = subprocess.run(
        [executable, "models"], capture_output=True, stdin=subprocess.DEVNULL, timeout=120
    ).stdout.decode("utf-8", "replace")
    return [line.strip() for line in output.splitlines() if re.fullmatch(r"\S+/\S+", line.strip())]


# ------------------------------------------------------------------ scoring

def check_passes(check, answer):
    kind, value = check["type"], check["value"]
    if kind == "regex":
        return re.search(value, answer, re.IGNORECASE | re.MULTILINE | re.DOTALL) is not None
    if kind == "absent":
        return re.search(value, answer, re.IGNORECASE | re.MULTILINE | re.DOTALL) is None
    if kind == "bullets":
        return sum(line.lstrip().startswith("- ") for line in answer.splitlines()) == value
    if kind == "max_words":
        return 0 < len(answer.split()) <= value
    raise ValueError(f"unknown check type: {kind}")


def score_answer(task, answer):
    """0 to 10: the share of the task's checks that the answer passes."""
    if not answer:
        return 0.0
    passed = sum(check_passes(check, answer) for check in task["checks"])
    return round(10 * passed / len(task["checks"]), 2)


def fixture_path(match):
    """{fixtures}/files/a.csv in a prompt -> that path on this machine, with this system's separators."""
    inside = match.group(1)
    return str(FIXTURES.joinpath(*re.split(r"[\\/]", inside)) if inside else FIXTURES)


def load_tasks(hard=False):
    """role -> its tasks. A task marked "level": "hard" is only asked with tune --hard."""
    tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    for role, role_tasks in tasks.items():
        tasks[role] = [task for task in role_tasks if hard or task.get("level") != "hard"]
        for task in tasks[role]:
            task["prompt"] = FIXTURE_PATH.sub(fixture_path, task["prompt"])
    return tasks


def summarise(rows):
    """rows of one role and model -> its score, speed and error count."""
    return {
        "score": round(statistics.mean(row["score"] for row in rows), 2),
        "seconds": round(statistics.median(row["seconds"] for row in rows), 1),
        "errors": sum(1 for row in rows if row["error"]),
        "runs": len(rows),
    }


def pick(candidates, current_model):
    """Best score wins, then the faster one. The current model stays on a tie in score."""
    best_model = max(candidates, key=lambda model: (candidates[model]["score"], -candidates[model]["seconds"]))
    if candidates[best_model]["score"] == 0:  # nothing passed: no reason to change
        return current_model
    if current_model in candidates and candidates[current_model]["score"] >= candidates[best_model]["score"]:
        return current_model
    return best_model


def earlier_answers(results_file):
    """Answered questions of the last days: (role, model, task, run) -> row. Used by tune --resume."""
    if not results_file.exists():
        return {}
    oldest = (datetime.datetime.now() - datetime.timedelta(days=RESUME_DAYS)).isoformat(timespec="seconds")
    found = {}
    for line in results_file.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "run" in row and not row["error"] and row["tuned_at"] >= oldest:
            found[(row["role"], row["model"], row["task"], row["run"])] = row
    return found


# ------------------------------------------------------------------ agent files

def read_model(agent_file):
    match = re.search(r"^model:\s*(\S+)", agent_file.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def write_model(agent_file, model):
    text = MODEL_LINE.sub("", agent_file.read_text(encoding="utf-8"))
    agent_file.write_text(text.replace("---\n", f"---\nmodel: {model}\n", 1), encoding="utf-8")


def installed_files():
    return sorted(opencode_agents_folder().glob(PREFIX + "*.md"))


def require_install():
    files = {path.stem[len(PREFIX):]: path for path in installed_files()}
    missing = [role for role in roles() if role not in files]
    if missing:
        sys.exit(f"Agents are not installed yet. Run: {PROGRAM} install")
    return files


# ------------------------------------------------------------------ commands

def install(arguments):
    target = opencode_agents_folder()
    target.mkdir(parents=True, exist_ok=True)
    for source in sorted(AGENT_SOURCE.glob(PREFIX + "*.md")):
        destination = target / source.name
        kept_model = read_model(destination) if destination.exists() else None
        shutil.copyfile(source, destination)
        if kept_model:  # an update keeps the model that tuning chose
            write_model(destination, kept_model)
        print(f"installed {destination.stem}" + (f"  (model kept: {kept_model})" if kept_model else ""))
    print(f"\n{len(roles())} agents are in {target}")
    print("Restart OpenCode, then pick an agent (Tab in the terminal, the agent menu in the desktop app).")
    print(f"Next: {PROGRAM} tune")


def uninstall(arguments):
    files = installed_files()
    for path in files:
        path.unlink()
        print(f"removed {path.stem}")
    print(f"{len(files)} agents removed. Your results stay in {home_folder()}.")


def tune(arguments):
    executable = find_opencode(arguments.opencode)
    agent_files = require_install()
    tasks = load_tasks(arguments.hard)
    models = arguments.models.split(",") if arguments.models else list_models(executable)
    if not models:
        sys.exit("OpenCode listed no models. Pass --models provider/model,provider/model")
    if len(models) > arguments.max_models and not arguments.models:
        sys.exit(f"OpenCode lists {len(models)} models. Choose some with --models a,b,c (or raise --max-models).")
    tuned_at = datetime.datetime.now().isoformat(timespec="seconds")
    store = home_folder()
    store.mkdir(parents=True, exist_ok=True)

    # Roll call: one short question per model, so a retired or silent model costs one question, not all of them.
    print(f"Roll call for {len(models)} models.")
    wait = min(arguments.timeout, ROLL_CALL_SECONDS)
    with concurrent.futures.ThreadPoolExecutor(arguments.parallel) as pool:
        replies = list(pool.map(lambda model: ask(executable, PREFIX + roles()[0], model, ROLL_CALL, wait), models))
    left_out = {model: reply[2] for model, reply in zip(models, replies) if not reply[0]}
    for model, reason in left_out.items():
        print(f"  left out: {model}  ({reason})")
    models = [model for model in models if model not in left_out]
    if not models:
        sys.exit("No model answered the roll call, so nothing was measured and nothing was changed.")

    earlier = earlier_answers(store / "results.jsonl") if arguments.resume else {}
    jobs = [
        (role, model, task, run_number)
        for role in roles()
        for model in models
        for task in tasks[role]
        for run_number in range(1, arguments.runs + 1)
    ]
    print(f"Tuning {len(roles())} roles on {len(models)} models: {len(jobs)} questions, {arguments.parallel} at a time.")
    stopped = []  # the provider's message once it refuses more questions

    def run(job):
        role, model, task, run_number = job
        if (role, model, task["id"], run_number) in earlier:
            return dict(earlier[(role, model, task["id"], run_number)], reused=True)
        if stopped:
            return None
        answer, seconds, error = ask(executable, PREFIX + role, model, task["prompt"], arguments.timeout)
        if LIMIT.search(error):  # a usage limit says nothing about the model, so it is not scored
            stopped.append(error)
            return None
        return {
            "tuned_at": tuned_at, "role": role, "model": model, "task": task["id"], "run": run_number,
            "score": score_answer(task, answer), "seconds": round(seconds, 1), "error": error, "answer": answer[:600],
        }

    rows = []
    with concurrent.futures.ThreadPoolExecutor(arguments.parallel) as pool, \
            (store / "results.jsonl").open("a", encoding="utf-8") as results:
        for number, row in enumerate(pool.map(run, jobs), 1):
            if row is None:
                continue
            rows.append(row)
            if not row.get("reused"):  # saved one by one, so a stopped run keeps what it measured
                results.write(json.dumps(row, ensure_ascii=False) + "\n")
                results.flush()
            note = "  (from the earlier run)" if row.get("reused") else f"  ({row['error']})" if row["error"] else ""
            print(f"[{number}/{len(jobs)}] {row['role']:<9} {row['model']:<40} {row['score']:>5}  {row['seconds']:>6} s{note}")

    table = {role: {} for role in roles()}  # only cells with every question answered or failed
    for role in roles():
        for model in models:
            cell = [row for row in rows if row["role"] == role and row["model"] == model]
            if len(cell) == len(tasks[role]) * arguments.runs:
                table[role][model] = summarise(cell)
    measured = [role for role in roles() if len(table[role]) == len(models)]
    before = {role: read_model(agent_files[role]) for role in roles()}
    chosen = {role: pick(table[role], before[role]) if role in measured else before[role] for role in roles()}
    result = {
        "version": VERSION, "tuned_at": tuned_at, "models": models, "left_out": left_out, "hard": arguments.hard,
        "stopped": stopped[0] if stopped else "", "table": table, "measured": measured,
        "before": before, "lineup": chosen, "applied": False,
    }

    if stopped:
        print(f"\nStopped after {len(rows)} of {len(jobs)} questions: {stopped[0]}")
        print("No agent was changed. The answers so far are saved: run the same command with --resume to continue.")
    elif not arguments.dry_run:
        result["applied"] = apply(executable, agent_files, chosen, before, tasks, arguments.timeout)
    (store / "lineup.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print()
    print_lineup(result)
    report_file = write_report(result)
    print(f"\nScore page: {report_file}")


def apply(executable, agent_files, chosen, before, tasks, timeout):
    """Write the chosen models, then prove each changed agent still answers. Any failure puts all back."""
    changed = [role for role in chosen if chosen[role] != before[role]]
    if not changed:
        print("\nThe current lineup is already the best one. Nothing changed.")
        return True
    backup = home_folder() / "backups" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True)
    for role in changed:
        shutil.copyfile(agent_files[role], backup / agent_files[role].name)
        write_model(agent_files[role], chosen[role])
    for role in changed:
        answer, _, error = ask(executable, PREFIX + role, None, tasks[role][0]["prompt"], timeout)
        if not answer:
            for restored in changed:
                shutil.copyfile(backup / agent_files[restored].name, agent_files[restored])
            print(f"\n{PREFIX}{role} did not answer on {chosen[role]} ({error}). All agents were put back.")
            return False
    print(f"\nApplied to {len(changed)} agents. The files from before are in {backup}")
    return True


def print_lineup(result):
    print(f"{'role':<10} {'model':<40} {'score':>5} {'speed':>8}   was")
    for role, model in result["lineup"].items():
        cell = result["table"][role].get(model)
        was = result["before"][role] or "OpenCode default"
        if cell:
            print(f"{role:<10} {model:<40} {cell['score']:>5} {cell['seconds']:>6} s   {'same' if was == model else was}")
        else:
            print(f"{role:<10} {was:<40} not measured")
    if not result["applied"]:
        print("(not applied to the agents)")


def status(arguments):
    files = require_install()
    saved = home_folder() / "lineup.json"
    scores = json.loads(saved.read_text(encoding="utf-8"))["table"] if saved.exists() else {}
    print(f"{'agent':<18} {'model':<40} {'score':>5}")
    for role, path in files.items():
        model = read_model(path)
        score = scores.get(role, {}).get(model, {}).get("score", "-")
        print(f"{PREFIX + role:<18} {model or 'OpenCode default':<40} {score:>5}")
    if not scores:
        print(f"\nNot tuned yet. Run: {PROGRAM} tune")


def report(arguments):
    saved = home_folder() / "lineup.json"
    if not saved.exists():
        sys.exit(f"Nothing to show yet. Run: {PROGRAM} tune")
    report_file = write_report(json.loads(saved.read_text(encoding="utf-8")))
    print(report_file)
    if not arguments.no_open:
        webbrowser.open(report_file.as_uri())


def write_report(result):
    """One self-contained page: who plays each role, and the full role x model score table."""
    models = result["models"]
    cards, lines, notes = [], [], []
    for role, model in result["lineup"].items():
        cell = result["table"][role].get(model)
        meta = f'{cell["score"]} / 10 &middot; {cell["seconds"]} s' if cell else "not measured"
        cards.append(
            f'<div class="card"><p class="role">{html.escape(role)}</p>'
            f'<p class="model">{html.escape(model or "OpenCode default")}</p><p class="meta">{meta}</p></div>'
        )
    for role in result["table"]:
        cells = []
        for model in models:
            cell = result["table"][role].get(model)
            if not cell:
                cells.append('<td class="none">not measured</td>')
                continue
            marker = ' class="chosen"' if result["lineup"][role] == model else ""
            failed = f' <span class="failed">{cell["errors"]} failed</span>' if cell["errors"] else ""
            cells.append(
                f'<td{marker} style="--score:{cell["score"] / 10}"><b>{cell["score"]}</b>'
                f'<small>{cell["seconds"]} s{failed}</small></td>'
            )
        lines.append(f"<tr><th>{html.escape(role)}</th>{''.join(cells)}</tr>")
    if result.get("stopped"):
        notes.append(f'This run stopped early: {html.escape(result["stopped"])} Continue it with <code>tune --resume</code>.')
    for model, reason in result.get("left_out", {}).items():
        notes.append(f"Left out at the roll call: <b>{html.escape(model)}</b> ({html.escape(reason)})")
    heads = "".join(f"<th>{html.escape(model.split('/', 1)[-1])}</th>" for model in models)
    page = (HERE / "report_template.html").read_text(encoding="utf-8")
    page = (
        page.replace("{{cards}}", "".join(cards))
        .replace("{{heads}}", heads)
        .replace("{{rows}}", "".join(lines))
        .replace("{{notes}}", "".join(f"<p>{note}</p>" for note in notes))
        .replace("{{tuned_at}}", html.escape(result["tuned_at"].replace("T", " ")))
        .replace("{{applied}}", "applied to the agents" if result["applied"] else "not applied")
        .replace("{{version}}", VERSION)
    )
    report_file = home_folder() / "report.html"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(page, encoding="utf-8")
    return report_file


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lineup", description="A self-tuning team of role agents for OpenCode.")
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("install", help="copy the role agents into OpenCode").set_defaults(run=install)
    commands.add_parser("uninstall", help="remove the role agents").set_defaults(run=uninstall)
    commands.add_parser("status", help="show the current lineup").set_defaults(run=status)
    tuner = commands.add_parser("tune", help="score the models and keep the best one per role")
    tuner.add_argument("--models", help="comma-separated provider/model list (default: all that OpenCode lists)")
    tuner.add_argument("--max-models", type=int, default=12, help="refuse a longer automatic list (default 12)")
    tuner.add_argument("--runs", type=int, default=1, help="times each question is asked (default 1)")
    tuner.add_argument("--parallel", type=int, default=3, help="questions asked at the same time (default 3)")
    tuner.add_argument("--timeout", type=int, default=180, help="seconds to wait for one answer (default 180)")
    tuner.add_argument("--hard", action="store_true", help="also ask the harder third question of every role")
    tuner.add_argument("--dry-run", action="store_true", help="score only, do not change the agents")
    tuner.add_argument("--resume", action="store_true", help="reuse the answers of a run that was stopped")
    tuner.add_argument("--opencode", help="path to the opencode executable")
    tuner.set_defaults(run=tune)
    reporter = commands.add_parser("report", help="write and open the score page")
    reporter.add_argument("--no-open", action="store_true", help="write the page without opening it")
    reporter.set_defaults(run=report)
    arguments = parser.parse_args(argv)
    arguments.run(arguments)


if __name__ == "__main__":
    main()
