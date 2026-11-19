"""Checks for Lineup. No OpenCode and no network needed: answers come from a stand-in.

    python -m unittest discover -s tests -v
"""
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

    def use_models(self, quality, dead=(), flaky=(), limit_after=None):
        """quality: model -> share of each role's tasks it answers well.

        dead: models that never answer. flaky: models that answer the roll call and nothing else.
        limit_after: the provider refuses every question after this many. Returns the list of questions asked.
        """
        place = {}  # prompt -> (task id, position within its role, tasks in that role)
        for tasks in lineup.load_tasks().values():
            for position, task in enumerate(tasks):
                place[task["prompt"]] = (task["id"], position, len(tasks))
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
            self.assertGreaterEqual(len(tasks[role]), 2, role)

    def test_a_correct_answer_scores_ten(self):
        for tasks in lineup.load_tasks().values():
            for task in tasks:
                self.assertEqual(lineup.score_answer(task, GOOD_ANSWERS[task["id"]]), 10.0, task["id"])

    def test_a_wrong_answer_does_not_score_ten(self):
        for tasks in lineup.load_tasks().values():
            for task in tasks:
                self.assertLess(lineup.score_answer(task, BAD_ANSWERS[task["id"]]), 10.0, task["id"])

    def test_no_answer_scores_zero(self):
        for tasks in lineup.load_tasks().values():
            for task in tasks:
                self.assertEqual(lineup.score_answer(task, ""), 0.0, task["id"])

    def test_fixture_paths_are_filled_in_and_exist(self):
        for tasks in lineup.load_tasks().values():
            for task in tasks:
                self.assertNotIn("{fixtures}", task["prompt"])
        for name in ("files/orders_q3.csv", "files/stock.csv", "files/notes.txt", "sales.csv", "feed.xml"):
            self.assertTrue((lineup.FIXTURES / name).is_file(), name)

    def test_the_sales_fixture_matches_the_expected_totals(self):
        totals = {}
        for line in (lineup.FIXTURES / "sales.csv").read_text(encoding="utf-8").splitlines()[1:]:
            _, region, amount = line.split(",")
            totals[region] = totals.get(region, 0) + float(amount)
        self.assertEqual(round(sum(totals.values()), 2), 4815.50)
        self.assertEqual(max(totals, key=totals.get), "North")
        self.assertEqual(round(totals["North"], 2), 2130.25)

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

    def test_a_fresh_tune_asks_everything_again(self):
        self.run_lineup("install")
        self.use_models({"p/one": 1.0})
        self.run_lineup("tune", "--models", "p/one")
        asked = self.use_models({"p/one": 1.0})
        self.run_lineup("tune", "--models", "p/one")
        self.assertEqual(len(asked), 12)


if __name__ == "__main__":
    unittest.main()
