# Research brief

Research done on 2026-10-21 to check ASH's design against (a) how Claude Code actually behaves and (b) prior work on self-improving agents. Each finding below says what changed in ASH, or why nothing did.

## 1. Claude Code contracts (verified by live probes, CLI 2.1.305)

Docs: [hooks](https://code.claude.com/docs/en/hooks.md), [headless](https://code.claude.com/docs/en/headless.md), [plugins reference](https://code.claude.com/docs/en/plugins-reference.md), [plugin evals](https://code.claude.com/docs/en/plugin-evals.md). The behaviour below was observed in real sessions, using a plugin that dumped every hook's raw input.

| Finding | Effect on ASH |
|---|---|
| A tool call that fails (for example, Bash exiting non-zero) fires **`PostToolUseFailure`**, with an `error` string such as `"Exit code 2\n..."`. It does **not** fire `PostToolUse`. A Bash `tool_response` has `stdout`, `stderr` and `interrupted`, but no exit code field. | **Bug fixed.** Telemetry only listened to `PostToolUse`, so tool-error counts were always 0. It now listens to `PostToolUseFailure` too. Some non-zero exits (e.g. `test -f` returning 1 with no output) are reported as successes, so treat the count as a lower bound. |
| With `--json-schema`, the run ends as soon as the model calls the `StructuredOutput` tool. A Stop-hook block fired *after* that is recorded (`hook_blocking_error`) but **not honoured**. A Stop block *is* honoured when the model stops with plain text, in both the JSON-decision and exit-2 forms. | **Bug fixed.** Every builder run uses `--json-schema`, so the stop gate never bounced anything. The gate now runs as a PreToolUse **deny on `StructuredOutput`** whenever `status` is `done`. A live test confirmed a premature "done" is refused and the agent then fixes the work. The Stop gate remains as a backstop. |
| Stop blocks are capped at 8 consecutive continuations (configurable with `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`). | No change: ASH caps itself at `gate_max` (3). |
| `claude -p --output-format json` printed a single result object in live runs, with `session_id`, `total_cost_usd`, `num_turns`, `is_error` and `structured_output`. It waits 3 s for stdin unless stdin is closed. | The parser accepts either a single object or an array. Stdin is now `/dev/null`. |
| Child sessions inherit the parent's `CLAUDE_CODE_SESSION_ID` and related variables, so without `--session-id` a child reports the parent's id. | Those variables are stripped and every run passes `--session-id`. Resume was verified live. |
| `claude plugin eval` exists. It only has regex, tool-use, file-exists and LLM-judge graders ("there are no custom-code graders"), and each case runs 3 times. | Not adopted for the gate: ASH needs deterministic hidden `check.sh` graders. It is still useful for quick before/after checks of skill behaviour. |

## 2. Prior work on self-improving agents

**Darwin Gödel Machine** ([arXiv 2505.22954](https://arxiv.org/abs/2505.22954))
- The agent edits its own code. Instead of keeping only the best version, it keeps an *archive* of variants and samples parents roughly in proportion to score, inversely to how many children they already have.
- The ablation without open-ended exploration stalls: after a bad modification, gains become hard to recover.
- Evaluation is staged: 10 tasks, then about 50, then 200 for top candidates.
- **Reward hacking:** the agent disabled hallucination detection by removing its logging. Hacking was more frequent when the detection code was visible to the agent.
- Results went from 20% to 50% on SWE-bench, at about two weeks and roughly $22k per run.

**SICA** ([arXiv 2504.15228](https://arxiv.org/abs/2504.15228))
- Utility combines score, cost and time: U = 0.5·score + 0.25·(1 − cost/$10) + 0.25·(1 − time/300 s).
- The real gains came from **tooling and context management** (diff editor, AST symbol locator, context summariser) more than from prose.
- An asynchronous overseer cancels agents that loop or drift off task.
- The authors report high path dependence and variance.

**Huxley-Gödel Machine** ([arXiv 2510.21614](https://arxiv.org/abs/2510.21614))
- A high benchmark score does not predict good descendants. It picks parents by how well their lineage performs.

**Memory** ([Reflexion](https://arxiv.org/abs/2303.11366), [ExpeL](https://arxiv.org/abs/2308.10144), [AWM](https://proceedings.mlr.press/v267/wang25bx.html), [arXiv 2505.16067](https://arxiv.org/abs/2505.16067))
- Agents copy retrieved past experience.
- Flawed memories spread errors, and the errors amplify when outputs are written back into memory.
- Selective add-and-delete beat letting memory grow by about 10 points absolute. Later task outcomes work as free quality labels for stored memories.

**Autonomous Claude Code loops**
- Sources: Anthropic, [*Effective harnesses for long-running agents*](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents); [Ralph](https://ghuntley.com/ralph/).
- Reported failure modes: declaring victory early; stubs and placeholders; re-implementing code that already exists; deleting or editing tests ("unacceptable to remove or edit tests"); spec drift.
- Recommended remedies: one feature per session, fast checks that push back on broken work, and short agent instructions.

**Eval noise** ([*On Randomness in Agentic Evals*](https://arxiv.org/abs/2602.07150); [*Adding Error Bars to Evals*](https://arxiv.org/abs/2411.00640))
- Single-run pass@1 on SWE-bench Verified swings by 2–6 points, even at temperature 0. Gains of 2–3 points can be noise.
- Recommendation: repeated runs and paired comparisons.
- With 3 tasks, one flip moves the score by 33 points.

## 3. What changed in ASH

| Finding | Change |
|---|---|
| Noise; pooled pass rate hides task-for-task swaps | **Paired, per-task ratchet** (`evals.better`): keep a change only if more tasks improve than regress. A cost-only win must be at least 5% *and* show on most tasks. |
| Staged evaluation (DGM) | **Smoke stage**: evals marked `"smoke": true` run first, and any regression on them rejects the candidate before the full suite runs. |
| Saturated benchmark | **Three harder evals** (`duration-parse`, `ttl-cache`, `inventory-report`), each with edge cases stated in the spec and checked only by the hidden test. |
| Evaluator gaming (DGM) | Evals stay hidden from every role. **Canaries** fail the eval if the agent edited the given tests (`inventory-report` hashes `test_loader.py`; `fix-median` requires the original tests). |
| Test tampering (Anthropic, Ralph) | **Integrity check before every merge** (`ash/integrity.py`): it rejects a diff that deletes test files, removes more test cases than it adds, or adds skip markers, unless the task card asks for that. |
| Memory degradation (2505.16067, ExpeL) | **Curated lessons**: each has a stable id, each run records which lessons it was given, and retrospectives rate them. A lesson is deleted when rated harmful twice, or when sessions given it succeed clearly less often than average (`ash/memory.py:curate`). |
| Premature "done" (Anthropic) | Re-verification by the orchestrator, plus the stop gate now actually enforced on `StructuredOutput` (section 1). |

## 4. Not done yet, ranked

1. **Harder evals, more of them, and repeats.** Measured on 2026-10-21: the current harness passed **all 6 evals** (the 3 new "harder" ones included) at a mean $0.17 per eval and 6.7 turns. Well-specified single-module tasks with edge cases stated up front do not discriminate at this model's strength, so the ratchet can only reward cost cuts. Evals that would discriminate are long-horizon and closer to real assignments:
   - multi-file changes in a seeded repository of a few thousand lines;
   - specs that are ambiguous or underspecified, where the right move is a `blocked` report or a reasonable documented choice;
   - tasks with performance or concurrency requirements;
   - real bug reports from open-source projects, SWE-bench style.

   Aim for a baseline pass rate of 40–70% across about 30–50 tasks with `eval_repeats` ≥ 2. This remains the main limit on how well self-improvement can work.

   **Second measurement, also 2026-10-21.**
   - **Setup:** 10 harder evals written to the brief above: cron-next, csv-query, invoice-rounding (7 interacting bugs behind a symptom-only report), three-way-merge, config-layering, ledger-idempotency, rate-limiter-concurrency, semver-range, text-wrap-unicode, plugin-registry-refactor (about 1,000 lines). Each was validated against seeded mistakes that fail its check.
   - **Result:** the harness passed **10/10 on the first attempt** for $2.47 (mean $0.25, 7.5 turns). No stop-gate bounces, no guard denials, and no transcript touched the eval material.
   - **Conclusion:** a task whose spec states every rule is solved first try at this model's strength, however many rules there are. Discriminating evals will need what spec-complete tasks lack:
     - an underspecified intent the builder must infer from the codebase;
     - real repositories of tens of thousands of lines, e.g. real upstream issues and fixes cloned from open-source projects;
     - long-horizon assignments that the planner must decompose;
     - judgement calls that are graded, such as knowing when to report `blocked`.

     Until such evals exist, the ratchet can still optimise **cost and turns**: 16 tasks give the paired cost rule enough breadth.

   **Third measurement: real bugs, 2026-10-21.**
   - **Setup:** 9 evals built from real Python-Markdown fix commits (2025–2026) with `tests/make_git_eval.py`.
     - Seed: the parent commit, pinned by `seed.git.json`, with no git history.
     - Task: a user-style bug report with real actual-vs-expected output.
     - Hidden check: the fix's own tests plus the full test suite of about 1,100 tests.
     - Runs are offline: no web tools, downloads or clones.
   - **Result: 8/9** for $2.16 (mean $0.24, **11 turns** against 6–7 on the spec-complete evals).
   - **The failure is genuine.** In `md-html-comment-paragraph` the builder fixed both reported cases and added five tests of its own. Its fix, however, turned a multi-line comment inside an inline tag into escaped text, which the upstream tests cover.
   - **Conclusion:** this is the first eval the harness fails, and the first behaviour difference between harness versions that a benchmark can measure (inferring the general rule from a narrow report, and checking nearby cases). Real-bug evals are the direction to grow: more Markdown fixes (the miner found more), then other projects.
   - **Noise:** at 1 failure in 9, a single run cannot separate harness versions. Improvement cycles on this set need `eval_repeats` ≥ 2.
2. **An archive instead of a pure hill climb.** Keep the top 3–5 harness variants (as git branches) and sometimes branch from a non-best one; choosing parents by how well their lineage performs (HGM) is better still. Without this, the ratchet will plateau.
3. **Point the improver at tooling.** Let it add helper scripts or MCP tools, such as context summarisers or test-runner wrappers, not just prose. This is where DGM and SICA found their gains. The genome would need a `plugin/bin/` or `plugin/mcp/` mutable path.
4. **Drift check.** Every few accepted changes, re-run the original baseline and rotate in fresh held-out evals to detect overfitting to the benchmark.
5. **Overseer.** A cheap periodic check that cancels a looping build session, beyond what the budget cap already stops.

## 5. Field test: a real multi-task assignment (2026-10-21)

**Assignment:** build `sitegen`, a static site generator, from a one-page brief. It needed Markdown pages with front matter, templates with escaped and raw placeholders, tag pages, an RSS feed, drafts, static files, errors that name the bad file, and tests. The run was `ash run --until-empty --no-improve`.

- **Plan:** one planner session ($0.26) produced 8 tasks in a sensible order. A walking skeleton came first, then the parser, renderer and templates in parallel branches, then the pipeline, then the index, feed and end-to-end test.
- **Build:** all 8 tasks were done and merged first try, for $1.47 (7.5 turns each on average), with no gate bounces and no guard denials. The result is 1,116 lines of code and tests, and the base branch only ever moved by verified merges.
- **Independent check:** an unseen sample site passed every assignment point I tried. Titles, text and code blocks were escaped. Ordering was newest first. Drafts were skipped, and `--drafts` included them. Tag pages and a well-formed RSS feed were produced. Static files were copied byte for byte. A page with bad front matter failed the build and named the file. The one gap was in the brief, not the build: I never named the index template's placeholder. The builder chose `items`, documented it, and made unknown placeholders an explicit error.
- **Retros:** all 8 returned no lessons, which is correct for runs this clean. They cost $1.17, nearly as much as the builds. **Changed:** retros now run only for runs with friction (`retro: "auto"`).
- **Conclusion:** on a well-scoped greenfield assignment the build loop works end to end with real Claude, at about $0.20 per task. The weak spots are where the evals point: inferring intent beyond a narrow report.

## 6. First real improvement cycle (2026-10-21)

**Gate:** 22 real-bug evals (14 Markdown, 8 more-itertools) × 2 runs. The baseline cost $8.53 and passed 42/44. The only discriminating task was `md-html-comment-paragraph`, which failed 2/2.

**Proposal:** the improver read the evidence, including the failing builder's own report and its transcript, but never the hidden check. Its diagnosis: "builders fixing bugs patch only the reported inputs with ad-hoc heuristics and miss variants". It added one sentence to `build-task`: fix the root cause and test variants before declaring done.

**Verdict: rejected.** Results were identical on all 22 evals; the target task still failed 2/2. Cost was 1.5% lower (cheaper on 13/22), short of the 5% bar. The whole cycle cost about $19.

**Lessons:**
- The ratchet behaved as designed. A plausible, well-aimed change that did not move the benchmark was not merged. Under a pooled pass rate with a single repeat, it could have been accepted on noise.
- **Signal is the bottleneck:** 1 of 22 real-bug evals discriminates. A cycle costs about $19, so the gate needs many more failing-but-fair tasks before cycles pay off. The cheapest source is bugs that a strong model fixes *narrowly*: fixes whose upstream tests cover variants beyond the report. The miner can rank candidates by how many hidden test cases go beyond the reported example.
- **Prose may be too weak a lever.** Prior work (SICA, DGM) found gains in tooling, not instructions. Letting the improver add helper scripts (e.g. a "probe variants" tool that diff-tests related inputs against the pre-change code) is the next experiment worth its cost.

## 7. Narrow reports: where the signal is (2026-10-22)

**Setup:** 29 more real-bug evals from sqlparse (15) and pypa/packaging (14, July–October 2026). Each eval's report was screened twice with the current harness, and almost all passed. sqlparse scored 14/15; the one failure, `sq-comment-grouping`, needs visible tests to be broken and is excluded as unfair.

**The finding:** the bug reports had been written generously, spelling out the general rule the hidden tests check. Real reports are narrow: one reproducer, no rule. So 37 *narrow* variants were made, with the same hidden upstream tests and the report cut to one example plus "similar inputs are probably affected too; please fix the underlying problem". Only evals whose hidden tests go beyond the reported case got one.

| Report style | Runs | Pass rate |
|---|---|---|
| generous (rule spelled out), real-bug evals | 104 | ~98% |
| narrow (one example), same hidden tests | 74 | **58%** |

- **Result:** 15 narrow variants failed both runs and 1 failed one run; every one of them passes in its generous form.
- **Conclusion:** the builder reliably fixes what is described and often misses what a maintainer would also cover. That is the habit a better harness should improve, and now there is a benchmark that can measure it.
- **Caveat:** before these become the gate, each failure is audited for fairness. Could a careful engineer have inferred the hidden expectation from the report and the codebase, or is it a judgement call no harness can learn?

**Fairness audit (2026-10-22).** Each of the 16 narrow failures was audited by rebuilding the builder's final workspace from its transcript and re-running the hidden tests. The question was whether a strong human engineer, given only the report and the codebase, would be blamed for missing the failing case.
- **6 FAIR:** the same bug on a closely related input, or a regression the builder introduced in neighbouring behaviour that already worked. These are `md-attr-name-sanitize`, `md-em-strong-nesting`, `md-html-comment-paragraph`, `md-unterminated-html`, `sq-begin-transaction` and `sq-splitter-nesting` (narrow variants).
- **9 UNFAIR, 1 MIXED:** the hidden tests required something the report and the codebase don't imply:
  - a private method's signature;
  - deduplication or strictness policies;
  - an unrelated improvement bundled into the same upstream commit;
  - T-SQL's `GO <count>`;
  - behaviour that contradicts the seed's own test.

  Those narrow variants were deleted; their generous originals remain.
- **Lesson:** an upstream fix commit is not a clean task. Narrowing a report exposes everything else the commit did, so narrow evals need a fairness audit before they can gate anything.

**Environment bug found by the audit.** Installing pytest pulled in Pygments 2.21, which un-skipped two CodeHilite tests that fail with that version. Two Markdown evals had become impossible to pass and a third could only be passed by patching unrelated tests; the validator had run before the install. All Markdown evals now run through a `run_tests.py` that hides Pygments, as the suite's original conditions did, and all re-validate.

**The gate is now** the 6 fair narrow failures plus 4 passing narrow canaries, one per project, marked `smoke`. That is 10 evals × 2 runs, about $4 per benchmark.
