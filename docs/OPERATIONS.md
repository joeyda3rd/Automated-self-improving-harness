# Operating ASH

How to run the harness unattended, and what to watch.

## Start

```bash
export PATH="$PWD/bin:$PATH"
ash doctor                                   # pre-flight: CLI, git, budget, gate, kernel/genome split
ash -C ~/code/app init --verify "npm test"   # attach a project (any git repo, or an empty directory)
ash -C ~/code/app assign @spec.md            # give it work (or drop .md files into ~/code/app/.ash/inbox/)
ash -C ~/code/app daemon enable              # auto-start for this project
ash -C ~/code/app daemon --ensure            # start the supervisor now (idempotent)
```

For a host that stays up, run `ash daemon --ensure --if-enabled` from cron, a CI schedule or a scheduled cloud session every few minutes. It is a no-op while a daemon is alive.

## What the daemon does

Every iteration, in this order:

1. **Build:** take the next ready task from the project queue, then plan, build, verify and merge it.
2. **Curate:** if the improvement gate has fewer than `min_gate_discriminating` evals, mine new real-bug evals, write reports, screen and audit them, and update `evals/gate.json`. This happens at most every `curate_interval_s`, and only if `min_curate_budget_usd` remains.
3. **Improve:** propose a change to the genome, benchmark it against the gate, and keep it only if it wins under the paired, noise-aware rule. Needs `min_cycle_budget_usd`.
4. **Sleep** for `idle_sleep_seconds`.

**Building comes first.** While build work is queued, steps 2–3 run only if self-improvement has used less than `meta_budget_share` (default 40%) of all spend. Idle time is free to go to self-improvement.

## Watch

| Command | Shows |
|---|---|
| `ash status` | queue, daemon liveness (pid, phase, heartbeat age, last step) |
| `ash report` | per harness version: success rate, cost and turns per run, total spend vs budget, recent improvement decisions |
| `ash lessons` | what the fast loop has learned |
| `ash improve --list` | archived near-miss candidates (`ash improve --retry ID` re-tests one) |
| `state/daemon.log` | daemon output |
| `state/spend.jsonl` | every session's cost |

## Stop and recover

- `ash daemon stop`: finish the current step, then exit.
- `ash pause` / `ash resume`: halt or clear a halt (also clears the circuit breaker).
- **Container restarts are safe.** The lock dies with the process, interrupted baselines resume from saved runs, and tasks left `active` go back to the queue.
- **Budget:** `budget_usd_total` is a hard ceiling. No session starts once it is reached, and concurrent eval sessions reserve their caps up front.

## Tune

All settings live in `harness.json` (kernel; the harness cannot change it):

| Setting | Controls |
|---|---|
| `budget_usd_per_run` | cap per build session |
| `eval_budget_usd_per_task` | cap per benchmark session |
| `effort` | `--effort` per role |
| `improve_eval_repeats`, `eval_workers` | benchmark precision and parallelism |
| `meta_budget_share` | how much spend self-improvement may take while there is build work |
| `min_cycle_budget_usd`, `min_curate_budget_usd` | budget floors for improving and curating |
| `curate_per_source` | candidates mined per source per curation pass |

Projects to mine evals from: `evals/sources.json`.
