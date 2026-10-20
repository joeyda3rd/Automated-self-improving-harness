---
name: build-task
description: The ASH builder's procedure for taking one queued task from card to verified, committed-ready change. Use whenever you are working an ASH task card.
---

# Build a task

1. **Orient (cheap first).** Read `.ash/notes.md` if present, then the task card. Locate the code the task touches with Grep/Glob before reading whole files. Find out how the project builds and tests (README, package manifest, Makefile).
2. **Pin "done".** Restate the acceptance criteria as concrete checks. If the project has a test suite, the criteria become tests. Write or extend the tests *first* when behaviour is new; delegate to the `test-writer` subagent when the surface is large.
3. **Implement in small steps.** Make the smallest change that moves one check from red to green, run the relevant tests, repeat. Match the surrounding code's style.
4. **Verify.** Run the `ash:verify` skill. Fix every failure you caused. If a failure predates your change, note it in your result instead of masking it.
5. **Review.** For any change over ~50 lines, ask the `reviewer` subagent to review the diff (`git diff`) against the task card, and address real findings.
6. **Record.** Update `.ash/notes.md` with anything a future session would have to rediscover (commands, layout, traps). Do not commit; the orchestrator commits.
7. **Report.** Finish with the JSON result: `status` (`done`, `blocked` or `failed`), a one-paragraph `summary`, `files_changed`, and `follow_ups` for work you discovered but that is out of scope (each a self-contained task title + spec).

Budget discipline: prefer targeted reads and test runs over whole-suite runs while iterating; run the full verification once at the end.
