# Working on the ASH harness itself

ASH is an orchestrator (`ash/`, Python stdlib only) around headless Claude Code sessions that load the plugin in `plugin/`. Read `docs/ARCHITECTURE.md` before changing behaviour.

- **Kernel vs genome.** `ash/`, `plugin/hooks/`, `evals/`, `harness.json`, `bin/` and `tests/` are the kernel: they decide what counts as done, what is allowed, and whether a self-modification is kept. `plugin/roles/`, `plugin/skills/`, `plugin/agents/`, `plugin/bin/` (builder tools, run as `$ASH_PLUGIN_DIR/bin/<tool>`) and `docs/` are the genome the improvement loop evolves. When you change a kernel rule, keep the guard (`plugin/hooks/ash_hook.py` `KERNEL_PARTS`), `harness.json` `mutable_paths` and this list in agreement.
- **Hooks contract.** Hooks get their run context only from `ASH_*` environment variables set in `ash/claude.py:run_session`. With no `ASH_ROLE` set they must stay permissive, so interactive use of the plugin is unaffected.
- **Tests.** `python3 -m unittest discover -s tests -q`. They use `tests/fake_claude.py` via `ASH_CLAUDE_BIN` and must never call the real API. Any new role or schema needs a fake behaviour there.
- **Evals.** Each `evals/tasks/<name>/` has a `task.json` (what the builder sees), an optional `seed/`, a hidden `check.sh`, and a `reference/` solution (files laid over the seed). Run `python3 tests/validate_evals.py` before committing: every eval must fail on its seed and pass on its reference.
- **Spend.** Every session the harness launches is recorded in `state/spend.jsonl`. `run_session` refuses to start a session once `budget_usd_total` is reached, and an eval suite cut short is marked incomplete and can never be cached or accepted.
- **Prompts are paid per session.** Keep skills and roles short. Prefer deleting a stale instruction to adding a new one.
- **Long-running work.** Containers restart without warning. Run loops through `ash daemon` (single instance, heartbeat, resumes), or as a tracked background task. Never use a bare `nohup … &` that nothing monitors. Before ending a turn, check that nothing you started is still running unless something is watching it.
