---
name: improve-harness
description: Propose one evidence-backed change to the ASH harness's skills, subagents or role prompts. Use when acting as the ASH harness engineer.
---

# Improve the harness

You are given an evidence file (recent run metrics, failure summaries, retro suggestions, accumulated lessons, and previously rejected proposals). Your change will be benchmarked against the current harness; it is kept only if the benchmark pass rate does not drop and it is better on pass rate or cost.

1. Read the evidence. Find the most frequent or most expensive failure mode. Ignore one-offs.
2. Check `state/improvements.jsonl` excerpts in the evidence: do not re-propose a rejected idea unless you have new evidence.
3. Form one hypothesis: "Builders waste N turns doing X because the procedure never says Y."
4. Make one focused change that tests it. Good changes: a sharper procedure step, a new skill for a recurring situation, a subagent for a recurring sub-problem, promoting a well-supported lesson from `state/learnings.md` into a skill (then it no longer needs to be a lesson).
5. Keep prompts short. Every line is paid for in every session. Delete stale or redundant instructions when you can.
6. Do not edit the kernel (`ash/`, `plugin/hooks/`, `evals/`, `harness.json`, `bin/`, `tests/`). Do not commit; the orchestrator does.
7. Finish with the JSON result: `hypothesis`, `change_summary`, `expected_effect`.
