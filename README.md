# Lineup

[![tests](https://github.com/juw12/lineup/actions/workflows/tests.yml/badge.svg)](https://github.com/juw12/lineup/actions/workflows/tests.yml)

A team of six role agents for [OpenCode](https://opencode.ai) that picks its own models. Lineup asks every model you have the same fixed questions on your own machine, scores the answers pass or fail, and writes the best model for each role into the agent files. It keeps a backup, checks that every changed agent still answers, and puts everything back if one does not.

![The score page of the example run](docs/report.png)

The picture is the score page of a real run, also at [juw12.github.io/lineup](https://juw12.github.io/lineup/). It shows the finishing run: see [The finishing run](#the-finishing-run).

## On a Mac

- **Mac:** [`Lineup-macOS-AppleSilicon.dmg`](https://github.com/juw12/lineup/releases/download/mac/Lineup-macOS-AppleSilicon.dmg) (M1 and newer) or [`Lineup-macOS-Intel.dmg`](https://github.com/juw12/lineup/releases/download/mac/Lineup-macOS-Intel.dmg). Open it and drag Lineup to Applications. The first time, macOS blocks it because it is not notarized: **System Settings → Privacy & Security → Open Anyway**.

It is the web edition (https://juw12.github.io/lineup/) in its own window ([`desktop/`](desktop/README.md)) and changes with it. Each build is opened on an Apple-silicon Mac and an Intel Mac on GitHub before it is published: the page loads, the app starts and can store data. No Mac of ours has run it yet.

## What you get

Six agents you can pick in OpenCode (Tab in the terminal, the agent menu in the desktop app) or call as subagents:

| Agent | Job | May edit files | May run commands |
|---|---|---|---|
| `lineup-files` | find, list, read and compare files | no | no |
| `lineup-docs` | summarise, extract and restructure text | asks first | no |
| `lineup-numbers` | growth, margin, interest and other business arithmetic | no | no |
| `lineup-writer` | titles, hooks, posts, plain-English rewrites | asks first | no |
| `lineup-office` | totals and groupings on CSV and text data, small scripts | asks first | asks first |
| `lineup-briefing` | a short, linked briefing from feeds, pages and notes | no | no |

And one command, `tune`, that decides which model each of them uses.

## What it is not

Lineup is a thin layer on OpenCode: six agent files and one Python script. It is not a chat app, it has no messaging channels and no scheduler, and nothing runs in the background. If you want a full assistant app, this is not one.

## How it compares

Checked on 19 November 2026 in each project's own README and guides.

| | What it gives you | How an agent gets its model |
|---|---|---|
| [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) (was oh-my-opencode) | a large orchestration layer for coding: many agents, categories and workflows | from built-in chains: the first model in the chain that your providers serve |
| [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim) | an orchestrator with specialist coding agents | from presets you edit by hand; its README says to build your own around the models you have |
| [OpenBot](https://github.com/next-open-ai/openbot) | a desktop assistant app with ready-made role agents | chosen by hand in the app's settings |
| Lineup | six role agents for office work and one command | measured on your machine with fixed questions, then written into the agent files, with a backup and a put-back |

The first two are far bigger than Lineup and are built for coding. If you want an orchestrator, use one of them. Lineup does the one step they leave to you, which is to measure, and it only adds six agent files named `lineup-*`, so it changes no other agent.

## Install

You need OpenCode with at least one working model.

**With Python** (3.9 or newer, on Windows, macOS or Linux; no Python packages are installed):

```
git clone https://github.com/juw12/lineup
cd lineup
python lineup.py install
```

**On Windows without Python:** download `lineup.exe` from the [latest release](https://github.com/juw12/lineup/releases/latest) and run `lineup.exe install`. Every command on this page works the same with `lineup.exe` in place of `python lineup.py`.

Restart OpenCode and the six agents are there. `python lineup.py uninstall` removes them again and touches nothing else.

## Tune

```
python lineup.py tune --models provider/model-a,provider/model-b,provider/model-c
```

Without `--models`, Lineup uses every model that `opencode models` lists. If that is more than 12, it asks you to choose.

What happens:

1. **Roll call.** Every model gets one short question. A model that does not answer in 60 seconds is left out, so a retired model costs one question, not all of them.
2. **Questions.** Each role has two fixed everyday tasks (in `tasks.json`), so a model answers 12 questions per run. `--hard` adds a harder third task per role, which makes 18. `--runs 2` asks everything twice.
3. **Score.** Every task has pass-or-fail checks, for example "exactly 3 bullets", "the sum is 4,815.50", "the three newest links, in order, and no other". The score is the share of checks passed, from 0 to 10. No model judges another model.
4. **Pick.** The best score wins a role. On equal scores the faster model wins, and the model you already use stays.
5. **Apply.** Lineup copies the agent files to `~/.lineup/backups/`, writes the new `model:` lines, and asks each changed agent one question. If any of them does not answer, all files are put back.

Other commands:

```
python lineup.py tune --hard        also ask the harder third question of every role
python lineup.py tune --dry-run     score only, change nothing
python lineup.py tune --resume      continue a run that a usage limit stopped
python lineup.py status             the current lineup
python lineup.py report             open the score page
```

If a provider refuses more questions (a usage or rate limit), Lineup stops asking, changes no agent, and keeps every answer it already has. The same command with `--resume` continues from there, for up to 7 days. Some providers also refuse a single question with the same message while they answer the rest. Lineup tells the two apart by asking the model one short question: if that is answered, the refused question counts as no answer, is named on the score page, and the run goes on. `--resume` also reuses the answers of an everyday run when you add `--hard` later, so only the six new questions per model are asked.

Results stay on your machine in `~/.lineup` (`results.jsonl`, `lineup.json`, `report.html`).

## The example run

19 November 2026, Windows 11, stock OpenCode 1.19.5, no account, its nine free models, every question asked twice. That is 216 questions. The raw log is [docs/example-run.log](docs/example-run.log).

The run did not finish. After 46 answers nothing came back any more, and a direct check a few minutes later showed OpenCode's message "Free usage limit reached", with about 20 hours until the next try. So one role of six is fully measured:

| Model (briefing role, 4 answers each) | Score | Median time |
|---|---|---|
| nemotron-3.5-super-vl-free | 10 | 6.9 s |
| beam-free | 10 | 10.8 s |
| mimo-v2.6-flash-free | 10 | 17.1 s |
| nemotron-3.5-lightning-free | 10 | 20.5 s |
| deepseek-v4.1-flash-free | 10 | 23.9 s |
| flint-40b-free | 10 | 24.6 s |
| big-pickle | 10 | 28.5 s |
| glm-5.3-flash-free | 0 | no answer: OpenCode reports the model as retired |
| nemotron-3-ultra-free | 0 | no answer after about 85 s, four times |

What this run showed:

- Two of the nine listed models could not be used at all. A list of models is not a list of working models.
- The seven working models all passed both briefing tasks, so the pick came down to speed, and the fastest was about four times faster than the slowest.
- A free plan cannot pay for 216 questions in a day. That run saved its results only at the end and scored refused questions as 0. Roll call, stop on a usage limit, saving every answer at once and `--resume` were added because of it, and are covered by tests. Checked afterwards on the same machine: with the limit still active, `tune` left both models out at the roll call and changed nothing.

A dry run of one model (big-pickle) on all twelve questions earlier that day passed eleven. The twelfth failed because the agent asked for permission to run a command; that task now says "without running a command".

### The finishing run

<!-- finishing-run:start -->
Done on 19 November 2026, on one of GitHub's test machines instead of the first machine, whose free limit lasts until 20 November: Ubuntu, stock OpenCode 1.19.6, no account, two free models, all 18 questions (two everyday and one harder per role), each asked once, and the lineup applied to the agents. [The run](https://github.com/juw12/lineup/actions/runs/44477706951) keeps its files until 17 February 2027; the raw log is [docs/finishing-run.log](docs/finishing-run.log).

| Role | beam-free | big-pickle | Pick |
|---|---|---|---|
| briefing | 6.67 in 7.5 s, 1 of 3 without an answer | 6.67 in 14.1 s, 1 of 3 without an answer | beam-free |
| docs | 10 in 4 s | 10 in 7.9 s | beam-free |
| files | 10 in 6.4 s | 10 in 14.3 s | beam-free |
| numbers | 10 in 6.1 s | 10 in 7.8 s | beam-free |
| office | 10 in 5.5 s | 10 in 8.8 s | beam-free |
| writer | 10 in 4.9 s | 10 in 6.6 s | beam-free |

Each cell is the score out of 10 and the median time per answer. The pick is the best score, and the faster model when scores are equal.

34 of 36 questions were answered, and every answer scored 10. Two got no answer: `briefing-newest-three`, once on each model. The provider refused it with "Free usage limit reached" while the same model answered the other questions. Up to 0.2.0 that message stopped the whole run. Since 0.2.1 Lineup asks the model one short question first: if that is answered, only this question counts as no answer and the run goes on. Why the provider refuses this question I do not know. On the Windows machine, earlier the same day, seven free models answered `briefing-newest-three` (the table above).
<!-- finishing-run:end -->

## Your own tasks

The two everyday tasks of a role are a floor: they catch models that are retired, slow, or that ignore a format. The hard task of a role asks for several steps in one answer: count lines across three log files without counting the look-alikes, build a table sorted by a year that has to be worked out, price a product mix with two years of growth, write three sentences under six rules, compare two months by region, group a feed by day in a fixed line format.

None of them knows your work. The useful step is to add questions from your own work to `tasks.json`:

```json
{
  "id": "numbers-my-margin",
  "prompt": "Revenue 4,200, cost 3,150. Give the gross margin as a percentage.",
  "checks": [{"type": "regex", "value": "\\b25(\\.0+)?\\s*%"}]
}
```

Check types: `regex` (must match), `absent` (must not match), `bullets` (exact number of `- ` lines), `max_words`. Files for file tasks go in `fixtures/`; write `{fixtures}/your-file.csv` in the prompt and Lineup fills in the full path in the spelling of your system. Add `"level": "hard"` to a task that should only be asked with `--hard`.

## Limits

- Twelve small tasks, or eighteen with `--hard`, and one or two runs are a small sample. Read a score of 10 as "passed these checks", not as "the best model".
- Pass-or-fail checks measure whether an answer is correct and in the asked format. They do not measure style or depth.
- The full tuning run is tested on Windows 11 with stock OpenCode 1.19.5, and on one OpenCode 2.x build, where Lineup adds `--standalone` so each question gets its own server. On Ubuntu and macOS it is tested on GitHub's test machines, not on a person's computer: with OpenCode 1.19.6 and two free models, [one run on each system](https://github.com/juw12/lineup/actions/runs/44477706951) asked all 18 questions per model, measured all six roles and applied the lineup. On both, 34 of 36 questions were answered and scored 10, and `briefing-newest-three` was refused on both models with "Free usage limit reached", which counts as no answer. [A check of that question](https://github.com/juw12/lineup/actions/runs/44474441495) showed that it is answered with another agent, and also when it asks for the titles only or the links only, so the provider refuses it by its content. Why, I do not know. The unit tests run on all three systems on every push, and a second job installs OpenCode and checks that it lists the six agents.
- `lineup.exe` is built by a GitHub workflow from the tagged source and is not code-signed, so Windows may show a warning the first time you start it. The release lists its SHA-256.
- Every question starts OpenCode once, so a question takes seconds even on a fast model.
- I did not find another OpenCode add-on that measures models on your own machine and writes the result into the agents. If you know one, please open an issue and I will link it here.

## Where the idea comes from

The idea of ready-made role agents comes from [OpenBot](https://github.com/next-open-ai/openbot), a desktop assistant app. Lineup is written from scratch and shares no code with it. It keeps the roles, drops the separate app, and adds the measuring.

## Tests

```
python -m unittest discover -s tests
```

40 tests, no OpenCode and no network needed: they use a stand-in for the models and cover scoring, picking, install, apply and put-back, the roll call, the usage-limit stop and resume, a single refused question, and the hard tasks. They run on Windows, macOS and Linux with Python 3.9 and 3.13 on every push.

## License

MIT
