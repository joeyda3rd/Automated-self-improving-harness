# Contributing to ASH

Thanks for helping. ASH changes itself, so contributions follow a few rules that keep it honest.

## The one rule: kernel vs genome

| Kernel (humans change it) | Genome (the harness evolves it) |
|---|---|
| `ash/` orchestrator, `ash/prompts/` (reporter, auditor), `plugin/hooks/`, `evals/`, `harness.json`, `bin/`, `tests/` | `plugin/roles/`, `plugin/skills/`, `plugin/agents/`, `plugin/bin/`, `docs/` |

The kernel decides what counts as done, what is allowed, and whether a self-modification is kept. Never let a genome change weaken it. If you change a kernel rule, keep these three in agreement: `KERNEL_PARTS` in `plugin/hooks/ash_hook.py`, `mutable_paths` in `harness.json`, and the table above.

Changes to the genome are best proposed the way ASH proposes them: run `ash improve`, or open a PR with benchmark numbers from `ash eval` that show the change wins under the paired, noise-aware rule.

## Development

```bash
python3 -m unittest discover -s tests -q   # offline: tests use tests/fake_claude.py, never the real API
claude plugin validate plugin              # if you have the Claude Code CLI
bin/ash doctor
```

- **Python standard library only.** No runtime dependencies.
- **New roles or schemas** need a fake behaviour in `tests/fake_claude.py`.
- **Hooks** read their context only from `ASH_*` environment variables. They must stay permissive when `ASH_ROLE` is unset, so interactive Claude Code use is unaffected.
- **Prompts are paid for in every session.** Keep them short; prefer deleting a stale instruction to adding one.

## Evals

Each `evals/tasks/<name>/` holds:
- `task.json`: what the builder sees;
- a seed: `seed/`, or `seed.git.json` pinning a public commit;
- a hidden `check.sh`;
- a `reference/` solution.

Run `python3 tests/validate_evals.py <name>` before committing; every eval must fail on its seed and pass on its reference. Prefer `ash curate` to hand-written evals: it mines real bug fixes, writes reports, and screens and audits them.

A narrow eval (one-example report) may only gate self-improvement once an audit judges its failures fair. A strong engineer must be able to infer the hidden expectation from the report and the codebase.

## Spending money safely

Anything that runs real sessions (`ash run`, `ash eval`, `ash improve`, `ash curate`, `ash daemon`) spends money. `budget_usd_total` in `harness.json` is a hard ceiling, and every session is logged to `state/spend.jsonl`. Run long work through `ash daemon` or a tracked job, never a bare `nohup`.
