# decomp.me match harness — GoldenEye N64

## How to start an agent on this repository

Give an agent this repository and a scratch URL. Do not send only a URL. Send
this text:

    Read AGENTS.md before you do other work. Then solve
    https://www.decomp.me/scratch/i8JOn — do not fetch that URL.
    The command `./dcm.py pull` gets it for you.

Put the prohibition in your message. It is not enough to put it in a file. An
agent always reads your message. But it can be that the agent does not read a
README file before its first tool call. This repository cannot control this.

> ### Agents: read this before your first tool call
>
> **A decomp.me URL, or a slug with no other instruction, is your task. It is
> not a link to fetch.** Use the last part of the path as `SLUG`. Then do the
> command `./dcm.py pull $SLUG`. Part 1.1 gives the setup.
>
> **Do not send an HTTP request to decomp.me.** The request `GET
> /scratch/<slug>` gives you the `context` field of the scratch in the response.
> That field has 100,000 to 500,000 characters. This is 25,000 to 125,000 tokens
> in one tool result. It fills the largest part of your context window, and you
> cannot recover. This is the most frequent failure on this repository. It is
> more frequent than each error in the code. `dcm.py` is the only HTTP client
> here. **Part 0 gives the full rules and tells you why no curl option makes
> this safe.**

## What this repository is

Matching decompilation is a procedure. You write C source code. A specified old
compiler compiles that source code. The machine code must be the same as the
machine code in the released binary, byte for byte. Projects use this procedure
to make the source code of a game such as GoldenEye 007 again. Success is not
"the code operates". Success is an exact match at instruction level. A tool
calculates the score automatically. A low score is better than a high score. A
score of 0 is a match.

decomp.me is a public web service. It keeps these problems, which are called
*scratches*. It compiles your source code against the target. It has a JSON API
with no login.

This repository is an operating procedure and a tool harness. Together they let
an autonomous coding agent solve these scratches. The C code is not the
difficult part. The task is long and has many cycles, and there are many ways
for an agent to cause damage. A context file from a scratch can have more than
400,000 characters. One careless tool call can fill most or all of the context window.
Thus the harness does these things:

- It limits the output of each command.
- It keeps the data on the disk and not in the conversation.
- It writes each improvement to git.
- It goes back automatically when the score becomes worse.

Also, the procedure that follows gives the conditions when you must stop. These
conditions prevent an unlimited number of unsuccessful tries.

Two files are important:

- `README.md` — this document. The agent reads it first.
- `dcm.py` — the command-line tool that the agent uses.

A tool makes all the other files in a work directory.

---

# decomp.me match procedure — operating manual (GoldenEye N64)

**Readers: an autonomous coding agent with access to a shell. Read Part 0 and
Part 1 before you do other work.**

Task: `SLUG=<slug>`, from `https://decomp.me/scratch/<slug>`.

This document uses `jgiaZ` as an example, and Part 7 gives a full solution for
it. **Use the slug that the human gave to you.** Only the example in Part 7 is
specific to `jgiaZ`. The procedure is applicable to all GoldenEye scratches.

---

# PART 0 — PRIMARY RULES

**decomp.me is an HTTP service that compiles code. It is not a web application
that you operate.**

A public JSON API gives you each step of the match loop. The API needs no login,
no cookie and no CSRF token. The full procedure is `./dcm.py` and local files.
**Do not send HTTP requests.**

## Prohibited actions

WARNING: Do not do the actions that follow. They can stop your run.

1. Do not fetch a decomp.me URL with a tool that is not `dcm.py`. curl,
   curl.exe, wget, Invoke-WebRequest, a browser tool, and Python or Node code
   that you write are the same error with different names. Items 2 to 6 are
   about browser tools. Item 1 is about all the other tools.
2. Do not open a decomp.me scratch page in a browser tool to do work.
3. Do not type in the Monaco editor. The editor keeps only some lines in memory,
   it closes brackets automatically, and it shows completion menus. The editor
   can change your text with no message. Then you must correct syntax errors
   that you did not intend to make.
4. Do not click the Compile button.
5. Do not read the diff panel from an accessibility snapshot or from a
   screenshot.
6. Do not use a browser snapshot tool on a scratch page. Do not use it one time.
   The page has a Monaco editor and a diff table with one entry for each token.
   One snapshot can fill a large part of your context window. Also, each
   reference becomes obsolete after the next click. This is the most frequent
   cause of failure for this task.

If a browser MCP server is available, **do not use it for this task.** It is
better to remove it from the profile. If you want to use it, this shows that you
have a problem with the procedure. Go to Part 2.

## No curl option is safe

The option `--max-time` limits the time. It does not limit the number of bytes.
The options `--fail` and `-sS` limit the error output. They do not limit the
body. The option `-L` only makes sure that you get to the data. If you add
options that look careful, you limit the incorrect quantity. The request needs
less than two seconds and it is fully successful. This is the problem. **The
response is the damage.**

The hazard is the bytes that go into your transcript. The hazard is not the word
`curl`. Almost always, you do not have a correct reason to use decomp.me without
the harness. If you have such a reason, write the body to a file. Do not write
the body to stdout:

    curl -sS -o raw.json https://www.decomp.me/api/scratch/$SLUG
    wc -c raw.json          # look at the size before you read the contents

Then read the file with a tool that limits its output. The same rule is
applicable to wget, Invoke-WebRequest, `requests.get`, and each other client
that you write. `dcm.py` is the only HTTP client in this project. It writes the
`context` field directly to the file `ctx.h` on the disk. It does not let the
field go into the transcript. If you need data from the API, use a `dcm.py`
command. If there is no applicable command, ask the human. Do not write your own
client.

## The one permitted use of a browser

You can read a related issue, a decomp wiki page, or the documents of a project.
Do not read the scratch.

## Actions that need the approval of the human

A compile does not change stored data and has no cost. It does not change the
scratch. Thus you do not need approval, and you can compile as frequently as
your discipline permits. The actions that follow make or change content. The
human must agree in the chat before you do them:

- `PUT /scratch/{slug}` (save)
- `POST /scratch/{slug}/fork`
- a change to `compiler`, `compiler_flags` or `diff_label` in `meta.json`
- a download of a file that the harness does not write

## Rules that you cannot change

- Make only one hypothesis for each compile.
- Do not make a change on top of a change that you did not check.
- A low score is better. A score of 0 is a match. `max_score` is not a maximum
  for the score.
- Usually, `current_score == max_score` shows that your code did not compile. It
  does not show that your code compiled badly.
- The compiler is `ido5.3`. **Do not change it.** The flags are `-Olimit 2000
  -mips2 -O2`. Read Part 8 before you change them.

---

# PART 1 — SETUP (do this first, each time)

## 1.1 First commands

```bash
SLUG=<slug>                       # from https://decomp.me/scratch/<SLUG>
mkdir -p work/$SLUG && cd work/$SLUG
# put dcm.py in this directory (Part 1.2)
chmod +x dcm.py
./dcm.py pull $SLUG
./dcm.py family              # does a related scratch have a match?
./dcm.py build               # first build. Usually it fails. This is correct.
./dcm.py target              # READ THE TARGET before you write C code
```

The command `pull` writes `meta.json`, `src.c`, `ctx.h`, `best.c` and `LOG.md`.
It also makes a git baseline. The command `build` compiles the code on the
server and prints a limited report. No command prints more than approximately 40
lines.

## 1.2 The harness

The file `dcm.py` is in the root directory of the repository. Copy it into your
work directory. Then make it executable:

```bash
chmod +x dcm.py
```

Do not change `dcm.py`. Do not copy its text into a different file. There is one
copy, and this is it.

```
./dcm.py pull <slug> [--force]  fetch the scratch -> meta.json, src.c, ctx.h, best.c
./dcm.py build [-n N] [--src]   compile src.c on the server, print score + differences
./dcm.py diff  [-n N]           show the last result again, offline (no cost, no network)
./dcm.py diff --at ADDR         show the diff near one target address
./dcm.py diff --src             show the source lines of the target for the differences
./dcm.py hist                   print only the histogram of the difference categories
./dcm.py target [-n N]          print only the disassembly column of the TARGET
./dcm.py ctx <regex> [-n N]     grep ctx.h  (do NOT open ctx.h in a different way)
./dcm.py ctx <regex> --block 40 print 40 lines from the first result (struct definitions)
./dcm.py family [--get SLUG]    list related scratches / fetch the source of one of them
./dcm.py revert                 write best.c over src.c
./dcm.py log "text"             add one line to LOG.md
./dcm.py status                 score, best score, iteration, score history, recent log
```

The harness uses the public JSON API of decomp.me. Thus the agent does not use a
browser.

**Each command has a limit.** One command prints a maximum of approximately 120
rows. The quantity of the data does not change this limit. This limit is the
primary protection for your context window during a long task. This is why you
use these commands and not `cat`, `grep` or a browser tool.

The harness writes these files into the work directory. A tool makes all of
them. None of them is source code that you write:

| file | what it is |
|---|---|
| `meta.json` | the settings of the scratch, the best score, the number of iterations, the score history |
| `src.c` | your current attempt. This is the only file that you edit |
| `best.c` | an automatic copy of the attempt with the best score |
| `ctx.h` | the context of the scratch. It is very large. Do not open it directly |
| `target.txt` | the disassembly column of the target. The harness writes it at each build |
| `last.json` | the last successful compile response. `diff` and `hist` use it offline |
| `lastfail.json` | the last compile response that failed |
| `LOG.md` | your record of the hypotheses that you tried and removed |

`best.c` and `LOG.md` are your memory. They stay after a reset of the context.
The conversation does not stay.

## 1.3 An example of a build

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

One iteration gives approximately 25 lines. This is all the data that you get.
Do not ask for more data, if one specific hypothesis does not need it. Use
`./dcm.py diff --at 1c`, which is offline and has no cost. Do not compile again
for this.

---

# PART 2 — THE STOP CONDITIONS

You must obey these conditions. They have more importance than your opinion
about your progress. Agents that fail this task do not fail because they have
too few ideas. They fail because they make new ideas continuously and do not see
that no idea was successful.

## Stop immediately if one of these conditions occurs

- **You will run curl, wget, Invoke-WebRequest, or a different HTTP client on
  decomp.me.** Stop. Use the applicable `./dcm.py` command.
- **8 builds in sequence** did not improve `best_score`.
- **You tried the same category of hypothesis three times** (three different
  changes of a type, three different changes of a sequence). Count the category,
  not the edit.
- **Two builds in sequence failed** because of your own edit.
- **One tool result has more than approximately 2000 lines.** Or you cannot
  write a summary of each of two tool results in one sentence.
- **The score is equal to or more than `max_score`**, and you did not examine
  `diff_label`.
- **You will open a browser tool.**
- **You will read `ctx.h`, or print all of `src.c`,** to get general knowledge of
  the code.
- **You cannot say in one sentence what your last edit tested.**

## Stop procedure

```bash
./dcm.py revert
./dcm.py status
./dcm.py hist
./dcm.py diff -n 15
```

Then give this report: the best score, the histogram of the categories, the
first differences, the hypotheses that you removed, and one specific question.
Use `ask_followup_question`. **Do not continue.**

A correct score of 846/1300, with a clear diff and a list of the hypotheses that
you removed, has much more value than forty turns with no result. Such turns
usually stop at 846 also, and they fill your context.

## Checkpoints

If you do more than 25 iterations and you continue to make real progress, use
`new_task`. Move only these items: the slug, the best score, the histogram, the
three most important differences, and `LOG.md`. Do not move source code, context
or old diffs. `best.c` and `LOG.md` are on the disk. They are your memory. The
conversation is not your memory.

---

# PART 3 — THE API, AS CHECKED

Base URL: `https://decomp.me/api`. The items that follow need no login. The
address `www.decomp.me` also operates.

**This table shows what `dcm.py` does for you. It is not a list of commands for
you to run.** It helps you to understand the behavior of the harness and its
failure modes. Do not write the same operations again.

| Method | Path | Notes |
|---|---|---|
| GET | `/scratch/{slug}` | contains `context` — **100,000 to 500,000 characters. For the harness only. If you call this directly, your run stops.** |
| POST | `/scratch/{slug}/compile` | **the primary operation**. Approximately 1.8 s. No login, no CSRF. It does not change the scratch |
| GET | `/scratch/{slug}/family` | related scratches (forks and others) with their scores |
| GET | `/scratch/{slug}/export` | a zip file with the same 400 KB of data. For the harness only |
| GET | `/scratch?page_size=N` | pages of results: `{next, previous, results}` |
| GET | `/preset/{id}` | the compiler and the flags of a preset (GoldenEye is **33**) |
| GET | `/user` | the current identity |
| OPTIONS | each path | the DRF schema of the fields |
| PUT | `/scratch/{slug}` | save — **for the owner only. The user must give approval** |
| POST | `/scratch/{slug}/fork` | fork — **it makes content. The user must give approval** |

## The compile request

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

The fields `compiler` and `source_code` are necessary. The field `preset` is
optional, and it changes nothing when you give `compiler` and `compiler_flags`.
Thus the harness does not send it. You can omit `context`, but then the score
has no value, because each type in the function is not defined.

## The compile response

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

The field `diff_output` is in the response also when `success` is false. The
`base` column always contains the full disassembly of the target. Thus the
harness writes `target.txt` at each build, also when the build fails. Thus you
can read the target before your first successful compile.

## Failure modes

| Symptom | Meaning |
|---|---|
| HTTP 400, `{"compiler":["Unknown compiler: x"],"kind":"ValidationError"}` | the name of the compiler is incorrect. No compile occurred |
| `success: false`, `current_score == max_score` | the code did not compile. Read `compiler_output` |
| `success: true`, score equal to or more than `max_score` | `diff_label` did not find the function. You changed its name |
| HTTP 429 / 502 / 504 | a temporary condition. The harness waits and tries again |

There is no obvious limit on the rate of the compile requests. But do not send
many requests quickly. One build for each hypothesis is the correct discipline.

---

# PART 4 — HOW TO READ THE DIFF

## The structure of a row

Each row has a `base` part (the target) and a `current` part (your code). Each
part has this structure: `{text:[{text, format?, group?, key?}], mnemonic, line,
branch?, src?, src_line?, src_comment?}`. Put the `text` parts together to get
the line for the display.

## The markers — the important part

The `format` values contain `register`, `stack`, `immediate` and `rotation`.
These values are **categories for the display. They are not flags for a
difference.** Only `diff_add`, `diff_remove` and `diff_change` are true diff
formats, and they show less than one third of the real differences. To find a
difference, read **the first marker character of the `current` column**. This
behavior is checked. It is not a guess.

| Marker | Meaning | Usual cause |
|---|---|---|
| `<` | in the target, not in your code | a missing operation, a temporary variable that you removed, a different form of a call |
| `>` | in your code, not in the target | an extra spill, an extra load, an unnecessary temporary variable, a callee-saved register that you do not need |
| `\|` | the instruction is different | an incorrect operation: the sign, the width, or the wrong group of opcodes |
| `r` | only the register is different | the sequence of the allocation, the lifetime of a local variable, the sequence of the declarations |
| `s` | only the stack offset is different | the layout of the frame: the number, the sequence, the alignment or the padding of the local variables |
| `i` | the immediate value is different | an incorrect constant, an incorrect struct offset, an incorrect field |
| (space) | the same | — |

## How to read the histogram

The histogram shows the class of your problem before you read one instruction.

Many `r` markers and almost no other markers show a problem with the allocation
of the registers. Change the sequence of the declarations, change the lifetimes
of the local variables, and move the temporary variables. Do not change the
semantics.

Many `s` markers show a problem with the layout of the stack frame: an incorrect
number, size, sequence or alignment of the local variables. Look first at the
instruction for the frame size, `addiu sp,sp,-N`. If this instruction is
different, no subsequent instruction is in the correct position, and all the
other differences are noise.

Many `i` markers show a problem with the constants and the struct offsets.
Almost always the field or the width of the type is incorrect. Use grep on the
context to find the struct. Do not guess.

Many `>` and `<` markers in balanced pairs show a different sequence of the
instructions, or an operation in a different position. Many `>` markers with
almost no `<` markers show that your code does unnecessary work: an unnecessary
load, an unnecessary spill, a common subexpression that the compiler did not
find, or a local variable that the target does not have.

A small number of `|` markers near the top, with a clear part after them, shows
one incorrect operation near the start. Correct that operation. The other
differences are a result of it.

## Diagnosis from the first difference

Compare these items in this sequence, and stop at the first difference:

1. the frame size (`addiu sp,sp,-N`)
2. the registers that the prologue saves, and their sequence
3. the structure and the number of the branches
4. the calls and the setup of their arguments
5. the number of the loads and the stores
6. the constants and the offsets
7. the return path and the epilogue

Usually, a difference near the end of the function is a result of one cause
before it. If you correct the last difference first, you can use twenty
iterations with no result.

---

# PART 5 — DISCIPLINE FOR THE HYPOTHESES

## The loop

```bash
./dcm.py hist                 # which class of problem?
./dcm.py diff -n 12           # the first differences, offline, no cost
# ---- make exactly ONE hypothesis. Write it in one sentence ----
# ---- make the smallest possible edit to src.c ----
./dcm.py build                # approximately 2 s
./dcm.py log "arg3 changed to s32: 846 -> 501, kept"
# if the score is worse: ./dcm.py revert immediately, before you think about the next idea
```

`best.c` and the git history keep your best result. The harness writes to both of
them automatically when the score improves. One command gives your best state
again. Thus you can try large changes — but only one change at a time.

## Catalogue of the hypotheses, approximately in the sequence of their value

**The number of the arguments and the register class of the function that you
call.** For GoldenEye, examine this first. It gives the best results, because
mips2c guesses the signatures of the calls and is frequently incorrect. Refer to
Part 6.

**Types and signs.** `s32`, `u32`, `s16` and `u8` change the sign extension and
the zero extension. They can add or remove full instructions. On MIPS, a
difference between `lb`, `lbu`, `lh` and `lhu` is only an error of type. This
check has a high value and a low risk.

**The sequence of the declarations of the local variables.** On IDO, this
sequence controls the layout of the stack and the allocation of the registers.
If the histogram has many `s` or `r` markers, change this sequence first.

**The lifetime of a temporary variable.** If you add or remove a local variable,
the allocation changes. `x = a->b; use(x); use(x);` and `use(a->b); use(a->b);`
give different machine code.

**The groups in an expression and the sequence of the operations.** `(a + b) + c`
or `a + (b + c)`, the sequence of the arguments, and the sequence of the operands
in a comparison.

**The form of a condition.** `if (!x)` or `if (x == 0)`, `if (a && b)` or two
`if` statements in each other, inverted branches, an early return or one return
at the end.

**The form of a loop.** `for`, `while` or `do/while`, invariants that you move
out of the loop, an increment of a pointer or an index.

**The form of the access to a struct.** `p->a.b[i]`, or an intermediate pointer
that you keep in a variable. An incorrect struct definition in the context gives
`i` differences. Use grep on `ctx.h` to find the struct. Do not guess the offset.

**Casts and pointers to a different type.** The position of the cast changes the
width of the load. `*(s32 *)((u8 *)p + 0x10)` and `p->field` can be different.

**`volatile`.** This keyword causes a spill or prevents a change of the
sequence. Sometimes it is the only method to get a match. It is permitted, but
use it as the last method, and write it in the log.

**Inline code and the form of a call.** The compiler can put the body of a
`static` function directly in the code. Or the compiler must not do this.
Examine the target: does it have a `jal` instruction or the body of the
function?

**Floats.** `f32` or `f64` for the intermediate values. On IDO, examine also if a
constant is in the literal pool. Look for pairs of `sdc1` and `ldc1` near `$f20`
and higher. They show that the target saves the callee-saved FPU registers.
Thus the target uses doubles and not floats.

---

# PART 6 — SPECIFIC DATA FOR GOLDENEYE AND PERFECT DARK

These scratches have the same general shape. This knowledge decreases the number
of the iterations.

## Usually the published source code does not compile

The GoldenEye scratches are the output of mips2c from a bulk import. If the
published score is equal to `max_score` (on `jgiaZ` it is 1300/1300), the source
code never compiled. Expect problems such as these: a `?` character in the
position of a return type, pseudo-local variables with the name `sp`, sequences
of `temp_t6` variables, and arithmetic on `void *`. Arithmetic on `void *` is a
GCC extension, and **IDO does not accept it**. Do a cast to `u8 *` before you add
a byte offset. Your first task is a build with no errors. A good score comes
after that.

## The context is a header dump of the full game

On `jgiaZ` the context has 417,462 characters. Most of it is typedefs, struct
definitions and prototypes of other functions. All of its content is already
correct. This has two results: do not write it again without a good reason, and
always look for a symbol in it before you write your own declaration:

```bash
./dcm.py ctx 'likely_generate_DL_for_image_declaration'
./dcm.py ctx 'typedef struct.*ObjHeader' --block 40
```

If grep finds nothing, the function that you call is not declared. Then **you
must add an `extern` prototype at the top of `src.c`**. This is normal and
correct. It is not a change to the context.

## Read the o32 calling convention from the target

This is the most useful method for GoldenEye and Perfect Dark, because it gives
you the true signature. Frequently mips2c guesses that signature incorrectly.

The integer arguments are in `a0` to `a3`. Argument five and the subsequent
arguments are on the stack at `0x10(sp)`, `0x14(sp)`, and so on. The 16 bytes
from `0x0(sp)` to `0xc(sp)` are the save area for the outgoing arguments. Thus a
store to `0x10(sp)` immediately before a `jal` is **argument five**. It is not a
local variable. In the usual conditions, the first two float arguments are in
`f12` and `f14`.

The most useful rule is this: **if a call uses an argument register, and the
function never writes to that register, then that register is a parameter of the
function.** Example: the target sets `a0` and `a3` and stores one argument on
the stack, but it does not touch `a1` or `a2`. Then `a1` and `a2` are parameters
of your function, and the code sends them with no change. mips2c cannot see
this, and it gives you a function with too few parameters. Add the parameters.

Also know these two patterns:

- `sw a0,0x20(sp)` with a frame size of `0x20` puts an incoming argument into the
  save slot of the caller. IDO does this when the parameter is live across a
  call, or when the code uses the address of the parameter.
- `move t6,a0` with `lw a3,4(t6)` is the usual IDO output for a struct pointer
  parameter. The code uses that parameter as a base for a load and also as an
  operand.

## Names and settings

Do not change the name of the function, because `diff_label` must find it. Do
not change the compiler from `ido5.3`. Do not add or remove flags without
approval (refer to Part 8).

---

# PART 7 — EXAMPLE: `jgiaZ` (`sub_GAME_7F073038`)

This is the current task and a full run in a small form. It is checked from the
start to the end. Use it to make sure that your harness operates, before you try
a scratch with no solution.

**Setup data.** Preset 33 (GoldenEye), compiler `ido5.3`, flags `-Olimit 2000
-mips2 -O2`, `max_score` 1300, a context of 417,462 characters, a target of 13
instructions. The command `./dcm.py family` shows three scratches. One of them
(`01o4n`, from the user `inspectredc`) has a **score of 0**. This is useful
data. Get it with `./dcm.py family --get 01o4n`, but only *after* your own
attempt. Do not get it before.

**Build 1 fails.** The error is `cfe: Error: src.c, line 1: Syntax Error` at the
`?` character at the start. The published source is the output of mips2c. It has
a placeholder for the return type and arithmetic on `void *`. Do not think about
the code generation now. Only make the code compile.

**Read the target.** The command `./dcm.py target` shows a function of 13
instructions with almost no other calls: a frame of `0x20`, `ra` at `0x1c(sp)`,
`a0` in `0x20(sp)`, `move t6,a0`, `lw a3,4(t6)`, `li t7,2` with a store to
`0x10(sp)`, and then `jal likely_generate_DL_for_image_declaration` with `addiu
a0,a0,0xc` in the delay slot.

**The one hypothesis.** The store to `0x10(sp)` shows a call with five
arguments. But the code never writes to `a1` and `a2`. Thus `a1` and `a2` are
parameters of `sub_GAME_7F073038`, and that function has three parameters, not
one. The `lw` instruction at offset 4 reads a word. Thus the field has 32 bits.

```c
extern void likely_generate_DL_for_image_declaration(void *, s32, s32, s32, s32);

void sub_GAME_7F073038(void *arg0, s32 arg1, s32 arg2) {
    likely_generate_DL_for_image_declaration((u8 *)arg0 + 0xC, arg1, arg2,
                                             ((s32 *)arg0)[1], 2);
}
```

The result is `SCORE 0 / max 1300 — *** MATCH ***` at the second build. No loop
was necessary.

**A negative example, for comparison.** Change the offset to `0x10`, change the
load to `((u8 *)arg0)[1]`, change the constant to `3`, and add an unnecessary
local variable `s32 pad[3]`. Then the score is 846/1300, and the histogram is
typical: `i` for the frame size, `>` for the extra spills that the array caused,
`|` where `lw` became `lbu`, and `r` where the numbers of the registers moved.
Each marker is the result of one of the four errors. This is a diff that you can
read, and this is why you change only one item at a time.

---

# PART 8 — LAST METHODS, IN SEQUENCE

Use this list only after a stop condition occurred and you gave a report to the
user.

**1. Examine the context.** If a struct in `ctx.h` has an incorrect field width,
or a member is missing, each access through that struct is incorrect. Then the
diff has many `i` markers, and no change to the C code corrects this. Use grep to
find the struct. Compare its offsets with the offsets of the loads and the
stores in the target. Tell the user the specific change before you make it. A
change to the context is permitted, but it changes data that all the project
uses. Thus say what you change and why.

**2. Think about `-mips3`.** You can change `-mips2` to `-mips3` **only** if you
can show from the target that a match with `-mips2` is not possible. Example:
the target has 64-bit instructions (`ld`, `sd`, `dsll`, `daddu`), and `-mips2`
cannot make them. "I tried many things and nothing was successful" is not
satisfactory evidence. Give the evidence, get the approval of the user, write it
in `LOG.md`, and record the change of the flag in `meta.json`.

**3. Do not change the compiler.** `ido5.3` does not change. In this project
there is no condition where a change of the compiler is correct.

All the other actions — save the scratch, fork it, or change it on the web site
— are for the user. They are not for you.

---

# PART 9 — CHECKLIST (ONE PAGE)

```
task        a URL or a slug with no other instruction IS the task.
            SLUG = the last part of the path. Do not fetch the URL. Go to `pull`.
http        do not send HTTP requests. no curl / curl.exe / wget /
            Invoke-WebRequest / browser / requests / fetch(). dcm.py is the only client.
pull        ./dcm.py pull i8JOn                  # a full URL is also permitted
related     ./dcm.py family                      # a related scratch can have a score of 0
build       ./dcm.py build                       # failure 1 is usual: mips2c artifacts
target      ./dcm.py target                      # read the asm BEFORE you write C
signature   count the arguments: a0-a3 + 0x10(sp) and higher.
            an argument register with no write = a parameter of your function
symbols     ./dcm.py ctx '<symbol>'              # do not open ctx.h
compile     correct the build first. Ignore the score until success:true
loop        hist -> diff -n 12 -> ONE hypothesis -> build -> log
worse score ./dcm.py revert   immediately
stop        8 builds with no improvement / 3 tries in the same category /
            2 failures that you caused / you will run an HTTP client
report      status + hist + diff -n 15 + the list of removed hypotheses + one question
prohibited  each HTTP request that you send, a browser on the scratch,
            text in Monaco, ctx.h, a change of the compiler
approval    save, fork, changes of flags, changes of the context, downloads
```

If you read this checklist before Part 0, stop and read Part 0. One `curl`
command on a scratch URL costs 25,000 to 125,000 tokens and the remainder of the
run.

---
