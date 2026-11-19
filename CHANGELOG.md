# Changes

## After 0.2.0 (not in a release yet)

- The test workflow can ask one real model every question on Ubuntu and macOS when started by hand. It continues once with `--resume` after a usage-limit stop and prints why a question got no answer.
- Result of that job with two free models: 17 of 18 questions answered and scored 10 on both systems; one question was refused by the free plan every time, so a complete tuning run on macOS or Linux is still missing. The README limits say so.

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
