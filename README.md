## What this is

Matching decompilation is the practice of writing C source that, when fed to a
specific period compiler, produces *byte-identical* machine code to a shipped
binary. It is how projects reconstruct the original source of a game like
GoldenEye 007. Success is not "the code works" — it is an exact
instruction-level match, scored automatically. Lower is better; 0 is a match.

decomp.me is a public web service that hosts these problems ("scratches") and
compiles submissions against the target. It exposes a JSON API with no auth.

This repo is an **operating protocol and tool harness that lets an autonomous
coding agent solve these scratches.** The hard part is not the C. It
is that the task is long, iterative, and full of ways for an agent to destroy
itself: a single context file here runs past 400,000 characters, and one careless
tool call can consume the entire context window. So the harness hard-bounds every
output, keeps state on disk rather than in the conversation, checkpoints
improvements to git, auto-reverts regressions, and the protocol below defines
explicit halt conditions that stop the agent from thrashing indefinitely.

Two files matter: `README.md` (this document — the agent reads it first) and
`dcm.py` (the CLI it drives). Everything else in a working directory is generated.

**Usage:** point an agent at a working folder containing both files and give it a
scratch URL.

---

# decomp.me matching — operating manual (GoldenEye N64)

**Audience: an autonomous coding agent with shell access. Read Part 0 and Part 1 before doing anything else.**

Assignment: `SLUG=<slug>`, from `https://decomp.me/scratch/<slug>`.

This document uses `jgiaZ` throughout as a running example, including the fully
worked solve in Part 7. **Substitute the slug you were actually given.** Nothing
here is specific to `jgiaZ` except the worked example itself; the protocol
generalizes to any GoldenEye scratch.

---

# PART 0 — PRIME DIRECTIVE

**decomp.me is an HTTP compile service. It is not a web app you operate.**

Every part of the match loop is available over a public JSON API that needs no login, no cookie, and no CSRF token. The entire workflow is curl plus local files.

## Absolutely forbidden

1. Opening a decomp.me scratch page in a browser tool to do work.
2. Typing into the Monaco editor. It virtualizes lines, auto-closes brackets, and fires autocomplete. Text you type will be silently corrupted and you will waste turns debugging syntax errors you created.
3. Clicking the Compile button.
4. Reading the diff pane out of an accessibility snapshot or a screenshot.
5. Calling any browser snapshot tool on a scratch page more than once, ever. The page is a Monaco instance plus a per-token-span diff table; one snapshot can eat a large fraction of your context window, and every ref goes stale on the next click. This is the single most common way this task fails.

If a browser MCP server is configured, **do not use it for this task.** Ideally remove it from the profile. If you find yourself reaching for it, that is a symptom that you have lost the thread — go to Part 2 instead.

## The only legitimate browser use

Reading a linked issue, a decomp wiki page, or a project's docs. Never the scratch itself.

## Actions that require the human's explicit approval

Compiling is stateless and free — it never modifies the scratch, so no approval is needed and you may do it as often as your discipline allows. These, by contrast, create or mutate content and require the human to say yes in chat first:

`PUT /scratch/{slug}` (save), `POST /scratch/{slug}/fork`, any change to `compiler`, `compiler_flags`, or `diff_label` in `meta.json`, and any file download beyond what the harness writes.

## Non-negotiables

- The context field on a GE scratch is 100k–500k characters. On `jgiaZ` it is **417,462 characters / 15,421 lines, roughly 105k tokens.** The harness writes it to `ctx.h`. **Never read it, never `cat` it, never let it into a tool result.** Use `./dcm.py ctx <regex>` — that is what it is for.
- One hypothesis per compile.
- Never build a change on top of an unvalidated change.
- Score: **lower is better, 0 is a match.** It is not capped by `max_score`.
- `current_score == max_score` almost always means **your code did not compile**, not that it compiled badly.
- The compiler is `ido5.3`. **You may never change it.** Flags are `-Olimit 2000 -mips2 -O2`; see Part 8 before touching them.

---

# PART 1 — SETUP (do this first, every time)

## 1.1 Bootstrap

```bash
SLUG=<slug>                       # from https://decomp.me/scratch/<SLUG>
mkdir -p work/$SLUG && cd work/$SLUG
# save dcm.py here (Part 1.2)
chmod +x dcm.py
./dcm.py pull $SLUG
./dcm.py family              # is a sibling already matched?
./dcm.py build               # first build; usually fails, that is expected
./dcm.py target              # READ THE TARGET before writing any C
```

`pull` writes `meta.json`, `src.c`, `ctx.h`, `best.c`, `LOG.md` and makes a git baseline. `build` compiles remotely and prints a bounded report. Nothing prints more than ~40 lines.

## 1.2 The harness

`dcm.py` lives in the repo root. Copy it into your working directory and make it executable:

```bash
chmod +x dcm.py
```

Do not modify it. Do not paste it into another file. There is one copy and this is it.

```
./dcm.py pull <slug> [--force]  fetch scratch -> meta.json, src.c, ctx.h, best.c
./dcm.py build [-n N] [--src]   compile src.c remotely, report score + divergences
./dcm.py diff  [-n N]           re-render last result offline (free, no network)
./dcm.py diff --at ADDR         window the diff around a target address
./dcm.py diff --src             show target source-line annotations for divergences
./dcm.py hist                   difference-category histogram only
./dcm.py target [-n N]          print the TARGET disassembly column only
./dcm.py ctx <regex> [-n N]     grep ctx.h  (NEVER open ctx.h any other way)
./dcm.py ctx <regex> --block 40 print 40 lines from the first hit (struct defs)
./dcm.py family [--get SLUG]    list related scratches / fetch a sibling's source
./dcm.py revert                 restore best.c over src.c
./dcm.py log "text"             append a line to LOG.md
./dcm.py status                 score, best, iteration, score history, recent log
```

Talks to the public decomp.me JSON API so the agent never touches a browser.

**Every command is hard-bounded.** No single invocation prints more than ~120 rows, regardless of how large the underlying data is. That ceiling is the main thing keeping the context window survivable across a long solve, and it is why you use these commands instead of `cat`, `grep`, or a browser tool.

Files the harness writes into the working directory — all generated, none of them source:

| file | what it is |
|---|---|
| `meta.json` | scratch settings, best score, iteration count, score history |
| `src.c` | your current attempt — the only file you edit |
| `best.c` | automatic snapshot of the best-scoring attempt so far |
| `ctx.h` | the scratch context. Enormous. Never open it directly |
| `target.txt` | the target disassembly column, written on each build |
| `last.json` | last successful compile response, used by `diff` and `hist` offline |
| `lastfail.json` | last failed compile response |
| `LOG.md` | your written record of hypotheses tried and ruled out |

`best.c` and `LOG.md` are your memory. They survive a context reset; the conversation does not.

## 1.3 What a build looks like

```
SCORE 846 / max 1300   best 846   [IMPROVED]  iter 3  1.8s

difference categories:
  >     4  extra (in ours, not in target)         ####
  r     3  register mismatch                      ###
  |     2  changed instruction                    ##
  s     1  stack offset mismatch                  #
  i     1  immediate mismatch                     #
  -- 11 divergent of 17 rows

first 11 of 11 divergences (target | ours):
 i 0:    addiu   sp,sp,-0x20             | i 0:    addiu   sp,sp,-0x30
 >                                       | > 4:    addiu   t7,a1,7
   4:    sw      ra,0x1c(sp)             |   8:    sw      ra,0x1c(sp)
 s 8:    sw      a0,0x20(sp)             | s c:    sw      a0,0x30(sp)
   ...
```

Roughly 25 lines per iteration. That is your entire feedback channel. Do not ask for more unless a specific hypothesis needs it, and prefer `./dcm.py diff --at 1c` (offline, free) over recompiling.

---

# PART 2 — THE STUCK TRIPWIRE

This is mandatory and it overrides your judgement about whether you are making progress. Agents that fail this task do not fail because they lack ideas; they fail because they generate ideas indefinitely without noticing that none of them worked.

## Halt immediately if any of these fire

- **8 consecutive builds** with no improvement to `best_score`.
- **The same category of hypothesis tried three times** (three different type changes, three different reorderings — count the category, not the edit).
- **Two consecutive build failures caused by your own edit.**
- **Any single tool result over ~2000 lines**, or any two consecutive tool results you cannot summarize in one sentence each.
- **Score ≥ max_score** and you have not checked `diff_label`.
- **You are about to open a browser tool.**
- **You are about to read `ctx.h` or dump `src.c` in full "just to get oriented."**
- **You cannot state, in one sentence, what your last edit was testing.**

## Halt procedure

```bash
./dcm.py revert
./dcm.py status
./dcm.py hist
./dcm.py diff -n 15
```

Then report: best score, the category histogram, the first divergences, the hypotheses already ruled out, and one specific question. Use `ask_followup_question`. **Do not continue.**

An honest 846/1300 with a clean diff and a ruled-out list is worth far more than forty turns of thrashing that ends at 846 anyway with a poisoned context.

## Checkpointing

If you pass 25 iterations and are still making real progress, use `new_task` and carry over only: slug, best score, the histogram, the top three divergences, and `LOG.md`. Do not carry over source, context, or old diffs. `best.c` and `LOG.md` are on disk; that is your memory, not the conversation.

---

# PART 3 — THE API, VERIFIED

Base: `https://decomp.me/api`. No auth for anything below. `www.decomp.me` also works.

| Method | Path | Notes |
|---|---|---|
| GET | `/scratch/{slug}` | full scratch incl. `source_code` and `context` |
| POST | `/scratch/{slug}/compile` | **the workhorse**; ~1.8 s; no auth, no CSRF; does not mutate the scratch |
| GET | `/scratch/{slug}/family` | related scratches (forks, siblings) with scores |
| GET | `/scratch/{slug}/export` | zip |
| GET | `/scratch?page_size=N` | paginated `{next, previous, results}` |
| GET | `/preset/{id}` | compiler + flags a preset implies (GE/PD is **33**) |
| GET | `/user` | current identity |
| OPTIONS | any | DRF field schema |
| PUT | `/scratch/{slug}` | save — **owner only, requires explicit user approval** |
| POST | `/scratch/{slug}/fork` | fork — **creates content, requires explicit user approval** |

## Compile request

```json
{
  "compiler": "ido5.3",
  "compiler_flags": "-Olimit 2000 -mips2 -O2",
  "source_code": "...",
  "context": "...",
  "diff_label": "sub_GAME_7F073038",
  "libraries": [],
  "diff_flags": []
}
```

`compiler` and `source_code` are required. `preset` is optional and changes nothing when `compiler` and `compiler_flags` are both supplied, so the harness omits it. `context` may be omitted, but then the score is meaningless — every type in the function will be undefined.

## Compile response

```json
{
  "success": true,
  "compiler_output": "",
  "diff_output": {
    "arch_str": "mips",
    "header": {"base": [], "current": []},
    "current_score": 846,
    "max_score": 1300,
    "rows": []
  }
}
```

Note that `diff_output` is present **even when `success` is false** — the `base` column still holds the full target disassembly. That is why the harness writes `target.txt` on every build, failed or not, and why you can read the target before you have ever compiled successfully.

## Failure modes

| Symptom | Meaning |
|---|---|
| HTTP 400, `{"compiler":["Unknown compiler: x"],"kind":"ValidationError"}` | bad compiler name; no compile ran |
| `success: false`, `current_score == max_score` | did not compile; read `compiler_output` |
| `success: true`, score ≥ max_score | `diff_label` did not resolve — you renamed the function |
| HTTP 429 / 502 / 504 | transient; the harness backs off and retries |

Compile is not obviously rate-limited, but do not hammer it. One build per hypothesis is the discipline anyway.

---

# PART 4 — READING THE DIFF

## Row structure

Each row has `base` (target) and `current` (yours), each shaped `{text:[{text, format?, group?, key?}], mnemonic, line, branch?, src?, src_line?, src_comment?}`. Concatenate the `text` chunks to get the display line.

## Markers — the important part

The `format` values include `register`, `stack`, `immediate` and `rotation`, which are **highlighting categories, not difference flags.** Only `diff_add`, `diff_remove` and `diff_change` are true diff formats, and they cover fewer than a third of real differences. Detect divergence from the **leading marker character of the `current` column** — this is verified behaviour, not a guess.

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

Dominated by `r` with almost nothing else means register allocation. Reorder declarations, change local lifetimes, hoist or sink temporaries — do not touch semantics.

Dominated by `s` means stack frame layout: wrong number, size, order or alignment of locals. Look at the frame-size instruction `addiu sp,sp,-N` first. If that differs, nothing downstream lines up and every other divergence is noise.

Dominated by `i` means constants and struct offsets, almost always the wrong field or the wrong type width. Grep the context for the struct instead of guessing.

Many `>` and `<` in balanced pairs means instruction scheduling or a moved operation. Many `>` alone means you are generating extra work — a redundant load, an unnecessary spill, a missing common subexpression, or a local the target does not have.

A handful of `|` near the top with a clean tail means one wrong operation early. Fix that one; the rest is downstream noise.

## Diagnose from the first divergence

Compare in this order and stop at the first mismatch: frame size (`addiu sp,sp,-N`), then which registers the prologue saves and in what order, then branch structure and count, then call sites and their argument setup, then load/store counts, then constants and offsets, then the return path and epilogue.

Late-function divergence is usually downstream of a single earlier cause. Chasing the last difference is the classic way to burn twenty iterations.

---

# PART 5 — HYPOTHESIS DISCIPLINE

## The loop

```bash
./dcm.py hist                 # what class of problem?
./dcm.py diff -n 12           # first divergences, offline, free
# ---- form exactly ONE hypothesis, state it in one sentence ----
# ---- edit src.c minimally ----
./dcm.py build                # ~2s
./dcm.py log "widened arg3 to s32: 846 -> 501, kept"
# if REGRESSED: ./dcm.py revert   immediately, before thinking about the next idea
```

`best.c` and the git history are your safety net; the harness updates both automatically on improvement. You can always return to your best state with one command, which means you are free to try aggressive ideas — but only one at a time.

## Hypothesis catalogue, roughly in order of yield

**Argument count and register class of the callee.** On GE/PD this is the highest-yield check by far, because mips2c guesses call signatures and is frequently wrong. See Part 6.

**Types and signedness.** `s32` vs `u32` vs `s16` vs `u8` changes sign/zero extension and can add or remove whole instructions. On MIPS, `lb`/`lbu`/`lh`/`lhu` mismatches are pure type errors. High yield, low risk.

**Declaration order of locals.** Directly drives both stack layout and register allocation on IDO. If the histogram is `s`- or `r`-dominated, permute this first.

**Temporary lifetime.** Introducing or removing an explicit local changes allocation: `x = a->b; use(x); use(x);` and `use(a->b); use(a->b);` produce different code.

**Expression grouping and evaluation order.** `(a + b) + c` versus `a + (b + c)`, argument evaluation order, operand order in a comparison.

**Condition form.** `if (!x)` versus `if (x == 0)`, `if (a && b)` versus nested `if`, inverted branches, early return versus single exit.

**Loop form.** `for` versus `while` versus `do/while`, hand-hoisted loop invariants, pointer increment versus index.

**Struct access form.** `p->a.b[i]` versus a cached intermediate pointer. Wrong struct definitions in the context produce `i` divergences; grep `ctx.h` for the struct rather than guessing at the offset.

**Casts and pointer punning.** Where the cast sits changes the load width. `*(s32 *)((u8 *)p + 0x10)` and `p->field` can differ.

**`volatile`.** Forces a spill or prevents reordering. Occasionally the only way to match; a legitimate but last-resort tool, and it must be logged as such.

**Inlining and call form.** A `static` helper that the compiler inlines, or a call the compiler must not inline. Check whether the target has a real `jal` or an inlined body.

**Float handling.** `f32` versus `f64` intermediates, and on IDO whether a constant lives in the literal pool. Watch for `sdc1`/`ldc1` pairs around `$f20`+ — those indicate the target saves callee-saved FPU registers, which means it really uses doubles, not floats.

---

# PART 6 — GOLDENEYE / PERFECT DARK SPECIFICS

These scratches share a signature shape, and knowing it saves most of the iterations.

## The published source usually does not compile

GE/PD scratches are bulk-imported mips2c output. A published `score == max_score` (as on `jgiaZ`: 1300/1300) means the source has never compiled. Expect artifacts like a bare `?` where a return type belongs, `sp` pseudo-locals, `temp_t6` chains, and arithmetic on `void *` — which is a GCC extension that **IDO rejects**. Cast to `u8 *` before adding a byte offset. Your first job is a clean build, not a good score.

## The context is a whole-game header dump

417,462 characters on `jgiaZ`, mostly typedefs, struct definitions and prototypes for other functions. It is already correct for everything it contains. Two consequences: never rewrite it casually, and always check whether a symbol is in it before declaring your own:

```bash
./dcm.py ctx 'likely_generate_DL_for_image_declaration'
./dcm.py ctx 'typedef struct.*ObjHeader' --block 40
```

If the grep comes back empty, the callee is genuinely undeclared and **you must add an `extern` prototype at the top of `src.c`** — that is expected and normal, not a context edit.

## Read the o32 calling convention off the target

This is the single most useful skill for GE/PD, because it recovers the true signature that mips2c guessed wrong.

Integer arguments go in `a0`–`a3`; the fifth and later arguments go on the stack at `0x10(sp)`, `0x14(sp)`, and so on. The 16 bytes at `0x0(sp)`–`0xc(sp)` are the outgoing argument save area, so a store to `0x10(sp)` immediately before a `jal` is **argument five**, not a local. Floats go in `f12`/`f14` for the first two arguments in the common cases.

The decisive trick: **an argument register that is used by a call but never written by the function is a pass-through parameter of the function itself.** If the target sets `a0` and `a3` and stores one stack argument but never touches `a1` or `a2`, then `a1` and `a2` arrived as your function's own parameters and are being forwarded unchanged. mips2c cannot see this and will give you a function with too few parameters. Add them.

Also recognise: `sw a0,0x20(sp)` with a frame of `0x20` is homing an incoming argument into the caller's save slot, which IDO does when the parameter is live across a call or its address is taken; and the `move t6,a0` / `lw a3,4(t6)` shuffle is IDO's normal output for a struct pointer parameter that is used both as a base for a load and as an operand.

## Naming and settings

Never rename the function; `diff_label` must resolve. Never change the compiler from `ido5.3`. Do not add or remove flags on your own initiative (Part 8).

---

# PART 7 — WORKED EXAMPLE: `jgiaZ` (`sub_GAME_7F073038`)

This is the current assignment, and it is a complete run in miniature. It has already been verified end-to-end, so use it to check that your harness works before trying an unsolved scratch.

**Setup facts.** Preset 33 (GoldenEye / Perfect Dark), `ido5.3`, `-Olimit 2000 -mips2 -O2`, `max_score` 1300, context 417,462 chars, target 13 instructions. `./dcm.py family` shows three scratches, one of which (`01o4n`, by `inspectredc`) is already at **score 0** — worth knowing, and worth fetching with `./dcm.py family --get 01o4n` *after* you have made your own attempt, never before.

**Build 1 fails.** `cfe: Error: src.c, line 1: Syntax Error` on the leading `?`. The published source is mips2c output with a placeholder return type and `void *` arithmetic. No codegen reasoning yet — just make it compile.

**Read the target.** `./dcm.py target` shows a 13-instruction leaf-ish function: frame `0x20`, `ra` at `0x1c(sp)`, `a0` homed at `0x20(sp)`, `move t6,a0`, `lw a3,4(t6)`, `li t7,2` stored to `0x10(sp)`, then `jal likely_generate_DL_for_image_declaration` with `addiu a0,a0,0xc` in the delay slot.

**The one hypothesis.** The store to `0x10(sp)` makes this a five-argument call, but `a1` and `a2` are never written — so they are pass-through parameters of `sub_GAME_7F073038` itself, which therefore takes three arguments, not one. The `lw` at offset 4 is a word, so the field is 32-bit.

```c
extern void likely_generate_DL_for_image_declaration(void *, s32, s32, s32, s32);

void sub_GAME_7F073038(void *arg0, s32 arg1, s32 arg2) {
    likely_generate_DL_for_image_declaration((u8 *)arg0 + 0xC, arg1, arg2,
                                             ((s32 *)arg0)[1], 2);
}
```

`SCORE 0 / max 1300 — *** MATCH ***`, second build, no iteration loop needed.

**Counter-example, for calibration.** Changing the offset to `0x10`, the load to `((u8 *)arg0)[1]`, the constant to `3`, and adding an unnecessary local `s32 pad[3]` gives 846/1300 with a textbook histogram: `i` on the frame size, `>` for the extra spills the array caused, `|` where `lw` became `lbu`, and `r` where the register numbering shifted. Each marker maps to exactly one of the four mistakes. That is what a readable diff looks like, and it is why you change one thing at a time.

---

# PART 8 — LAST RESORTS, IN ORDER

Work down this list only after the tripwire has fired and you have reported to the user.

**1. Check the context.** If a struct in `ctx.h` has the wrong field width or a missing member, every access through it is wrong and the diff will be `i`-dominated in a way no C rewrite fixes. Grep the struct, compare the offsets against the target's load/store offsets, and propose the specific edit to the user before making it. Context edits are legitimate but they are a change to shared project truth, so say what you are changing and why.

**2. Consider `-mips3`.** You may switch `-mips2` to `-mips3` **only** if you can demonstrate from the target that a match is impossible under `-mips2` — for example the target contains 64-bit instructions (`ld`, `sd`, `dsll`, `daddu`) that `-mips2` cannot emit at all. "I tried a lot of things and nothing worked" is not a demonstration. State the evidence, get the user's approval, log it in `LOG.md`, and record the flag change in `meta.json`.

**3. Never change the compiler.** `ido5.3` is fixed. There is no circumstance in this project where changing it is correct.

Anything beyond this — saving, forking, or editing the scratch on the site — belongs to the user, not to you.

---

# PART 9 — ONE-PAGE CHECKLIST

```
pull        ./dcm.py pull jgiaZ
siblings    ./dcm.py family                      # someone may already have 0
build       ./dcm.py build                       # expect failure #1: mips2c artifacts
target      ./dcm.py target                      # read the asm BEFORE writing C
signature   count args: a0-a3 + 0x10(sp)+ ; unwritten arg regs = pass-through params
symbols     ./dcm.py ctx '<name>'                # never open ctx.h
compile     fix the build first, ignore the score until success:true
loop        hist -> diff -n 12 -> ONE hypothesis -> build -> log
regress     ./dcm.py revert   immediately
halt        8 flat builds / 3 same-category tries / 2 self-inflicted failures
report      status + hist + diff -n 15 + ruled-out list + one question
forbidden   browser on the scratch, Monaco typing, reading ctx.h, changing compiler
approval    save, fork, flag changes, context edits, downloads
```

---
