# Changes

## 0.2.1 (19 November 2026)

- A provider can refuse one question with its usage-limit message while it answers the rest. Up to 0.2.0 that stopped the whole run, and `--resume` stopped at the same question again. Now Lineup asks the model one short question: if that is answered, the refused question counts as no answer, is named in the output and on the score page, and the run goes on. A real usage limit still stops the run as before.
- The check after applying a lineup uses a question that was not refused.
- Roll call: the first model is asked alone. On a fresh OpenCode two first starts at once collided ("database is locked"), and a working model was left out.
- Complete tuning runs on Ubuntu and macOS, on GitHub's test machines: two free models, all 18 questions, lineup applied. On both, 34 of 36 questions were answered and scored 10, and one question was refused on both models ([run](https://github.com/juw12/lineup/actions/runs/44477706951)). The Ubuntu run is the new example score page.
- The test workflow can do a full tuning run with several real models when started by hand, and keeps the result files.
- 40 tests, 38 before.

## 0.2.0 (19 November 2026)

- `tune --hard` asks a harder third task per role, 18 questions instead of 12. Each one needs several steps in one answer, for example counting across three log files or a month-over-month comparison by region.
- `--resume` reuses the answers of an everyday run when `--hard` is added later, so only the six new questions per model are asked.
- `lineup.exe` for Windows, for people without Python. A workflow builds it from the tagged source, tries it and attaches it to the release.
- Runs on macOS and Linux: file paths in the tasks are written in the spelling of the system, and a question that runs out of time stops OpenCode's helper processes there too.
- The unit tests run on Windows, macOS and Linux with Python 3.9 and 3.13 on every push, and a second job installs OpenCode on each system and checks that it lists the six agents.
- The README compares Lineup with oh-my-openagent, oh-my-opencode-slim and OpenBot.

## 0.1.0 (19 November 2026)

- Six role agents for OpenCode: files, docs, numbers, writer, office and briefing.
- `tune` asks every model the same fixed questions, scores the answers pass or fail and writes the best model of each role into the agent files, with a backup and a put-back.
- Roll call, stop on a usage limit, and `--resume`.
