# Working on the ASH harness itself

ASH is an orchestrator (`ash/`, Python stdlib only) around headless Claude Code sessions that load the plugin in `plugin/`. Read `docs/ARCHITECTURE.md` before changing behaviour.

- **Kernel vs genome.** `ash/`, `plugin/hooks/`, `evals/`, `harness.json`, `bin/` and `tests/` are the kernel: they decide what counts as done, what is allowed, and whether a self-modification is kept. `plugin/roles/`, `plugin/skills/`, `plugin/agents/` and `docs/` are the genome the improvement loop evolves. When you change a kernel rule, keep the guard (`plugin/hooks/ash_hook.py` `KERNEL_PARTS`), `harness.json` `mutable_paths` and this list in agreement.
- **Hooks contract.** Hooks get their run context only from `ASH_*` environment variables set in `ash/claude.py:run_session`. With no `ASH_ROLE` set they must stay permissive, so interactive use of the plugin is unaffected.
- **Tests.** `python3 -m unittest discover -s tests -q`. They use `tests/fake_claude.py` via `ASH_CLAUDE_BIN` and must never call the real API. Any new role or schema needs a fake behaviour there.
- **Evals.** Each `evals/tasks/<name>/` has a `task.json` (what the builder sees), an optional `seed/`, and a hidden `check.sh`. A new eval must fail on its seed and pass on a reference solution. Check both before committing.
- **Prompts are paid per session.** Keep skills and roles short. Prefer deleting a stale instruction to adding a new one.
