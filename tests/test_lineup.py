"""Checks for Lineup. No OpenCode and no network needed: answers come from a stand-in.

    python -m unittest discover -s tests -v
"""
import importlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lineup  # noqa: E402

# One answer per task that a careful person would give. Each must score 10.
GOOD_ANSWERS = {
    "files-list-csv": "orders_q3.csv\nstock.csv\n\nThere are 2 .csv files.",
    "files-find-date": 'notes.txt: "Delivery moved to 14 March."',
    "docs-three-bullets": (
        "- Runtime rose from 8 to 11 hours with a new display driver and lower standby current.\n"
        "- The battery is unchanged and charging still takes 95 minutes.\n"
        "- A 30 watt charger and a larger cell are tested next month."
    ),
    "docs-extract-numbers": "12%, 18%",
    "numbers-growth-margin": "Revenue growth: 25%\nGross margin last year: 25%\nGross margin this year: 30%\nMargin improved.",
    "numbers-simple-interest": "Total interest: 1,200. Total repaid: 9,200.",
    "writer-fixed-format": (
        "Title 1: How One Bakery Halved Its Food Waste\n"
        "Title 2: Less Bread in the Bin\n"
        "Title 3: Baking Only What Sells\n"
        "Hook: A small bakery counted every unsold loaf for a month, then changed three habits."
    ),
    "writer-plain-rewrite": "We will send your refund within five business days.",
    "office-column-sum": "4,815.50",
    "office-top-region": "North has the highest total: 2,130.25.",
    "briefing-newest-three": (
        "Solar roof approved for the sports hall https://example.org/news/solar-roof\n"
        "New bus lanes open on Mill Road https://example.org/news/bus-lanes\n"
        "Library extends evening hours https://example.org/news/library-hours"
    ),
    "briefing-count-day": "2",
    # the harder third task of every role (tune --hard)
    "files-count-errors": "run-01.log: 2\nrun-02.log: 4\nrun-03.log: 1\n\nrun-02.log has the most, 4. Total: 7.",
    "docs-table-order": (
        "| Name | Role | Start year |\n|---|---|---|\n| Ana | Team lead | 2019 |\n| Ben | Tooling | 2020 |\n"
        "| Chidi | Test lab | 2021 |\n| Dewi | Purchasing | 2023 |"
    ),
    "numbers-product-mix": (
        "Total revenue: 6,000.00\nTotal gross profit: 2,160.00\nOverall gross margin: 36.0%\n"
        "Highest margin: product C, 45%\nRevenue after two years: 7,260.00"
    ),
    "writer-three-sentences": (
        "Today our shop starts to refill glass bottles at the counter. Bring any clean bottle and pay only for "
        "what goes in. Which bottle will you bring first?"
    ),
    "office-month-change": "January: 2,915.75\nFebruary: 1,899.75\nNorth fell the most, by 730.25.",
    "briefing-by-day": (
        "2026-03-03: 1: Solar roof approved for the sports hall\n"
        "2026-03-02: 2: Library extends evening hours | New bus lanes open on Mill Road\n"
        "2026-03-01: 1: Harbour bridge repainting starts\n"
        "2026-02-28: 1: School garden wins regional prize"
    ),
}

# Plausible mistakes. None may score 10.
BAD_ANSWERS = {
    "files-list-csv": "orders_q3.csv, stock.csv and notes.txt, so 3 files.",
    "files-find-date": "The readme mentions a delivery in April.",
    "docs-three-bullets": "Here is the summary:\n- Runtime is up.\n- The battery is the same.\n- Charging is slow.\n- More tests follow.",
    "docs-extract-numbers": "The percentages are 18% and 12%.",
    "numbers-growth-margin": "Revenue growth: 20%. Margins: 25% and 33%.",
    "numbers-simple-interest": "Interest is 1,261 and the total is 9,261.",
    "writer-fixed-format": "Sure! Here are some ideas:\nTitle 1: Waste\nTitle 2: Bread\nTitle 3: Loaves\nHook: Read on.",
    "writer-plain-rewrite": "You will get your refund within five business days, as our policy states, without delay!",
    "office-column-sum": "The sum is 4,185.50.",
    "office-top-region": "South, with 1,358.25.",
    "briefing-newest-three": (
        "Harbour bridge repainting starts https://example.org/news/harbour-bridge\n"
        "Solar roof approved https://example.org/news/solar-roof\n"
        "School garden wins https://example.org/news/school-garden"
    ),
    "briefing-count-day": "There were 3 items.",
    "files-count-errors": "run-02.log has the most ERROR lines, 4. In total the word appears 9 times.",
    "docs-table-order": (
        "Here is the table:\n| Name | Role | Start year |\n|---|---|---|\n| Chidi | Test lab | 2021 |\n"
        "| Ana | Team lead | 2019 |\n| Dewi | Purchasing | 2022 |\n| Ben | Tooling | 2020 |"
    ),
    "numbers-product-mix": "Revenue 6,000, gross profit 2,160, margin 36%. Product C has the best margin. After two years: 7,200.",
    "writer-three-sentences": "Today we are excited to announce our new refill station! Bring your glass bottles. See you soon.",
    "office-month-change": "January: 2,915.75. February: 1,899.75. South fell the most, by 332.75.",
    "briefing-by-day": (
        "Here is the feed by day:\n- 3 March 2026: Solar roof approved for the sports hall\n"
        "- 2 March 2026: New bus lanes open on Mill Road, Library extends evening hours"
    ),
}


def event(kind, part):
    return json.dumps({"type": kind, "part": part})


class Sandbox(unittest.TestCase):
    """Every test gets its own OpenCode config folder and Lineup data folder."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.saved = {name: os.environ.get(name) for name in ("OPENCODE_CONFIG_DIR", "LINEUP_HOME", "LINEUP_OPENCODE")}
        os.environ["OPENCODE_CONFIG_DIR"] = str(root / "opencode")
        os.environ["LINEUP_HOME"] = str(root / "lineup")
        os.environ["LINEUP_OPENCODE"] = "stand-in"
        self.addCleanup(self.restore)
        self.real_ask = lineup.ask
        self.agents = root / "opencode" / "agents"
        self.home = root / "lineup"

    def restore(self):
        lineup.ask = self.real_ask
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def run_lineup(self, *arguments):
        with redirect_stdout(io.StringIO()) as output:
            lineup.main(list(arguments))
        return output.getvalue()

    def use_models(self, quality, dead=(), flaky=(), limit_after=None, hard_good=()):
        """quality: model -> share of each role's everyday tasks it answers well.

        dead: models that never answer. flaky: models that answer the roll call and nothing else.
        limit_after: the provider refuses every question after this many. Returns the list of questions asked.
        hard_good: the models that also answer the hard tasks well.
        """
        place = {}  # prompt -> (task id, position within its role, tasks in that role)
        for tasks in lineup.load_tasks().values():
            for position, task in enumerate(tasks):
                place[task["prompt"]] = (task["id"], position, len(tasks))
        hard = {
            task["prompt"]: task["id"]
            for tasks in lineup.load_tasks(hard=True).values() for task in tasks if task.get("level") == "hard"
        }
        asked = []

        def stand_in(executable, agent, model, prompt, timeout):
            model = model or lineup.read_model(self.agents / f"{agent}.md")
            if model in dead:
                return "", 1.0, "model not available"
            if prompt == lineup.ROLL_CALL:
                return "ready", 1.0, ""
            if limit_after is not None and len(asked) >= limit_after:
                return "", 1.0, "Free usage limit reached."
            asked.append((agent, model, prompt))
            if model in flaky:
                return "", 1.0, "empty answer"
            if prompt in hard:
                task, good = hard[prompt], model in hard_good
            else:
                task, position, count = place[prompt]
                good = position < round(quality[model] * count)
            return (GOOD_ANSWERS if good else BAD_ANSWERS)[task], quality.get("seconds:" + model, 5.0), ""

        lineup.ask = stand_in
        return asked


class Tasks(unittest.TestCase):
    def test_every_role_has_tasks_and_an_agent_file(self):
        tasks = lineup.load_tasks()
        self.assertEqual(sorted(tasks), lineup.roles())
        self.assertEqual(len(lineup.roles()), 6)
        for role in lineup.roles():
            self.assertEqual(len(tasks[role]), 2, role)

    def test_hard_adds_one_task_per_role(self):
        everyday, with_hard = lineup.load_tasks(), lineup.load_tasks(hard=True)
        for role in lineup.roles():
            self.assertEqual(len(with_hard[role]), 3, role)
            self.assertEqual([task["id"] for task in with_hard[role][:2]], [task["id"] for task in everyday[role]])
            self.assertEqual(with_hard[role][2].get("level"), "hard", role)
            self.assertTrue(all("level" not in task for task in everyday[role]), role)

    def test_a_correct_answer_scores_ten(self):
        for tasks in lineup.load_tasks(hard=True).values():
            for task in tasks:
                self.assertEqual(lineup.score_answer(task, GOOD_ANSWERS[task["id"]]), 10.0, task["id"])

    def test_a_wrong_answer_does_not_score_ten(self):
        for tasks in lineup.load_tasks(hard=True).values():
            for task in tasks:
                self.assertLess(lineup.score_answer(task, BAD_ANSWERS[task["id"]]), 10.0, task["id"])

    def test_no_answer_scores_zero(self):
        for tasks in lineup.load_tasks(hard=True).values():
            for task in tasks:
                self.assertEqual(lineup.score_answer(task, ""), 0.0, task["id"])

    def test_fixture_paths_are_filled_in_and_exist(self):
        prompts = {task["id"]: task["prompt"] for tasks in lineup.load_tasks(hard=True).values() for task in tasks}
        for prompt in prompts.values():
            self.assertNotIn("{fixtures}", prompt)
        for task, inside in (
            ("files-list-csv", "files"), ("office-column-sum", "sales.csv"),
            ("briefing-newest-three", "feed.xml"), ("files-count-errors", "logs"),
        ):  # the path in the prompt is this system's own spelling of a path that exists
            path = lineup.FIXTURES / inside
            self.assertTrue(path.exists(), inside)
            self.assertIn(str(path) + " ", prompts[task])
        for name in ("files/orders_q3.csv", "files/stock.csv", "files/notes.txt", "sales.csv", "feed.xml"):
            self.assertTrue((lineup.FIXTURES / name).is_file(), name)

    def test_a_fixture_path_takes_either_slash_and_keeps_the_full_stop_of_the_sentence(self):
        def fill(prompt):
            return lineup.FIXTURE_PATH.sub(lineup.fixture_path, prompt)

        expected = str(lineup.FIXTURES / "files" / "stock.csv")
        self.assertEqual(fill("Read {fixtures}/files/stock.csv."), f"Read {expected}.")
        self.assertEqual(fill("Read {fixtures}\\files\\stock.csv now"), f"Read {expected} now")
        self.assertEqual(fill("In {fixtures}, look"), f"In {lineup.FIXTURES}, look")

    def test_the_log_fixture_matches_the_expected_counts(self):
        counts = {
            path.name: sum(line.startswith("ERROR") for line in path.read_text(encoding="utf-8").splitlines())
            for path in (lineup.FIXTURES / "logs").glob("*.log")
        }
        self.assertEqual(counts, {"run-01.log": 2, "run-02.log": 4, "run-03.log": 1})
        mentions = sum(
            "error" in line.lower()
            for path in (lineup.FIXTURES / "logs").glob("*.log") for line in path.read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(mentions, 9)  # the count a careless reader gets, which the task rejects

    def test_the_sales_fixture_matches_the_expected_totals(self):
        totals = {}
        for line in (lineup.FIXTURES / "sales.csv").read_text(encoding="utf-8").splitlines()[1:]:
            _, region, amount = line.split(",")
            totals[region] = totals.get(region, 0) + float(amount)
        self.assertEqual(round(sum(totals.values()), 2), 4815.50)
        self.assertEqual(max(totals, key=totals.get), "North")
        self.assertEqual(round(totals["North"], 2), 2130.25)

    def test_the_sales_fixture_matches_the_month_change(self):
        months = {}
        for line in (lineup.FIXTURES / "sales.csv").read_text(encoding="utf-8").splitlines()[1:]:
            date, region, amount = line.split(",")
            months[(date[5:7], region)] = months.get((date[5:7], region), 0) + float(amount)
        january = {region: total for (month, region), total in months.items() if month == "01"}
        february = {region: total for (month, region), total in months.items() if month == "02"}
        self.assertEqual(round(sum(january.values()), 2), 2915.75)
        self.assertEqual(round(sum(february.values()), 2), 1899.75)
        change = {region: round(february[region] - january[region], 2) for region in january}
        self.assertEqual(min(change, key=change.get), "North")
        self.assertEqual(change["North"], -730.25)

    def test_the_packaged_program_reads_its_files_from_where_it_was_unpacked(self):
        self.addCleanup(importlib.reload, lineup)
        with tempfile.TemporaryDirectory() as unpacked:
            sys._MEIPASS = unpacked
            self.addCleanup(lambda: hasattr(sys, "_MEIPASS") and delattr(sys, "_MEIPASS"))
            importlib.reload(lineup)
            self.assertEqual(lineup.TASKS_FILE, Path(unpacked) / "tasks.json")
            self.assertEqual(lineup.AGENT_SOURCE, Path(unpacked) / "agents")
            del sys._MEIPASS

    def test_agent_files_are_valid_and_carry_no_model(self):
        for path in lineup.AGENT_SOURCE.glob("lineup-*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\ndescription: "), path.name)
            self.assertIn("\nmode: all\n", text)
            self.assertIsNone(lineup.read_model(path), path.name)


class Parsing(unittest.TestCase):
    def test_final_answer_is_the_text_after_the_last_tool_call(self):
        output = "\n".join([
            event("step_start", {"type": "step-start"}),
            event("text", {"type": "text", "text": "Let me look."}),
            event("tool_use", {"type": "tool", "tool": "read"}),
            event("text", {"type": "text", "text": "There are 2 files."}),
            event("step_finish", {"type": "step-finish"}),
        ])
        self.assertEqual(lineup.final_answer(output), "There are 2 files.")

    def test_final_answer_survives_noise(self):
        self.assertEqual(lineup.final_answer("not json\n[1, 2]\n" + event("text", {"type": "text", "text": " pong "})), "pong")
        self.assertEqual(lineup.final_answer(""), "")

    def test_failure_reason_prefers_the_error_opencode_reports(self):
        gone = json.dumps({"type": "error", "error": {"name": "APIError", "data": {"message": "Model x has been deprecated."}}})
        self.assertEqual(lineup.failure_reason(gone, "noise"), "Model x has been deprecated.")
        self.assertEqual(lineup.failure_reason("", "\x1b[91m! \x1b[0mpermission requested: bash"), "permission requested: bash")
        self.assertEqual(lineup.failure_reason("", ""), "empty answer")

    def test_failure_reason_reads_opencode_2_errors_and_the_log_of_opencode_1(self):
        refused = json.dumps({"type": "error", "error": {"type": "provider.free-limit", "message": "Free usage limit reached.", "status": 429}})
        self.assertEqual(lineup.failure_reason(refused, ""), "Free usage limit reached.")
        log = (
            'timestamp=2026-11-19T04:28:35Z level=INFO message="stream start"\n'
            'timestamp=2026-11-19T04:28:36Z level=ERROR message="stream error" modelID=x '
            'error.error="AI_APICallError: Free usage limit reached. Try later"\n'
            'timestamp=2026-11-19T04:28:37Z level=INFO message="retrying"'
        )
        self.assertEqual(lineup.failure_reason("", log), "AI_APICallError: Free usage limit reached. Try later")
        self.assertEqual(lineup.failure_reason("", 'timestamp=1 level=INFO message="start"'), "empty answer")

    def test_a_usage_limit_is_told_apart_from_a_model_failure(self):
        for reason in ("Free usage limit reached.", "Rate limit exceeded", "HTTP 429", "You exceeded your current quota"):
            self.assertTrue(lineup.LIMIT.search(reason), reason)
        for reason in ("Model x has been deprecated.", "empty answer", "no answer in 180 s"):
            self.assertFalse(lineup.LIMIT.search(reason), reason)

    def test_opencode_2_gets_its_own_server_per_question(self):
        self.assertEqual(lineup.version_flags("opencode v2.2.0"), ["--standalone"])
        self.assertEqual(lineup.version_flags("1.19.5"), [])
        self.assertEqual(lineup.version_flags(""), [])

    def test_check_types(self):
        self.assertTrue(lineup.check_passes({"type": "regex", "value": "^b"}, "a\nB"))
        self.assertTrue(lineup.check_passes({"type": "absent", "value": "x"}, "abc"))
        self.assertTrue(lineup.check_passes({"type": "bullets", "value": 2}, "- a\n - b\nc"))
        self.assertFalse(lineup.check_passes({"type": "max_words", "value": 2}, "one two three"))
        with self.assertRaises(ValueError):
            lineup.check_passes({"type": "nope", "value": 1}, "x")


class Picking(unittest.TestCase):
    def cell(self, score, seconds):
        return {"score": score, "seconds": seconds, "errors": 0, "runs": 2}

    def test_best_score_wins(self):
        self.assertEqual(lineup.pick({"a": self.cell(7, 3), "b": self.cell(9, 30)}, None), "b")

    def test_faster_model_wins_a_tie_between_new_models(self):
        self.assertEqual(lineup.pick({"a": self.cell(9, 12), "b": self.cell(9, 4)}, None), "b")

    def test_current_model_stays_on_a_tie(self):
        self.assertEqual(lineup.pick({"a": self.cell(9, 12), "b": self.cell(9, 4)}, "a"), "a")

    def test_current_model_is_replaced_when_it_is_worse_or_gone(self):
        self.assertEqual(lineup.pick({"a": self.cell(8, 2), "b": self.cell(9, 4)}, "a"), "b")
        self.assertEqual(lineup.pick({"a": self.cell(8, 2), "b": self.cell(9, 4)}, "retired"), "b")

    def test_nothing_changes_when_no_model_passed_anything(self):
        self.assertIsNone(lineup.pick({"a": self.cell(0, 2), "b": self.cell(0, 1)}, None))
        self.assertEqual(lineup.pick({"a": self.cell(0, 2)}, "retired"), "retired")


class Installing(Sandbox):
    def test_install_status_uninstall(self):
        self.run_lineup("install")
        self.assertEqual(len(list(self.agents.glob("lineup-*.md"))), 6)
        self.assertIn("Not tuned yet", self.run_lineup("status"))
        (self.agents / "my-own-agent.md").write_text("mine", encoding="utf-8")
        self.run_lineup("uninstall")
        self.assertEqual([path.name for path in self.agents.iterdir()], ["my-own-agent.md"])

    def test_model_line_is_written_once_and_survives_an_update(self):
        self.run_lineup("install")
        agent = self.agents / "lineup-docs.md"
        lineup.write_model(agent, "p/one")
        lineup.write_model(agent, "p/two")
        self.assertEqual(agent.read_text(encoding="utf-8").count("model:"), 1)
        self.run_lineup("install")
        self.assertEqual(lineup.read_model(agent), "p/two")
        self.assertTrue(agent.read_text(encoding="utf-8").startswith("---\nmodel: p/two\ndescription: "))

    def test_commands_need_an_install(self):
        with self.assertRaises(SystemExit):
            self.run_lineup("status")
        with self.assertRaises(SystemExit):
            self.run_lineup("tune", "--models", "p/a")


class Tuning(Sandbox):
    def test_tune_applies_the_best_model_and_writes_the_report(self):
        self.run_lineup("install")
        self.use_models({"p/weak": 0.5, "p/strong": 1.0})
        self.run_lineup("tune", "--models", "p/weak,p/strong", "--parallel", "2")
        for path in self.agents.glob("lineup-*.md"):
            self.assertEqual(lineup.read_model(path), "p/strong", path.name)
        saved = json.loads((self.home / "lineup.json").read_text(encoding="utf-8"))
        self.assertTrue(saved["applied"])
        self.assertEqual(saved["table"]["docs"]["p/strong"]["score"], 10.0)
        self.assertEqual(len((self.home / "results.jsonl").read_text(encoding="utf-8").splitlines()), 24)
        page = (self.home / "report.html").read_text(encoding="utf-8")
        self.assertNotIn("{{", page)
        self.assertEqual(page.count('class="chosen"'), 6)
        self.assertIn("p/strong", self.run_lineup("status"))

    def test_dry_run_changes_no_agent(self):
        self.run_lineup("install")
        self.use_models({"p/strong": 1.0})
        self.assertIn("not applied", self.run_lineup("tune", "--models", "p/strong", "--dry-run"))
        for path in self.agents.glob("lineup-*.md"):
            self.assertIsNone(lineup.read_model(path))

    def test_a_second_tune_with_equal_scores_keeps_the_lineup(self):
        self.run_lineup("install")
        self.use_models({"p/first": 1.0})
        self.run_lineup("tune", "--models", "p/first")
        self.use_models({"p/first": 1.0, "p/fast": 1.0, "seconds:p/fast": 1.0})
        self.assertIn("Nothing changed", self.run_lineup("tune", "--models", "p/first,p/fast"))
        self.assertEqual(lineup.read_model(self.agents / "lineup-files.md"), "p/first")

    def test_everything_is_put_back_when_a_chosen_model_stops_answering(self):
        self.run_lineup("install")
        self.use_models({"p/old": 0.5})
        self.run_lineup("tune", "--models", "p/old")
        before = {path.name: path.read_text(encoding="utf-8") for path in self.agents.glob("lineup-*.md")}

        scoring = {"p/old": 0.5, "p/new": 1.0}
        self.use_models(scoring)
        answering = lineup.ask

        def dies_after_scoring(executable, agent, model, prompt, timeout):
            if model is None:  # the check after applying asks the agent without naming a model
                return "", 1.0, "model not available"
            return answering(executable, agent, model, prompt, timeout)

        lineup.ask = dies_after_scoring
        self.assertIn("put back", self.run_lineup("tune", "--models", "p/old,p/new"))
        after = {path.name: path.read_text(encoding="utf-8") for path in self.agents.glob("lineup-*.md")}
        self.assertEqual(before, after)
        self.assertFalse(json.loads((self.home / "lineup.json").read_text(encoding="utf-8"))["applied"])

    def test_a_model_that_misses_the_roll_call_is_left_out(self):
        self.run_lineup("install")
        asked = self.use_models({"p/ok": 1.0}, dead=("p/dead",))
        self.assertIn("left out: p/dead", self.run_lineup("tune", "--models", "p/ok,p/dead"))
        saved = json.loads((self.home / "lineup.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["models"], ["p/ok"])
        self.assertEqual(saved["left_out"], {"p/dead": "model not available"})
        self.assertEqual({model for _, model, _ in asked}, {"p/ok"})
        self.assertIn("Left out at the roll call: <b>p/dead</b>", (self.home / "report.html").read_text(encoding="utf-8"))

    def test_no_model_at_the_roll_call_changes_nothing(self):
        self.run_lineup("install")
        self.use_models({}, dead=("p/dead",))
        with self.assertRaises(SystemExit):
            self.run_lineup("tune", "--models", "p/dead")
        self.assertFalse((self.home / "lineup.json").exists())

    def test_a_model_that_stops_answering_scores_zero_and_is_counted(self):
        self.run_lineup("install")
        self.use_models({"p/ok": 1.0}, flaky=("p/flaky",))
        self.run_lineup("tune", "--models", "p/ok,p/flaky")
        saved = json.loads((self.home / "lineup.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["table"]["office"]["p/flaky"], {"score": 0.0, "seconds": 1.0, "errors": 2, "runs": 2})
        self.assertEqual(lineup.read_model(self.agents / "lineup-office.md"), "p/ok")
        self.assertIn("2 failed", (self.home / "report.html").read_text(encoding="utf-8"))

    def test_a_usage_limit_stops_the_run_and_resume_finishes_it(self):
        self.run_lineup("install")
        self.use_models({"p/weak": 0.5, "p/strong": 1.0}, limit_after=10)
        output = self.run_lineup("tune", "--models", "p/weak,p/strong", "--parallel", "1")
        self.assertIn("Stopped after 10 of 24 questions: Free usage limit reached.", output)
        for path in self.agents.glob("lineup-*.md"):
            self.assertIsNone(lineup.read_model(path), path.name)  # nothing applied
        saved = json.loads((self.home / "lineup.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["measured"], ["briefing", "docs"])  # 2 models x 2 tasks each = 8 of the 10 answers
        self.assertEqual(saved["stopped"], "Free usage limit reached.")
        self.assertEqual(len((self.home / "results.jsonl").read_text(encoding="utf-8").splitlines()), 10)
        page = (self.home / "report.html").read_text(encoding="utf-8")
        self.assertIn("This run stopped early", page)
        self.assertIn("not measured", page)

        asked = self.use_models({"p/weak": 0.5, "p/strong": 1.0})  # the limit is gone
        output = self.run_lineup("tune", "--models", "p/weak,p/strong", "--parallel", "1", "--resume")
        self.assertEqual(len(asked), 14 + 6)  # the 14 open questions, then one check per changed agent
        self.assertEqual(output.count("(from the earlier run)"), 10)
        saved = json.loads((self.home / "lineup.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["measured"], lineup.roles())
        self.assertTrue(saved["applied"])
        for path in self.agents.glob("lineup-*.md"):
            self.assertEqual(lineup.read_model(path), "p/strong", path.name)
        self.assertEqual(len((self.home / "results.jsonl").read_text(encoding="utf-8").splitlines()), 24)

    def test_hard_asks_a_third_question_and_separates_models_that_tie_on_the_everyday_ones(self):
        self.run_lineup("install")
        models = {"p/fast": 1.0, "p/deep": 1.0, "seconds:p/fast": 1.0}
        self.use_models(models, hard_good=("p/deep",))
        self.run_lineup("tune", "--models", "p/fast,p/deep")
        self.assertEqual(lineup.read_model(self.agents / "lineup-numbers.md"), "p/fast")  # a tie, so speed decides

        asked = self.use_models(models, hard_good=("p/deep",))
        output = self.run_lineup("tune", "--models", "p/fast,p/deep", "--hard")
        self.assertIn("36 questions", output)
        self.assertEqual(len(asked), 36 + 6)  # 2 models x 18 questions, then one check per changed agent
        saved = json.loads((self.home / "lineup.json").read_text(encoding="utf-8"))
        self.assertTrue(saved["hard"])
        self.assertEqual(saved["table"]["numbers"]["p/deep"]["score"], 10.0)
        self.assertLess(saved["table"]["numbers"]["p/fast"]["score"], 10.0)
        for path in self.agents.glob("lineup-*.md"):
            self.assertEqual(lineup.read_model(path), "p/deep", path.name)

    def test_hard_resumes_from_an_everyday_run(self):
        self.run_lineup("install")
        self.use_models({"p/one": 1.0})
        self.run_lineup("tune", "--models", "p/one", "--dry-run")
        asked = self.use_models({"p/one": 1.0}, hard_good=("p/one",))
        output = self.run_lineup("tune", "--models", "p/one", "--hard", "--dry-run", "--resume")
        self.assertEqual(len(asked), 6)  # only the six hard questions are new
        self.assertEqual(output.count("(from the earlier run)"), 12)

    def test_a_fresh_tune_asks_everything_again(self):
        self.run_lineup("install")
        self.use_models({"p/one": 1.0})
        self.run_lineup("tune", "--models", "p/one")
        asked = self.use_models({"p/one": 1.0})
        self.run_lineup("tune", "--models", "p/one")
        self.assertEqual(len(asked), 12)


if __name__ == "__main__":
    unittest.main()
