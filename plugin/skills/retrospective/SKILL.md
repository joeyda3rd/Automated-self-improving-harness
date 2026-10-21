---
name: retrospective
description: Analyse a finished ASH run and distil reusable lessons. Use when acting as the ASH retrospector.
---

# Retrospective

Inputs are in the run directory named in the prompt: `task.json`, `result.json`, `tools.jsonl` (every tool call, with errors flagged), `gate.jsonl` (stop-gate verification attempts), `guard.jsonl` (blocked actions) and `transcript-*.jsonl`.

1. Establish what happened: outcome, cost, turns, where time went (repeated reads, failing commands, gate bounces, blocked actions).
2. Find the *avoidable* waste or failure. Ask: what single piece of knowledge, given at session start, would have prevented it?
3. Write at most 3 lessons. Each lesson must be:
   - general enough to help a different task (not "fix line 40 of foo.py"),
   - actionable as an instruction ("Run `pytest -x -q path` while iterating; the full suite takes 4 minutes"),
   - tagged `scope: "project"` (true only for this codebase) or `scope: "harness"` (true for building software in general).
4. If the run went cleanly, return no lessons. Noise is worse than silence: lessons are injected into every future session.
5. Rate the lessons the session was given (ids like `L-3fa2c1`, listed in the prompt; their text is in the session's start context in the transcript) in `lesson_feedback`: `helpful` if following it visibly helped, `harmful` if it misled the session or cost turns, `irrelevant` otherwise. Only rate lessons you have evidence about. Harmful lessons get deleted.
6. If you see a recurring problem that a lesson cannot fix (a missing skill, a bad procedure step), describe it in `harness_suggestion`; the improvement loop reads these.
