# decomp.me matching — operating manual (GoldenEye N64)

**Audience: an autonomous coding agent with shell access. Read Part 0 and Part 1 before doing
anything else.**

Assignment: `SLUG=<slug>`, from `https://decomp.me/scratch/<slug>`.

**Substitute the slug you were actually given.** Nothing here is specific to any one scratch; the
protocol generalises to any GoldenEye scratch.

`README.md` is the human-facing overview of this repo. This document is the protocol you follow.

---

# PART 0 — PRIME DIRECTIVE

**decomp.me is an HTTP compile service. It is not a web app you operate.**

Every part of the match loop is available over a public JSON API that needs no login, no cookie and
no CSRF token. The entire workflow is `./dcm.py` plus local files. **You never speak HTTP
yourself.**

## Absolutely forbidden

1. Fetching any decomp.me URL by any means other than `dcm.py`. curl, curl.exe, wget,
   Invoke-WebRequest, a browser tool, a Python or Node snippet you wrote — all the same mistake
   with different spelling. The rest of this list is about browser tools specifically; this item
   covers everything else.
2. Opening a decomp.me scratch page in a browser tool to do work.
3. Typing into the Monaco editor. It virtualizes lines, auto-closes brackets and fires
   autocomplete. Text you type will be silently corrupted and you will waste turns debugging syntax
   errors you created.
4. Clicking the Compile button.
5. Reading the diff pane out of an accessibility snapshot or a screenshot.
6. Calling any browser snapshot tool on a scratch page more than once, ever. The page is a Monaco
   instance plus a per-token-span diff table; one snapshot can eat a large fraction of your context
   window, and every ref goes stale on the next click. This is the single most common way this task
   fails.

If a browser MCP server is configured, **do not use it for this task.** Ideally remove it from the
profile. If you find yourself reaching for it, that is a symptom that you have lost the thread — go
to Part 2 instead.

## No curl flag makes it safe

`--max-time` bounds wall-clock, not bytes. `--fail` and `-sS` bound error output, not the body.
`-L` just makes sure you arrive at the payload. An agent adding careful-looking flags to that
command is bounding the wrong axis: the request takes under two seconds and succeeds cleanly, and
that is precisely the problem. **The response is the damage.**

The hazard is bytes reaching your transcript, not the word `curl`. So if you ever have a real
reason to touch decomp.me outside the harness — you almost certainly do not — the body goes to a
file and never to stdout:

    curl -sS -o raw.json https://www.decomp.me/api/scratch/$SLUG
    wc -c raw.json          # check the size before you look at the contents

then read it with a bounded tool. The same rule applies to wget, Invoke-WebRequest,
`requests.get`, and anything else you improvise. `dcm.py` is the only HTTP client in this project:
it writes that field straight to `ctx.h` on disk and never lets it reach the transcript. If you
want something from the API, there is a `dcm.py` command for it; if there isn't one, ask the human
rather than writing your own client.

## The only legitimate browser use

Reading a linked issue, a decomp wiki page, or a project's docs. Never the scratch itself.

## Actions that require the human's explicit approval

Compiling is stateless and free — it never modifies the scratch, so no approval is needed and you
may do it as often as the guardrails allow. These, by contrast, create or mutate content and
require the human to say yes in chat first:

`PUT /scratch/{slug}` (save), `POST /scratch/{slug}/fork`, any change to `compiler`,
`compiler_flags` or `diff_label` in `meta.json`, and any file download beyond what the harness
writes. None of the mutating endpoints are implemented in `dcm.py`, and that is deliberate.

## Non-negotiables

- The context field on a GE scratch is 100k–500k characters — **commonly past 400,000 characters
  and 100k tokens.** The harness writes it to `ctx.h`. **Never read it, never `cat` it, never let
  it into a tool result.** Use `./dcm.py ctx <regex>` — that is what it is for.
- One hypothesis per compile. This is enforced: `build` refuses to run without an armed `trial`.
- Never build a change on top of an unvalidated change.
- Score: **lower is better, 0 is a match.** It is not capped by `max_score`.
- `current_score == max_score` almost always means **your code did not compile**, not that it
  compiled badly.
- The compiler is `ido5.3`. **You may never change it.** Flags are `-Olimit 2000 -mips2 -O2`; see
  Part 7 before touching them.

---

# PART 1 — SETUP (do this first, every time)

## 1.1 Bootstrap

```bash
SLUG=<slug>                       # from https://decomp.me/scratch/<SLUG>
mkdir -p work/$SLUG
cp dcm.py work/$SLUG              # one copy per working directory
cd work/$SLUG
chmod +x dcm.py
./dcm.py pull $SLUG
./dcm.py family                   # is a sibling already matched?
./dcm.py build                    # first build; usually fails, that is expected
./dcm.py target                   # READ THE TARGET before writing any C
```

`pull` writes `meta.json`, `src.c`, `ctx.h`, `best.c` and `LOG.md`, and makes a git baseline.
`build` compiles remotely and prints a bounded report. Nothing prints more than ~40 lines.

The very first `build` is the one exception to the hypothesis rule: with `iteration == 0` the
harness arms a `baseline` trial for you. Every build after that needs a declared hypothesis.

## 1.2 The harness

`dcm.py` lives in the repo root. Copy it into your working directory and make it executable. Do not
modify it. Do not paste it into another file. There is one copy and this is it.

```
./dcm.py pull <slug> [--force]     fetch scratch -> meta.json, src.c, ctx.h, best.c
./dcm.py trial <text> --category C --expect E
                                   arm the ONE hypothesis the next build tests
./dcm.py categories                list categories and how much budget each has left
./dcm.py build [-n N] [--src]      compile src.c remotely, report score + divergences
./dcm.py diff  [-n N]              re-render last result offline (free, no network)
./dcm.py diff --at ADDR            window the diff around a target address
./dcm.py diff --src                show target source-line annotations for divergences
./dcm.py hist                      difference-category histogram only
./dcm.py target [-n N]             print the TARGET disassembly column only
./dcm.py ctx <regex> [-n N]        grep ctx.h  (NEVER open ctx.h any other way)
./dcm.py ctx <regex> --block 40    print 40 lines from the first hit (struct defs)
./dcm.py family [--get SLUG]       list related scratches / fetch a sibling's source
./dcm.py revert                    restore best.c over src.c, clear the pending trial
./dcm.py resume --ack "<why>"      HUMAN ONLY - clear a halt. Not yours to run.
./dcm.py log "text"                append a free-text note to LOG.md
./dcm.py status                    score, best, iteration, guardrails, recent trials
./dcm.py selftest                  51 offline guardrail, parser and CLI checks
```

Talks to the public decomp.me JSON API so you never touch a browser.

**Every command is hard-bounded.** No single invocation prints more than ~120 rows, regardless of
how large the underlying data is. That ceiling is the main thing keeping the context window
survivable across a long solve, and it is why you use these commands instead of `cat`, `grep`, or a
browser tool.

Files in the working directory — all generated, none of them source:

| file | what it is |
|---|---|
| `meta.json` | scratch settings, best score, iteration, history, guardrail state, trial ledger |
| `src.c` | your current attempt — the only file you edit |
| `best.c` | automatic snapshot of the best-scoring attempt so far |
| `ctx.h` | the scratch context. Enormous. Never open it directly |
| `target.txt` | the target disassembly column, rewritten by any build that returns a diff |
| `last.json` | last successful compile response, used by `diff` and `hist` offline |
| `lastfail.json` | last failed compile response |
| `fail_iterN.c` | the source that caused a halting build failure, kept for inspection |
| `regress_iterN.c` | the source that caused a regression, kept for inspection |
| `sib_<slug>.c` | a sibling's source, from `family --get` |
| `LOG.md` | the experiment ledger: hypothesis, expectation, result, verdict |

`best.c` and `LOG.md` are your memory. They survive a context reset; the conversation does not.

## 1.3 The trial/build cycle

Every compile after the first must be preceded by exactly one declared hypothesis:

```bash
./dcm.py trial --category signature \
  --expect "adds the missing a3 setup before the jal" \
  "the callee takes four args, not three"
# ---- now edit src.c, minimally ----
./dcm.py build
```

`trial` refuses if the category is exhausted, if the harness is halted, or if you cannot state the
hypothesis and its expected effect in a sentence each. `build` consumes the armed trial, records
`prev -> new` against it in `LOG.md` and `meta.json`, and charges the attempt to its category.

`--expect` is not paperwork. It forces a falsifiable prediction onto the record *before* the
evidence arrives, which is the only reliable defence against deciding after the fact that a flat
result was "informative".

## 1.4 What a build looks like

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

Roughly 25 lines per iteration. That is your entire feedback channel. Do not ask for more unless a
specific hypothesis needs it, and prefer `./dcm.py diff --at 1c` (offline, free) over recompiling.

---

# PART 2 — THE STUCK TRIPWIRE

Agents that fail this task do not fail because they lack ideas; they fail because they generate
ideas indefinitely without noticing that none of them worked. **The halt conditions below are
enforced by `dcm.py`, not left to your judgement.** You cannot decide you are the exception.

## What the harness halts on

| Trigger | Limit | What happens |
|---|---|---|
| Builds with no improvement to `best_score` | 8 consecutive | halt, `src.c` restored from `best.c` |
| Build failures caused by your own edits | 2 consecutive | halt, restore, `fail_iterN.c` kept |
| Trials in one hypothesis category | 3 | the 4th is refused at `trial` time, then halt |
| Regression (`score > best_score`) | immediate | halt, restore, `regress_iterN.c` kept |
| Total builds | 25 | halt, restore — checkpoint here |
| `score == 0` | immediate | halt, **no** restore — you are done |

A halt is sticky. It is written to `meta.json`, and every subsequent `build` and `trial` refuses
until a human runs `resume`. Offline commands — `status`, `hist`, `diff`, `target`, `ctx` — keep
working, because you need them to write your report.

## Halt yourself, before the harness has to

These are not counted for you. Stop on your own if any of them is true:

- **You are about to run curl, wget, Invoke-WebRequest, or any HTTP client against decomp.me.**
  The command you want is a `./dcm.py` subcommand.
- **You are about to open a browser tool.**
- **You are about to read `ctx.h`, or dump `src.c` in full "just to get oriented".**
- **Any single tool result over ~2000 lines**, or any two consecutive tool results you cannot
  summarise in one sentence each.
- **Score ≥ `max_score`** and you have not checked `diff_label`.
- **You cannot state, in one sentence, what your last edit was testing.** If you cannot fill in
  `--expect`, you do not have a hypothesis.

## Halt procedure

The harness prints this when it stops you. Run it, then stop:

```bash
./dcm.py status
./dcm.py hist
./dcm.py diff -n 15
```

Then report to the human: best score, the category histogram, the first divergences, the
hypotheses already ruled out, and **one specific question**. If your runtime has a question tool
(`ask_followup_question` in Cline/Roo, or the equivalent), use it; otherwise end your turn with the
question. **Do not continue.**

An honest 512/900 with a clean diff and a ruled-out list is worth far more than forty turns of
thrashing that ends at 512 anyway with a poisoned context.

## Resuming is the human's move, not yours

```bash
./dcm.py resume --ack "<a sentence on why continuing is the right call>"
./dcm.py resume --ack "<...>" --category loop     # for a category halt
```

`resume` clears **only** the halt. Iteration count, score history, category counts and the trial
ledger all survive, and the acknowledgement is recorded in `meta.json`. You cannot launder a streak
by resuming, and you should not be running this command at all — propose it, and let the human
decide.

## Checkpointing

The harness prints a checkpoint advisory at 12 builds and halts at 25. If you are still making real
progress, start a fresh task and carry over only: slug, best score, the histogram, the top three
divergences, and `LOG.md`. Do not carry over source, context or old diffs. `best.c` and `LOG.md`
are on disk; that is your memory, not the conversation.

---

# PART 3 — THE API, VERIFIED

Base: `https://decomp.me/api`. No auth for anything below. `www.decomp.me` also works.

**This table documents what `dcm.py` already does on your behalf. It is not a list of commands for
you to run.** It exists so you can reason about the harness's behaviour and failure modes, not so
you can reimplement it.

| Method | Path | Notes |
|---|---|---|
| GET | `/scratch/{slug}` | includes `context` — **100k–500k chars. Harness only. Calling this directly ends your run.** |
| POST | `/scratch/{slug}/compile` | **the workhorse**; ~1.8 s; no auth, no CSRF; does not mutate the scratch |
| GET | `/scratch/{slug}/family` | related scratches (forks, siblings) with scores |
| GET | `/scratch/{slug}/export` | zip of the same 400 KB payload. Harness only |
| GET | `/scratch?page_size=N` | paginated `{next, previous, results}` |
| GET | `/preset/{id}` | compiler + flags a preset implies (GE is **33**) |
| GET | `/user` | current identity |
| OPTIONS | any | DRF field schema |
| PUT | `/scratch/{slug}` | save — **owner only, not implemented, human's call** |
| POST | `/scratch/{slug}/fork` | fork — **creates content, not implemented, human's call** |

## Compile request

```json
{
  "compiler": "ido5.3",
  "compiler_flags": "-Olimit 2000 -mips2 -O2",
  "source_code": "...",
  "context": "...",
  "diff_label": "<target function name>",
  "libraries": [],
  "diff_flags": []
}
```

`compiler` and `source_code` are required. `preset` is optional and changes nothing when `compiler`
and `compiler_flags` are both supplied, so the harness omits it. `context` may be omitted, but then
the score is meaningless — every type in the function will be undefined.

## Compile response

```json
{
  "success": true,
  "compiler_output": "",
  "diff_output": {
    "arch_str": "mips",
    "header": {"base": [], "current": []},
    "current_score": 512,
    "max_score": 900,
    "rows": []
  }
}
```

Note that `diff_output` is normally present **even when `success` is false** — the `base` column
still holds the full target disassembly. That is why the harness rewrites `target.txt` from any
response that carries a diff, failed build or not, and why you can read the target before you have
ever compiled successfully. It is written under a presence check rather than assumed, so a response
without a diff leaves the previous `target.txt` in place instead of truncating it.

## Failure modes

| Symptom | Meaning |
|---|---|
| HTTP 400, `{"compiler":["Unknown compiler: x"],"kind":"ValidationError"}` | bad compiler name; no compile ran |
| `success: false`, `current_score == max_score` | did not compile; read `compiler_output` |
| `success: true`, score ≥ max_score | `diff_label` did not resolve — you renamed the function |
| HTTP 429 / 502 / 504 | transient; the harness backs off and retries |

Compile is not obviously rate-limited, but do not hammer it. One build per hypothesis is the
discipline anyway, and the harness will not let you do otherwise.

---

# PART 4 — READING THE DIFF

## Row structure

Each row has `base` (target) and `current` (yours), each shaped
`{text:[{text, format?, group?, key?}], mnemonic, line, branch?, src?, src_line?, src_comment?}`.
Concatenate the `text` chunks to get the display line.

## Markers — the important part

The `format` values include `register`, `stack`, `immediate` and `rotation`, which are
**highlighting categories, not difference flags.** Only `diff_add`, `diff_remove` and `diff_change`
are true diff formats, and they cover fewer than a third of real differences. Detect divergence
from the **leading marker character of the `current` column** — this is verified behaviour, not a
guess. A row whose `current` side is empty while `base` holds an instruction is a deletion by
definition, and the harness reports it as `<`.

| Marker | Meaning | Usually caused by |
|---|---|---|
| `<` | in target, absent from ours | missing operation, dropped temporary, different call form |
| `>` | in ours, absent from target | extra spill, extra load, unnecessary temporary, a callee-saved register we should not need |
| `\|` | instruction changed | wrong operation — signedness, width, wrong opcode family |
| `r` | register mismatch only | allocation order, local lifetime, declaration order |
| `s` | stack offset mismatch only | frame layout — local count, order, alignment, padding |
| `i` | immediate mismatch | wrong constant, wrong struct offset, wrong field |
| (space) | identical | — |

## Reading the histogram

The histogram tells you what class of problem you have before you look at a single instruction.

Dominated by `r` with almost nothing else means register allocation. Reorder declarations, change
local lifetimes, hoist or sink temporaries — do not touch semantics.

Dominated by `s` means stack frame layout: wrong number, size, order or alignment of locals. Look
at the frame-size instruction `addiu sp,sp,-N` first. If that differs, nothing downstream lines up
and every other divergence is noise.

Dominated by `i` means constants and struct offsets, almost always the wrong field or the wrong
type width. Grep the context for the struct instead of guessing.

Many `>` and `<` in balanced pairs means instruction scheduling or a moved operation. Many `>`
alone means you are generating extra work — a redundant load, an unnecessary spill, a missing
common subexpression, or a local the target does not have.

A handful of `|` near the top with a clean tail means one wrong operation early. Fix that one; the
rest is downstream noise.

## Diagnose from the first divergence

Compare in this order and stop at the first mismatch: frame size (`addiu sp,sp,-N`), then which
registers the prologue saves and in what order, then branch structure and count, then call sites
and their argument setup, then load/store counts, then constants and offsets, then the return path
and epilogue.

Late-function divergence is usually downstream of a single earlier cause. Chasing the last
difference is the classic way to burn twenty iterations.

---

# PART 5 — HYPOTHESIS DISCIPLINE

## The loop

```bash
./dcm.py hist                 # what class of problem?
./dcm.py diff -n 12           # first divergences, offline, free
# ---- form exactly ONE hypothesis ----
./dcm.py trial --category types --expect "the two lbu become lb" "arg3 is signed, not unsigned"
# ---- edit src.c minimally ----
./dcm.py build                # ~2s; consumes the trial, logs prev -> new
```

You do not need to `revert` after a regression and you do not need to `log` the result — `build`
does both. A regression restores `best.c` over `src.c` automatically and halts. Use
`./dcm.py log "text"` only for observations that are not the result of a trial.

`best.c` and the git history are your safety net, and the harness updates both on every
improvement. You can always return to your best state, which means you are free to try aggressive
ideas — but only one at a time, and only three per category.

## Categories

`./dcm.py categories` prints these with remaining budget. Pick the one that actually describes your
edit; the budget is what stops you from trying five variations of the same idea.

**`signature` — argument count and register class of the callee.** On GE this is the highest-yield
check by far, because mips2c guesses call signatures and is frequently wrong. See Part 6.

**`types` — types and signedness.** `s32` vs `u32` vs `s16` vs `u8` changes sign/zero extension and
can add or remove whole instructions. On MIPS, `lb`/`lbu`/`lh`/`lhu` mismatches are pure type
errors. High yield, low risk.

**`order` — declaration order of locals.** Directly drives both stack layout and register
allocation on IDO. If the histogram is `s`- or `r`-dominated, permute this first.

**`lifetime` — temporary lifetime.** Introducing or removing an explicit local changes allocation:
`x = a->b; use(x); use(x);` and `use(a->b); use(a->b);` produce different code.

**`grouping` — expression grouping and evaluation order.** `(a + b) + c` versus `a + (b + c)`,
argument evaluation order, operand order in a comparison.

**`condition` — condition form.** `if (!x)` versus `if (x == 0)`, `if (a && b)` versus nested `if`,
inverted branches, early return versus single exit.

**`loop` — loop form.** `for` versus `while` versus `do/while`, hand-hoisted loop invariants,
pointer increment versus index.

**`struct` — struct access form.** `p->a.b[i]` versus a cached intermediate pointer. Wrong struct
definitions in the context produce `i` divergences; grep `ctx.h` for the struct rather than
guessing at the offset.

**`cast` — casts and pointer punning.** Where the cast sits changes the load width.
`*(s32 *)((u8 *)p + 0x10)` and `p->field` can differ.

**`volatile`.** Forces a spill or prevents reordering. Occasionally the only way to match; a
legitimate but last-resort tool, and the category name puts that on the record.

**`inline` — inlining and call form.** A `static` helper that the compiler inlines, or a call the
compiler must not inline. Check whether the target has a real `jal` or an inlined body.

**`float` — float handling.** `f32` versus `f64` intermediates, and on IDO whether a constant lives
in the literal pool. Watch for `sdc1`/`ldc1` pairs around `$f20`+ — those indicate the target saves
callee-saved FPU registers, which means it really uses doubles, not floats.

**`layout`, `register`** — stack frame size and spill placement, register allocation pressure, when
the edit is aimed squarely at one of those rather than at the C.

**`build`** — fixing a compile error. Not a codegen hypothesis, so it is uncounted; the two-failure
limit bounds it instead.

**`other`** — none of the above. Say why in the text.

---

# PART 6 — GOLDENEYE / PERFECT DARK SPECIFICS

These scratches share a signature shape, and knowing it saves most of the iterations.

## The published source usually does not compile

GE scratches are bulk-imported mips2c output. A published `score == max_score` means the source has
never compiled. Expect artifacts like a bare `?` where a return type belongs, `sp` pseudo-locals,
`temp_t6` chains, and arithmetic on `void *` — which is a GCC extension that **IDO rejects**. Cast
to `u8 *` before adding a byte offset. Your first job is a clean build, not a good score; use the
`build` category for those trials.

## The context is a whole-game header dump

Commonly past 400,000 characters, mostly typedefs, struct definitions and prototypes for other
functions. It is already correct for everything it contains. Two consequences: never rewrite it
casually, and always check whether a symbol is in it before declaring your own:

```bash
./dcm.py ctx 'someCalleeName'
./dcm.py ctx 'typedef struct.*ObjHeader' --block 40
```

If the grep comes back empty, the callee is genuinely undeclared and **you must add an `extern`
prototype at the top of `src.c`** — that is expected and normal, not a context edit.

## Read the o32 calling convention off the target

This is the single most useful skill for GE/PD, because it recovers the true signature that mips2c
guessed wrong.

Integer arguments go in `a0`–`a3`; the fifth and later arguments go on the stack at `0x10(sp)`,
`0x14(sp)`, and so on. The 16 bytes at `0x0(sp)`–`0xc(sp)` are the outgoing argument save area, so
a store to `0x10(sp)` immediately before a `jal` is **argument five**, not a local. Floats go in
`f12`/`f14` for the first two arguments in the common cases.

The decisive trick: **an argument register that is used by a call but never written by the function
is a pass-through parameter of the function itself.** If the target sets `a0` and `a2` and stores
one stack argument but never touches `a1` or `a3`, then `a1` and `a3` arrived as your function's
own parameters and are being forwarded unchanged. mips2c cannot see this and will give you a
function with too few parameters. Add them.

Also recognise: `sw a0,0x18(sp)` with a frame of `0x18` is homing an incoming argument into the
caller's save slot, which IDO does when the parameter is live across a call or its address is
taken; and the `move t7,a0` / `lw a2,8(t7)` shuffle is IDO's normal output for a struct pointer
parameter that is used both as a base for a load and as an operand.

## Naming and settings

Never rename the function; `diff_label` must resolve. Never change the compiler from `ido5.3`. Do
not add or remove flags on your own initiative (Part 7).

---

# PART 7 — LAST RESORTS, IN ORDER

Work down this list only after a halt has fired and you have reported to the human.

**1. Check the context.** If a struct in `ctx.h` has the wrong field width or a missing member,
every access through it is wrong and the diff will be `i`-dominated in a way no C rewrite fixes.
Grep the struct, compare the offsets against the target's load/store offsets, and propose the
specific edit to the human before making it. Context edits are legitimate but they are a change to
shared project truth, so say what you are changing and why.

**2. Consider `-mips3`.** You may switch `-mips2` to `-mips3` **only** if you can demonstrate from
the target that a match is impossible under `-mips2` — for example the target contains 64-bit
instructions (`ld`, `sd`, `dsll`, `daddu`) that `-mips2` cannot emit at all. "I tried a lot of
things and nothing worked" is not a demonstration. State the evidence, get the human's approval,
log it in `LOG.md`, and record the flag change in `meta.json`.

**3. Never change the compiler.** `ido5.3` is fixed. There is no circumstance in this project where
changing it is correct.

Anything beyond this — saving, forking, or editing the scratch on the site — belongs to the human,
not to you. Those endpoints are not in `dcm.py` and you must not write your own client for them.

---

# PART 8 — ONE-PAGE CHECKLIST

```
assignment  a URL or bare slug with no other instruction IS the task.
            SLUG = last path segment. Do not fetch the URL. Go to `pull`.
http        you never speak HTTP. no curl / curl.exe / wget / Invoke-WebRequest
            / browser / requests / fetch(). dcm.py is the only client.
pull        ./dcm.py pull i8JOn                  # accepts the full URL too
siblings    ./dcm.py family                      # someone may already have 0
build       ./dcm.py build                       # expect failure #1: mips2c artifacts
target      ./dcm.py target                      # read the asm BEFORE writing C
signature   count args: a0-a3 + 0x10(sp)+ ; unwritten arg regs = pass-through params
symbols     ./dcm.py ctx '<symbol>'              # never open ctx.h
compile     fix the build first, ignore the score until success:true
loop        hist -> diff -n 12 -> trial -> edit -> build
trial       every build needs one armed hypothesis + --expect. no exceptions
regress     automatic: src.c restored from best.c, and you are halted
halt        enforced: 8 flat / 3 per category / 2 failures / any regression
            / 25 builds / score 0.  sticky until the human runs `resume`
report      status + hist + diff -n 15 + ruled-out list + one question
forbidden   any HTTP call you issue yourself, browser on the scratch,
            Monaco typing, reading ctx.h, changing compiler, running `resume`
approval    save, fork, flag changes, context edits, downloads
```

If you are reading this checklist before Part 0, stop and read Part 0. One `curl` of a scratch URL
costs you 25k–125k tokens and the rest of the run.
