# ASH architecture

ASH turns stock Claude Code into a software factory that runs unattended and gets better at its job over time. It adds no new agent framework. It composes Claude Code's own primitives (headless sessions, plugins, skills, subagents, hooks, session resume, structured output, budgets and mods) and puts a small, deterministic orchestrator around them.

The design rests on three rules:

1. **The model does the work; code makes the decisions that must not drift.** Choosing the next task, judging whether work is done, integrating it, and keeping or discarding a self-modification are all plain Python and shell exit codes. None of them is left to the model's judgement.
2. **Self-improvement only touches the "genome", never the "kernel".** The harness may rewrite its own prompts, skills and subagents. It may never rewrite the code that grades it, guards it, or runs it.
3. **Every change to the genome must win a benchmark.** It is a ratchet, compared task by task: a change ships only if more eval tasks improve than regress, or nothing changes and it is measurably cheaper on most tasks.

How the design was checked against Claude Code's real behaviour and against prior work on self-improving agents is in [RESEARCH.md](RESEARCH.md).

## The two halves

| | Kernel (immutable to the harness) | Genome (evolved by the harness) |
|---|---|---|
| What | `ash/` orchestrator, `plugin/hooks/` guardrails and gates, `evals/` benchmark, `harness.json`, `bin/`, `tests/` | `plugin/roles/` session personas, `plugin/skills/` procedures, `plugin/agents/` subagents, `plugin/bin/` builder tools (prior work found the biggest gains in tooling), `docs/` |
| Changed by | humans | the improvement loop, behind the eval gate |
| Enforced by | the PreToolUse guard (denies edits and shell writes), the post-hoc diff check in `improve.py`, and hidden evals | - |

Memory (`state/learnings.md`, per-project lessons, `.ash/notes.md`) is a third tier. It is written freely by the fast loop, kept small by a cap and deduplication, and re-injected at every session start.

## Claude Code primitive → ASH role

| Claude Code feature | How ASH uses it |
|---|---|
| **Headless sessions** (`claude -p`, `--output-format json`) | Every unit of work (plan, build, retro, improve, eval) is one non-interactive session launched by `ash/claude.py`. |
| **Structured output** (`--json-schema`) | Each role returns a schema-checked JSON object (`BUILD_SCHEMA`, `PLAN_SCHEMA`, ...), so the orchestrator never parses prose. |
| **Sessions** (`--session-id`, `--resume`) | Each run gets a known session id. When independent verification fails, the orchestrator *resumes the same session* with the failure, so the agent keeps all its context instead of starting cold. Transcripts are copied into the run record by the `SessionEnd` hook. |
| **Plugins** (`--plugin-dir`) | All behaviour ships as one plugin (`plugin/`), so it can be loaded into any project without touching the project's own `.claude/`. Improvement candidates are benchmarked by pointing `--plugin-dir` at a worktree copy. |
| **System prompt** (`--append-system-prompt`) | Role personas in `plugin/roles/*.md` (builder, planner, retro, improver). |
| **Skills** | Procedures: `build-task`, `verify`, `plan-work`, `retrospective`, `improve-harness`. These are the main thing self-improvement edits. |
| **Subagents** | `reviewer` (diff review against the task card) and `test-writer` (tests first). The improver can add more when a sub-problem recurs. |
| **Hooks: SessionStart** | Injects lessons from memory, project notes and the definition of done. This is how learning reaches new sessions. |
| **Hooks: PreToolUse** | The guard: confines writes to the workspace, blocks `git push`, `sudo`, `curl \| sh` and similar, keeps sessions out of orchestrator state, protects the kernel from the improver, and hides `evals/` so neither builders nor the improver can learn the answers. |
| **Hooks: PostToolUse / PostToolUseFailure / SubagentStop** | Telemetry. Every tool call goes to `tools.jsonl`. A failed call arrives as `PostToolUseFailure`, so errors are flagged with their message. |
| **Hooks: PreToolUse on `StructuredOutput`** | The verification gate. When the agent submits `status: done`, the hook runs `ASH_VERIFY_CMD`. On failure it denies the submission and feeds the output back, up to `gate_max` times. It lives here because a `--json-schema` run ends once the result is submitted. |
| **Hooks: Stop** | A backstop for the same gate when a session ends without structured output. |
| **Hooks: PreCompact / SessionEnd** | Records compactions and saves the transcript into the run directory for the retrospective. |
| **Effort** (`--effort`) | Set per role in `harness.json` (`effort`), never inherited. Before this, every builder silently inherited the launching session's `CLAUDE_EFFORT`. |
| **Budgets** (`--max-budget-usd`) | A cap per session, plus a total cap (`budget_usd_total`) enforced by the loop. |
| **Permission modes** | `bypassPermissions` by default, so the loop never blocks on a prompt. The guard hook still applies under it, and the harness is meant to run in a container or VM. |
| **Mods** | `mods/harness-console` is a live pane (`/ash`) and status-line entry that shows the queue, recent runs and every keep/reject decision, for anyone with a Claude Code session open in the project. |
| **Git worktrees** | One worktree and branch per task (`ash/T-0007`), and one per improvement attempt (`ash-improve/<ts>`). Base branches only move by verified merges. |

## The loops

```
                ┌──────────────────────── ash run (continuous) ───────────────────────┐
 assignment ──▶ │ intake ─▶ plan ─▶ ready queue ─▶ build ─▶ verify ─▶ integrate ─▶ retro │
 (.ash/inbox,   │            │       (deps,        (worktree, (stop gate + (merge base  (lessons ─▶ memory)
  ash assign)   │            ▼        priority)     resume on  orchestrator  in, re-verify,      │
                │       child tasks                 failure)   re-check)     merge --no-ff)     │
                └──────────────────────────────────────────────────────────────────────┘
                                         every N builds │
                                                        ▼
                ┌──────────────────── improvement cycle (slow loop) ──────────────────┐
                │ evidence ─▶ improver session in harness worktree ─▶ kernel diff check │
                │   ─▶ benchmark candidate vs cached baseline ─▶ keep (merge) / discard │
                │   ─▶ log to state/improvements.jsonl (rejected ideas are remembered)  │
                └──────────────────────────────────────────────────────────────────────┘
```

### Build loop (per task)

1. **Pick**: the highest-priority pending task whose dependencies are all `done`. Tasks that depend on a failed task become `blocked`.
2. **Plan tasks** (`kind: plan`) run the planner read-only on the project root. It returns child tasks with acceptance criteria and dependencies, and may set the project's `verify_cmd`.
3. **Build tasks** run the builder in a fresh worktree off the base branch:
   - The gate hook refuses a `done` result until `verify_cmd` passes (inner loop, inside the session).
   - The orchestrator then re-runs `verify_cmd` itself and does not trust the agent's claim. If it fails, it resumes the same session with the output (middle loop, `max_attempts_per_run`).
   - A failed run puts the task back in the queue, with the failure written into its card for the next attempt (outer loop, `max_runs_per_task`).
4. **Integrate**: commit, then run the test-integrity check (`ash/integrity.py` rejects deleted test files, net-removed test cases and new skip markers unless the card asks for them). Merge the latest base *into* the task branch, verify again, then `merge --no-ff` into base. A conflict, a tampering finding or a post-merge failure sends the task back with the reason in its card.
5. **Follow-ups** the builder reports become new low-priority tasks, at most two generations deep.
6. **Retro** (fast loop), only for runs with friction (`retro: "auto"`): a failure, a retry, a gate bounce, a guard denial, at least `retro_min_tool_errors` tool errors, or at least `retro_min_turns` turns. A field test showed retros of clean runs return nothing and cost nearly as much as the build. A cheap session reads the run record (telemetry, gate history, guard denials, transcript) and returns at most three lessons, each scoped `harness` or `project`. They are deduplicated and capped, then injected at every later session start. Suggestions that a lesson cannot fix go to `state/suggestions.jsonl` for the slow loop.
7. **Curation**: memory that only grows degrades. Each lesson has an id, and each run records which lessons it was given. The retro rates those lessons `helpful`, `harmful` or `irrelevant`, and `memory.curate` deletes a lesson rated harmful twice, or one whose sessions succeed clearly less often than average (`state/lessons_pruned.jsonl` keeps the record).

### Improvement cycle (slow loop)

Triggered every `improve_every` builds, or by hand with `ash improve`.

1. **Evidence**: outcome mix, cost, turns, gate bounces, guard denials and tool errors over recent runs; failure notes; retro suggestions; current lessons; and every earlier improvement attempt with its verdict.
2. **Propose**: the improver works in a worktree of the harness repo, with writes restricted to `mutable_paths` by the guard (`ASH_WRITE_ROOTS`). It makes one focused change and states its hypothesis.
3. **Kernel check**: any changed file outside `mutable_paths` rejects the attempt outright. This is a second line of defence behind the guard.
4. **Benchmark, staged**: evals marked `"smoke": true` run first, and any per-task regression rejects the candidate there. Otherwise the rest of `evals/tasks/` runs. Each eval runs `eval_repeats` times in a throwaway repo, with `--plugin-dir` pointing at the candidate, and the hidden `check.sh` decides pass or fail. Canaries in some checks fail the eval if the agent edited the tests it was given. The baseline score is cached per harness commit.
   Only the evals matching `improve_evals` (glob patterns; currently the real-bug evals) gate a change, each run `improve_eval_repeats` times. Evals every version passes carry no signal and would only cost money. The rest stay runnable with `ash eval`.
5. **Ratchet** (`evals.better`), paired per task: keep the change if more tasks improve than regress, with a positive net gain. If no task changed, keep it only if mean cost drops by at least `improve_min_cost_gain` *and* it was cheaper on most tasks. Otherwise discard it.
6. **Apply**: the change is committed with its hypothesis and evidence, and merged into the live harness. Plugin files are read fresh by every session, so the next build already uses the new genome. Nothing needs to restart.

`ash report` prints success rate, cost and turns grouped by harness commit. That table is the learning curve.

## The supervisor (`ash daemon`)

Long jobs used to run as loose shell scripts. Container restarts left stale entries behind, and nothing could tell a live loop from a dead one. Now one supervisor drives everything:
- **Single instance:** an exclusive `flock` on `state/daemon.lock`. The kernel releases it when the process dies, so a crash or a container restart never leaves a lock that looks alive.
- **Heartbeat:** written to `state/daemon.json` every 30 s, with the current phase and the last step. `ash status` shows it.
- **Each iteration:** build one ready task, else run an improvement cycle when one is due and `min_cycle_budget_usd` remains, else sleep. `STOP`, `PAUSED` and a budget shortfall halt it. `SIGTERM` (sent by `ash daemon stop`) lets the current step finish.
- **Auto-resume (opt-in):** `ash [-C project] daemon enable`. This repo's `.claude/settings.json` has a SessionStart hook that runs `ash daemon --ensure --if-enabled`, which is a no-op inside ASH's own sessions or when a daemon is alive. Interrupted baselines resume from saved runs, so restarting costs only the runs in flight.

## Candidate archive and noise

- **Archive:** a candidate that was benchmarked and rejected is kept as `state/archive/<id>.patch`. `ash improve --list` shows them. `ash improve --retry <id>` re-applies one and benchmarks it again without paying for a new proposal. Near misses are not lost to one noisy measurement.
- **Noise-aware ratchet:** an eval whose recorded outcomes are mixed (at least 4 runs, pass rate between 15% and 85%) is *noisy*. Its swings only count toward a decision when they reach `0.75`, which at 2 runs means a full flip. Evals that reliably fail or reliably pass keep full weight.

## Safety and failure containment

- **Kill switches**: `ash pause` (writes `state/STOP`, so the loop stops after the current task); a circuit breaker after `max_consecutive_failures` writes `state/PAUSED` and refuses to restart until `ash resume`.
- **Budgets**: per session, per eval task, per improvement attempt, and a lifetime total. Every session is recorded in `state/spend.jsonl`. Eval sessions run `eval_workers` at a time, and each reserves its per-session cap before starting, so concurrent sessions cannot overshoot the total together.
- **Crash recovery**: tasks left `active` by a crash go back to `pending` on the next start. Orchestrator exceptions are caught per task.
- **No reward hacking by construction**: the verification command, eval checks and gate logic live in the kernel. Eval checks are hidden from every agent role. The orchestrator re-verifies independently instead of trusting `status: done`.
- **Blast radius**: sessions write only inside their worktree (and `/tmp`), cannot push, cannot touch `.ash/` state (except `notes.md`), and cannot modify the harness while building a project.
- **Run it in a sandbox.** `bypassPermissions` plus shell access is powerful. Run ASH in a container or VM with only the credentials it needs.

## Known limits and extension points

- **Eval noise**: LLM runs are stochastic (pass@1 swings 2–6 points on SWE-bench even at temperature 0). With 6 evals and `eval_repeats: 1`, a lucky or unlucky run can flip a decision. Aim for 30–50 evals and at least 2 repeats as budget allows. Rejected ideas are remembered, so noise mostly costs time, not regressions.
- **Greedy ratchet**: only the current best harness is ever modified. Prior work (Darwin Gödel Machine, Huxley-Gödel Machine) shows this plateaus, and that an archive of variants to branch from does better. See RESEARCH.md §4 for this and the other open items.
- **Benchmark drift**: the harness can only get better at what the evals measure. Add evals that look like the work you actually assign. A good habit is to turn every real failure into a new eval.
- **Grep leakage**: the guard hides `evals/` from paths it can see, but a broad recursive grep from the harness root during an improvement could still surface check scripts. Keeping evals outside the repo (and changing `evals_dir`) closes that gap fully.
- **Intake**: `.ash/inbox/*.md` and `ash assign` are the built-in channels. A GitHub-issues or Linear poller only has to write inbox files.
- **Scale-out**: tasks are independent worktrees, so several `ash run` workers could share one queue if task claiming were made atomic (for example with a lock file per task). That change is not implemented.
