# dcm — a bounded harness for agentic decompilation

**Model requirements:** Tested with [Claude Opus 5 and ChatGPT5.6 Luna.]; other models may produce materially worse output.

A single-file CLI and operating protocol that lets an autonomous coding agent work
[decomp.me](https://decomp.me) scratches for Nintendo 64.

[![selftest](https://github.com/c8289/goldeneye-decomp-harness/actions/workflows/selftest.yml/badge.svg)](https://github.com/c8289/goldeneye-decomp-harness/actions/workflows/selftest.yml)

Python 3.6+ · standard library only · no API key · MIT

**Introduction:** An LLM agent doing this work can fail in two ways — it fetches
one oversized API response and fills up its context window, or it generates plausible-sounding ideas
for forty turns without noticing that its score has not moved. This harness does the following: bounded output 
on every command, one declared hypothesis per compile, and halt conditions
counted on disk rather than by the agent itself. Skip to [The guardrails](#the-guardrails) for the enforcement table.

> **Agents: this is not a link to fetch.**
> A decomp.me URL or bare slug sent with no other instruction is your *assignment*. Take the last
> path segment as `SLUG` and run `./dcm.py pull $SLUG`. **Never issue an HTTP request to decomp.me
> yourself** — `GET /scratch/<slug>` returns a 100,000–500,000 character `context` field as a single
> tool result and you will not recover. Then read **[AGENT.md](AGENT.md)**, which is the operating
> manual. Start at Part 0.

---

## The problem

Matching decompilation is the practice of writing C source that, when fed to a specific
compiler, produces *byte-identical* machine code when compared to the original binary. It is how projects
reconstruct the original source code of a game like GoldenEye 007. Success is an exact instruction-level match, 
scored automatically. Lower is better; 0 is a match.

decomp.me hosts these problems as "scratches" and compiles submissions against the target. It
exposes a public JSON API with no auth.

## What this does about it

- **Every command is hard-bounded.** No invocation prints more than ~120 rows regardless of the
  size of the underlying data. `ctx.h` is grepped through `./dcm.py ctx <regex>` and never opened.
- **State lives on disk, not in the conversation.** `best.c`, `LOG.md` and `meta.json` survive a
  context reset; the transcript does not.
- **One declared hypothesis per compile, enforced.** `build` refuses to run without a `trial`
  armed in front of it, and records `prev -> new` against that hypothesis. `LOG.md` becomes an
  experiment ledger rather than optional prose.
- **Improvements are checkpointed, regressions are undone.** A better score snapshots `best.c` and
  commits to git automatically. A worse score restores `src.c` and halts.
- **The halt conditions are in the code, not the prompt.** An agent in a long transcript cannot be
  trusted to count its own streaks, so the harness counts them. Halts are sticky and only a human
  clears them, with a written acknowledgement.

## What a build looks like

```
SCORE 512 / max 900   best 512   [IMPROVED]  iter 3  1.8s
trial [types] widen the third argument to s32  (760 -> 512)

difference categories:
  >     4  extra (in ours, not in target)          ####
  r     3  register mismatch                       ###
  |     2  changed instruction                     ##
  s     1  stack offset mismatch                   #
  i     1  immediate mismatch                      #
  -- 11 divergent of 17 rows

first 11 of 11 divergences (target | ours):
 i 0:    addiu   sp,sp,-0x28             | i 0:    addiu   sp,sp,-0x38
 >                                       | > 4:    addiu   t7,a1,7
   4:    sw      ra,0x24(sp)             |   8:    sw      ra,0x24(sp)
 s 8:    sw      a0,0x28(sp)             | s c:    sw      a0,0x38(sp)
   ...

guardrails:
  total builds      3 / 25
  flat streak       0 / 8
  failed streak     0 / 2
  types trials      2 / 3
  halted         no
```

Roughly 25 lines per iteration. That is the agent's entire feedback channel.

## Quickstart

```bash
git clone https://github.com/c8289/goldeneye-decomp-harness.git
cd goldeneye-decomp-harness
./dcm.py selftest                 # 51 offline checks, no network

SLUG=i8JOn                        # from https://decomp.me/scratch/i8JOn
mkdir -p work/$SLUG && cp dcm.py work/$SLUG && cd work/$SLUG
./dcm.py pull $SLUG               # -> meta.json, src.c, ctx.h, best.c, LOG.md, git baseline
./dcm.py family                   # has a sibling already matched this?
./dcm.py build                    # first build; usually fails on mips2c artifacts
./dcm.py target                   # read the target disassembly before writing any C
```

Then the loop, one hypothesis at a time:

```bash
./dcm.py hist                     # what class of problem is this?
./dcm.py diff -n 12               # first divergences, offline, free
./dcm.py trial --category types --expect "drops the two lbu" "widen arg3 to s32"
# edit src.c minimally
./dcm.py build
```

## Pointing an agent at this repo

Give it a scratch URL — but **do not paste a bare URL**. Paste this:

```
Read AGENT.md before doing anything, then solve
https://decomp.me/scratch/<SLUG> — do not fetch that URL yourself,
`./dcm.py pull` retrieves it.
```

The prohibition has to be in your message, not only in a file. An agent always reads your turn;
whether it reads a document before its first tool call is not something a repository can control.
If a browser MCP server is configured, disable it for this task.

## Commands

| Command | What it does |
|---|---|
| `pull <slug> [--force]` | Fetch a scratch → `meta.json`, `src.c`, `ctx.h`, `best.c`, `LOG.md`, git baseline. Accepts a full URL. |
| `trial <text> --category C --expect E` | Arm the one hypothesis the next build tests. Required before every build. |
| `categories` | List the hypothesis categories and their remaining budget. |
| `build [-n N] [--src]` | Compile `src.c` remotely, score it, print a bounded diff, advance every counter. |
| `diff [-n N] [--at ADDR] [--src]` | Re-render the last result offline. Free, no network. |
| `hist` | Difference-category histogram only. |
| `target [-n N]` | Print the target disassembly column only. |
| `ctx <regex> [-n N] [--block N]` | Grep `ctx.h`. The only sanctioned way to read it. |
| `family [--get SLUG]` | List related scratches with scores, or fetch a sibling's source. |
| `revert` | Restore `best.c` over `src.c` and clear the pending trial. |
| `resume --ack "<why>" [--category C]` | Human-only. Clear a sticky halt. History and the ledger survive. |
| `log "<text>"` | Append a free-text note to `LOG.md`. |
| `status` | Score, best, iteration, history, guardrail dashboard, recent trials, log tail. |
| `selftest` | 51 offline checks over the guardrail state machine, the diff parser and the CLI table. |

## The guardrails

All of these are enforced in `dcm.py`, not left to the agent's judgement. Every halt is written to
`meta.json`, and every later `build` or `trial` refuses until a human runs `resume`. Halting
restores `src.c` from `best.c`, so the workspace is always left in its best known state.

| Trigger | Limit | On halt |
|---|---|---|
| Consecutive builds with no improvement to `best_score` | 8 | restore `src.c` from `best.c` |
| Consecutive build failures from the agent's own edits | 2 | restore, and keep `fail_iterN.c` |
| Trials in a single hypothesis category | 3 | refused at `trial` time, before the compile |
| Any regression (`score > best_score`) | immediate | restore, and keep `regress_iterN.c` |
| Total builds | 25 | restore; `resume` grants 10 more |
| `score == 0` | immediate | **no** restore — saving or forking is the human's call |

`resume --ack` requires a sentence of justification, records it in `meta.json`, and clears *only*
the halt. Iteration count, score history, category counts and the trial ledger all survive, so an
agent cannot launder a streak by resuming.

## Files

`dcm.py` and the two markdown files are the whole project. Everything a working directory contains
is generated and gitignored:

| File | What it is |
|---|---|
| `meta.json` | Scratch settings, best score, iteration, history, guardrail state, trial ledger |
| `src.c` | The current attempt — the only file the agent edits |
| `best.c` | Automatic snapshot of the best-scoring attempt |
| `ctx.h` | The scratch context. 100k–500k chars. Never opened directly |
| `target.txt` | Target disassembly column, rewritten by any build that returns a diff |
| `last.json` | Last successful compile response; backs offline `diff` and `hist` |
| `lastfail.json` | Last failed compile response |
| `fail_iterN.c` | The source that caused a halting build failure, kept for inspection |
| `regress_iterN.c` | The source that caused a regression, kept for inspection |
| `sib_<slug>.c` | A sibling scratch's source, from `family --get` |
| `LOG.md` | The experiment ledger: hypothesis, expectation, result, verdict |

## Design notes

**The tripwire moved from the prompt into the code.** A previous version of this repo described the halt conditions in the
manual and asked the agent to honour them. It did not work reliably — self-monitoring is exactly
the capability that degrades as a transcript grows. This repo now counts streaks in `meta.json` and
refuses to compile, which turns a soft instruction into an invariant.

**Hypotheses are declared before the compile, not narrated after it.** `trial --expect` forces a
falsifiable prediction on the record before the evidence arrives, and the category budget makes
"three different type changes in a row" a mechanical stop rather than a judgement call.

**Bounded output is the whole design constraint.** Every rendering path takes a limit and clamps it
against a module-level ceiling, because the failure being defended against is not a crash — it is a
tool result that succeeds and costs the run.

**The guardrail logic is pure.** `check_trial`, `record_trial`, `apply_build_result` and
`apply_resume` do no I/O; they take a `meta` dict and move numbers. That is what makes `selftest`
possible offline, and it is why the state machine has fixtures for eight flat builds and a
four-way category refusal without touching the network. The diff parser is covered the same way,
since it is the layer most likely to break when decomp.me changes its response shape.

## Testing

```bash
./dcm.py selftest        # exit 0 on success, 1 on any failure
```

51 checks, no network, no fixtures on disk. Covers the halt state machine (streaks, resets,
regression handling, sticky halts, resume semantics), slug parsing, the diff parsing layer
(marker classification, histograms, render bounds, source annotations), and the subcommand table.

The same command runs in CI on every push and pull request, across Python 3.9, 3.11 and 3.13 —
see [.github/workflows/selftest.yml](.github/workflows/selftest.yml). There is nothing to install,
so the workflow is `checkout`, `setup-python`, `./dcm.py selftest`.

## Requirements and etiquette

Python 3.6 or newer, standard library only — no `pip install`. Nothing in `dcm.py` uses syntax or
APIs introduced after 3.6; CI covers 3.9 upward, which is the oldest interpreter GitHub's current
runner images still provide. `git` is optional but recommended; without it you still get `best.c`,
and the harness says so once rather than failing silently.

This project is not affiliated with decomp.me. It uses the public JSON API, which requires no
account. Compiling is stateless and does not mutate a scratch. `PUT /scratch/{slug}` (save) and
`POST /scratch/{slug}/fork` create or change content and are deliberately **not** implemented here —
those belong to a human with an account, not to an agent.

## License

MIT. See [LICENSE](LICENSE).
