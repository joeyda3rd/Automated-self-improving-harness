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

## 8. Four improvement cycles on the audited gate, then effort (2026-10-22)

**Gate:** the 6 fair narrow failures plus 4 canaries, 2 runs each. At medium builder effort the baseline passed 45%. Five of the six fair evals were 0/2; `md-unterminated-html-narrow` was 1/2.

**Four improver proposals, all rejected.** Each was one more paragraph in `build-task`:
- grep for other callers and mirrored code;
- reproduce first and prefer existing helpers;
- always run the reviewer;
- keep the fix narrow and compare neighbouring inputs.

Over the baseline and the 4 candidates, the five stuck evals passed 0 of 40 runs. Two candidates were rejected for dropping `md-unterminated-html-narrow` from 1/2 to 0/2, which is probably noise at 2 runs, but the rule is conservative. No proposal used the new `plugin/bin/` tool option. The four cycles cost $20.

**A hand-made tool, dropped before spending on it.** `behavior-diff` replays every string literal in the test suite through the HEAD code and the working tree, and lists outputs that changed. On the builders' actual failed attempts it reported **zero** changed outputs from 1,787 inputs. Their regressions only show up in input combinations no existing test contains, so the tool could not have helped, and it was not added.

**Hidden variable found:** every builder had silently inherited the launching session's `CLAUDE_EFFORT=medium`. Effort is now an explicit per-role setting.

**Effort experiment, same gate:**

| Builder effort | Pass rate | Mean cost per run | Changed evals |
|---|---|---|---|
| medium (baseline) | 45% | $0.197 | |
| **high** | **55%** | $0.224 (+14%) | `md-unterminated-html` 0.5→1.0, `sq-splitter-nesting` 0→0.5, no regressions |

- **Decision:** the paired ratchet accepts high effort (more evals improved than regressed), so builders now run at `high`. The evidence is thin (two evals, one run each), and the same rule would undo it if a later benchmark disagrees.
- **Conclusion:** the other five fair failures stayed at 0 even with more thinking. Both prose and thinking time fail to move them, which points at a model capability limit on inferring unstated variants. The remaining levers are tools that generate and check variants (not tools that replay existing inputs), or a different model.

## 9. Final cycles at high effort, and where things stand (2026-10-22)

Three more cycles ran on the high-effort baseline; all were rejected:
- **Prose:** write a regression test for the reported input and its family. Improved on none, regressed on `md-unterminated-html-narrow`.
- **Prose:** verify sibling inputs. Same result.
- **Tool (the first one the improver wrote):** `plugin/bin/before-after`, which runs a command on the stashed original and on the edited tree and diffs the outputs, plus a skill step telling builders to run it over the reported input and its neighbours. It **improved on `sq-begin-transaction-narrow`**, a task stuck at 0 in every earlier run. It regressed on `md-unterminated-html-narrow`. With one win and one loss it was rejected.

**Noise is now the binding constraint.** `md-unterminated-html-narrow` has "regressed" in 4 of 7 candidates. Its pass rate swings between 0.5 and 1.0 with no change to the harness, so with 2 runs per eval it vetoes changes on noise alone. Next steps, in order:
1. Raise `improve_eval_repeats` to 4 for the gate. It costs twice as much, but per-eval rates become meaningful.
2. Treat evals whose baseline rate is strictly between 0 and 1 as noisy. A change should need a gain elsewhere that exceeds their swing.
3. Re-run the `before-after` tool candidate under that rule. It is the only change so far to move a stuck eval.

**Cumulative result:**

| Measure | Value |
|---|---|
| Benchmark | 95 validated evals: 16 synthetic, 51 real-bug (generous reports), 28 narrow variants (audited; 6 fair failures form the gate) |
| Improvement cycles run | 8 real cycles + 1 hand-run effort experiment |
| Accepted | 1: builder effort medium → high (gate 45% → 55%, +14% cost) |
| Rejected | 8, including 7 prose changes and 1 tool. Nothing that failed the ratchet was merged, and no kernel file was ever touched by the improver |
| Kernel bugs found by evidence | Stop gate bypassed under `--json-schema`; tool errors never recorded; inherited session id and effort; Pygments breaking evals; a system-wide `packaging` shadowing the code under test; budget not covering evals |
| Total spend | about $91 of the $100 budget |

## 10. Noise-aware acceptance, and an honest reversal (2026-10-23)

- **New rule:** with noise-aware acceptance in place, the evals with mixed history are exactly `md-unterminated-html-narrow` and `sq-splitter-nesting-narrow`.
- **Reversal:** both "wins" that justified adopting `high` builder effort were on those two evals. Under the better rule, high effort shows no measurable gain at 14% more cost, so builders are back on `medium`. That is the cached baseline, and later evidence can bring `high` back.
- **Archive:** rejected candidates are now archived, so the one change that ever moved a stuck eval (the improver's `before-after` tool, cycle 3 of §9) can be re-tested instead of being lost.

**Re-test of the archived `before-after` candidate** (medium effort, noise-aware rule): **rejected**, with identical results on every non-noisy eval. `sq-begin-transaction-narrow` stayed 0/2, so its earlier single pass did not replicate. The noisy `md-unterminated-html-narrow` dropped 0.5 → 0 and, as intended, no longer decided the outcome.

**Net result of the harness's own improvement loop so far: zero.** Ten proposals were benchmarked (prose, a tool, and effort), and none survived a fair, noise-aware comparison. The weakness the gate measures (inferring unstated variants of a reported bug) has not responded to instructions, tools that diff outputs, or more thinking.

**The real bottleneck is the eval pipeline.** It is still run by hand: mining, writing reports, validating, screening and auditing for fairness. Until the harness does that itself, its improvement stops when its operator does. That is the next piece of work.

## 11. The eval pipeline is now automated (2026-10-23)

`ash curate` runs mine → make → report → screen → audit → gate without a human (see ARCHITECTURE).

**First real run** on sqlparse:
- **Mine and make:** found a fix I had missed (function grouping with lowercase `as` in `CREATE TABLE … AS`), then built and validated the eval.
- **Report:** the reporter session ($0.28) wrote a precise full report and a one-example narrow report.
- **Screen:** both passed 2/2, so neither joins the gate; the narrow one is available as a canary.
- **Gate:** recomputing it dropped the two noisy evals automatically, leaving 4 discriminating evals plus 4 canaries.

That is below `min_gate_discriminating` (8), so with budget the daemon would now curate before improving. Real-run cost of the pipeline: about $0.70 per new eval pair (report plus screening), plus about $1 per audited failure.

**Remaining human roles:** setting the budget, choosing source projects in `evals/sources.json`, and a durable host for `ash daemon`.

## 12. Brownfield field test (2026-10-23)

**Assignment:** pagination (`--per-page`, prev/next placeholders, `/page/N/`) and a `sitemap.xml` (sitemaps.org namespace, absolute URLs from `--base-url`, `lastmod` from page dates, warning when the base URL is missing), added to the existing 1,100-line `sitegen`. The assignment gave no hints about its code.

**Result:** planned into 3 tasks, all merged first try, **$0.96 in total** (plan $0.34, then $0.17–0.23 per task). An independent probe site confirmed every requirement, including the defaults staying unchanged.

**Bug found and fixed:** the project history had 21 committed `__pycache__/*.pyc` files (`git add -A` in a project without a `.gitignore`). The harness now excludes build artefacts from every commit and writes a default `.gitignore` for new projects.
