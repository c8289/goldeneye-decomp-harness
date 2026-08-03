#!/usr/bin/env python3
"""Bounded decomp.me API harness for GoldenEye/Perfect Dark scratches.

Version 3.0 — the Part 2 tripwire is enforced here, not in the prompt.

The harness now owns the halt conditions the README describes, because an agent
in a long transcript cannot be trusted to count its own streaks:

  * 8 consecutive builds with no improvement          -> halt
  * 3 trials in the same hypothesis category          -> refused at declare time
  * 2 consecutive self-inflicted build failures       -> halt
  * any regression (score > best)                     -> auto-revert + halt
  * 25 builds (README checkpoint)                     -> halt
  * score 0                                           -> halt (save/fork is the human's)

A halt is sticky: it is written to meta.json, every later `build` and `trial`
refuses until the human runs `./dcm.py resume --ack "<reason>"`. Halting always
restores src.c from best.c, so the workspace is left in its best known state.

Every compile must be preceded by exactly one declared hypothesis:

    ./dcm.py trial --category loop --expect "drops the extra beq" "make the bounds check an explicit break"
    ./dcm.py build

`build` consumes that trial, records prev -> new score against it in LOG.md,
and counts the attempt against its category. LOG.md becomes an experiment
ledger rather than optional prose.

Offline guardrail tests:  ./dcm.py selftest
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://www.decomp.me/api"
MAX_PRINT = 120
CTX_FILE = "ctx.h"
SRC_FILE = "src.c"
BEST_FILE = "best.c"
META = "meta.json"
LAST = "last.json"
FAIL = "lastfail.json"
LOG = "LOG.md"
TARGET_FILE = "target.txt"

# ---- tripwire constants (README Part 2) ------------------------------------
FLAT_LIMIT = 8          # consecutive builds with no improvement to best_score
FAIL_LIMIT = 2          # consecutive self-inflicted build failures
CATEGORY_LIMIT = 3      # trials in one hypothesis category
BUILD_BUDGET = 25       # README checkpoint: new_task past 25 iterations
CHECKPOINT_AT = 12      # advisory: recommend a context checkpoint here

# Hypothesis categories, from the README Part 5 catalogue.
CATEGORIES = {
    "signature": "argument count / register class of the callee",
    "types": "types and signedness (s32/u32/s16/u8, lb vs lbu)",
    "order": "declaration order of locals (stack layout, allocation)",
    "lifetime": "temporary lifetime - introduce or remove a local",
    "grouping": "expression grouping and evaluation order",
    "condition": "condition form, branch inversion, early return",
    "loop": "loop form: for/while/do-while, invariants, pointer vs index",
    "struct": "struct access form, cached intermediate pointer",
    "cast": "casts and pointer punning, load width",
    "volatile": "volatile - last resort, must be logged as such",
    "inline": "inlining and call form, static helper vs real jal",
    "float": "f32 vs f64 intermediates, literal pool, sdc1/ldc1 pairs",
    "layout": "stack frame size / spill slot placement",
    "register": "register allocation pressure",
    "build": "fixing a compile error, not a codegen hypothesis",
    "other": "none of the above - say why in the text",
}
# `build` is exempt from CATEGORY_LIMIT: fixing a compile error is not a
# codegen hypothesis, and FAIL_LIMIT already bounds it.
UNCOUNTED = {"build", "baseline"}

MARKERS = {
    "<": "missing (in target, not in ours)",
    ">": "extra (in ours, not in target)",
    "|": "changed instruction",
    "r": "register mismatch",
    "s": "stack offset mismatch",
    "i": "immediate mismatch",
}


def die(msg):
    print("ERROR: " + str(msg), file=sys.stderr)
    raise SystemExit(2)


def _req(url, data=None, method=None, tries=4, timeout=180):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "dcm-harness/3.0"}
    last = None
    for n in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            payload = e.read().decode(errors="replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and n < tries - 1:
                time.sleep(2 ** n * 2)
                last = "HTTP %d" % e.code
                continue
            die("HTTP %d from %s\n%s" % (e.code, url, payload))
        except Exception as e:  # noqa: BLE001
            if n < tries - 1:
                time.sleep(2 ** n * 2)
                last = str(e)[:200]
                continue
            die("network failure: %s" % e)
    die("gave up after %d tries: %s" % (tries, last))


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------

GUARD_DEFAULTS = {
    "iteration": 0,
    "best_score": None,
    "history": [],
    "flat_streak": 0,
    "failure_streak": 0,
    "halted": False,
    "halt_reason": None,
    "halt_kind": None,
    "categories": {},
    "category_allow": {},
    "budget_extra": 0,
    "pending_trial": None,
    "trials": [],
    "acks": [],
}


def with_defaults(meta):
    for key, value in GUARD_DEFAULTS.items():
        if key not in meta or meta[key] is None and key not in ("best_score", "halt_reason",
                                                                "halt_kind", "pending_trial"):
            meta[key] = json.loads(json.dumps(value))
    return meta


def load_meta():
    if not os.path.exists(META):
        die("no meta.json here - run './dcm.py pull <slug>' first")
    with open(META) as f:
        return with_defaults(json.load(f))


def save_meta(meta):
    with open(META, "w") as f:
        json.dump(meta, f, indent=1)


def git(*args):
    subprocess.run(["git", *args], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# pure guardrail logic  (no I/O -> exercised by ./dcm.py selftest)
# ---------------------------------------------------------------------------

def category_budget(meta, category):
    """How many trials this category is allowed in total."""
    if category in UNCOUNTED:
        return None  # unlimited; bounded by FAIL_LIMIT / FLAT_LIMIT instead
    return CATEGORY_LIMIT + meta.get("category_allow", {}).get(category, 0)


def check_trial(meta, category):
    """Return (allowed, reason). Refuses the 4th trial in one category."""
    if meta.get("halted"):
        return False, "harness is halted: %s" % meta.get("halt_reason")
    if category not in CATEGORIES:
        return False, "unknown category '%s' (see ./dcm.py categories)" % category
    budget = category_budget(meta, category)
    if budget is None:
        return True, ""
    used = meta.get("categories", {}).get(category, 0)
    if used >= budget:
        return False, ("category '%s' already tried %d times (limit %d) - README Part 2: "
                       "the same category three times is a halt condition"
                       % (category, used, budget))
    return True, ""


def record_trial(meta, category, text, expect):
    """Store the single pending hypothesis and charge it to its category."""
    previous = meta.get("pending_trial")
    if previous and previous["category"] not in UNCOUNTED:
        counts = meta.setdefault("categories", {})
        counts[previous["category"]] = max(0, counts.get(previous["category"], 1) - 1)
    if category not in UNCOUNTED:
        counts = meta.setdefault("categories", {})
        counts[category] = counts.get(category, 0) + 1
    meta["pending_trial"] = {
        "category": category,
        "text": text,
        "expect": expect,
        "prev_score": meta.get("best_score"),
        "declared_at": meta.get("iteration", 0),
    }
    return meta["pending_trial"]


def apply_build_result(meta, ok, score=None, max_score=None):
    """Advance all counters for one compile. Returns a verdict dict.

    Keys: verdict, halt (reason or None), halt_kind, restore (bool), warn (list).
    Callers do the file I/O; this function only moves numbers.
    """
    meta["iteration"] = meta.get("iteration", 0) + 1
    out = {"verdict": None, "halt": None, "halt_kind": None, "restore": False, "warn": []}

    if not ok:
        meta["failure_streak"] = meta.get("failure_streak", 0) + 1
        out["verdict"] = "FAILED"
        if meta["failure_streak"] >= FAIL_LIMIT:
            out["halt"] = ("%d consecutive build failures from your own edits"
                           % meta["failure_streak"])
            out["halt_kind"] = "fail"
            out["restore"] = True
        return out

    meta["failure_streak"] = 0
    meta.setdefault("history", []).append(score)
    meta["history"] = meta["history"][-40:]
    best = meta.get("best_score")

    if best is None or score < best:
        meta["best_score"] = score
        meta["flat_streak"] = 0
        out["verdict"] = "IMPROVED"
    elif score == best:
        meta["flat_streak"] = meta.get("flat_streak", 0) + 1
        out["verdict"] = "SAME"
    else:
        out["verdict"] = "REGRESSED"
        out["restore"] = True
        out["halt"] = "regression %s -> %s; src.c restored from best.c" % (best, score)
        out["halt_kind"] = "regress"
        return out

    if max_score is not None and score >= max_score:
        out["warn"].append(
            "score >= max_score almost always means it did not compile, or diff_label is wrong "
            "- check diff_label before forming another codegen hypothesis")

    if score == 0:
        out["halt"] = "MATCH (score 0) - do not save or fork without the human's approval"
        out["halt_kind"] = "match"
        return out

    if meta["flat_streak"] >= FLAT_LIMIT:
        out["halt"] = "%d consecutive builds with no improvement to best_score" % FLAT_LIMIT
        out["halt_kind"] = "flat"
        out["restore"] = True
    elif meta["iteration"] >= BUILD_BUDGET + meta.get("budget_extra", 0):
        out["halt"] = ("build budget reached (%d iterations) - README Part 2 says checkpoint "
                       "with new_task here" % meta["iteration"])
        out["halt_kind"] = "budget"
        out["restore"] = True
    return out


def apply_resume(meta, ack, category=None):
    """Clear the halt state only. History, iteration and the ledger survive."""
    kind = meta.get("halt_kind")
    meta["acks"] = (meta.get("acks") or []) + [
        {"iteration": meta.get("iteration", 0), "kind": kind, "ack": ack}]
    if kind == "flat":
        meta["flat_streak"] = 0
    elif kind == "fail":
        meta["failure_streak"] = 0
    elif kind == "budget":
        meta["budget_extra"] = meta.get("budget_extra", 0) + 10
    elif kind == "category" and category:
        allow = meta.setdefault("category_allow", {})
        allow[category] = allow.get(category, 0) + 1
    meta["halted"] = False
    meta["halt_reason"] = None
    meta["halt_kind"] = None
    return meta


# ---------------------------------------------------------------------------
# diff rendering (unchanged, still hard-bounded)
# ---------------------------------------------------------------------------

def flat(side):
    return "".join(t["text"] for t in side["text"]) if side else ""


def marker(row):
    text = flat(row.get("current")) or flat(row.get("base"))
    return text[:1] if text[:1] in MARKERS else " "


def render(rows, limit, at=None, show_src=False):
    marks = [marker(r) != " " for r in rows]
    idxs = [i for i, m in enumerate(marks) if m]
    if not idxs:
        return ["(no divergences)"], 0
    if at is not None:
        hit = [i for i, r in enumerate(rows) if at in flat(r.get("base"))]
        centre = hit[0] if hit else idxs[0]
        span = range(max(0, centre - 8), min(len(rows), centre + 16))
    else:
        keep = set()
        for i in idxs[:limit]:
            keep.update(range(max(0, i - 2), min(len(rows), i + 3)))
        span = sorted(keep)
    out, previous = [], None
    for i in span:
        if previous is not None and i != previous + 1:
            out.append("   ...")
        row = rows[i]
        out.append((" %s %-40s| %s" %
                    (marker(row), flat(row.get("base")), flat(row.get("current"))))[:200])
        if show_src and marks[i]:
            for source_line in (row.get("base") or {}).get("src", [])[:1]:
                out.append("        ^ target src: %s" % source_line[:120])
        previous = i
    return out[:MAX_PRINT], len(idxs)


def histogram(rows):
    result = {}
    for row in rows:
        mark = marker(row)
        if mark != " ":
            result[mark] = result.get(mark, 0) + 1
    return result


def print_hist(hist, total):
    if not hist:
        print("  clean")
        return
    for mark, count in sorted(hist.items(), key=lambda kv: -kv[1]):
        print("  %s  %4d  %-38s %s" %
              (mark, count, MARKERS[mark], "#" * min(40, count)))
    print("  -- %d divergent of %d rows" % (sum(hist.values()), total))


# ---------------------------------------------------------------------------
# halt plumbing
# ---------------------------------------------------------------------------

def dashboard(meta):
    lines = []
    lines.append("  total builds   %4d / %d" %
                 (meta["iteration"], BUILD_BUDGET + meta.get("budget_extra", 0)))
    lines.append("  flat streak    %4d / %d" % (meta.get("flat_streak", 0), FLAT_LIMIT))
    lines.append("  failed streak  %4d / %d" % (meta.get("failure_streak", 0), FAIL_LIMIT))
    for category, used in sorted(meta.get("categories", {}).items(), key=lambda kv: -kv[1]):
        if used:
            budget = category_budget(meta, category)
            lines.append("  %-13s  %4d / %s" %
                         (category + " trials", used, budget if budget else "-"))
    lines.append("  halted         %s" %
                 ("YES - %s" % meta.get("halt_reason") if meta.get("halted") else "no"))
    return lines


def restore_best(note=""):
    if os.path.exists(BEST_FILE):
        shutil.copy(BEST_FILE, SRC_FILE)
        print("   src.c restored from best.c %s" % note)


def do_halt(meta, reason, kind, restore):
    meta["halted"] = True
    meta["halt_reason"] = reason
    meta["halt_kind"] = kind
    meta["pending_trial"] = None
    save_meta(meta)
    print("\n" + "=" * 68)
    print("HALTED — %s" % reason)
    print("=" * 68)
    if restore:
        restore_best("(best score %s)" % meta.get("best_score"))
    print("\nREADME Part 2 halt procedure — run these, then STOP:")
    print("   ./dcm.py status")
    print("   ./dcm.py hist")
    print("   ./dcm.py diff -n 15")
    print("\nReport to the human: best score, the histogram, the first divergences,")
    print("the hypotheses already ruled out, and ONE specific question. Do not continue.")
    if kind != "match":
        print("\nOnly the human unblocks this:")
        print('   ./dcm.py resume --ack "<why continuing is the right call>"%s'
              % (" --category <cat>" if kind == "category" else ""))
    raise SystemExit(3)


def block_if_halted(meta):
    if meta.get("halted"):
        print("HALTED — %s" % meta.get("halt_reason"), file=sys.stderr)
        print("The harness will not compile again until the human acknowledges this.",
              file=sys.stderr)
        print('   ./dcm.py resume --ack "<reason>"', file=sys.stderr)
        print("Offline commands still work: status, hist, diff, target, ctx.", file=sys.stderr)
        raise SystemExit(3)


def ledger(meta, trial, verdict, score):
    entry = {"iteration": meta["iteration"], "category": trial["category"],
             "text": trial["text"], "expect": trial.get("expect"),
             "prev": trial.get("prev_score"), "score": score, "verdict": verdict}
    meta.setdefault("trials", []).append(entry)
    meta["trials"] = meta["trials"][-60:]
    if os.path.exists(LOG):
        with open(LOG, "a") as f:
            f.write("- #%d [%s] %s -> %s %s | %s | expected: %s\n" % (
                entry["iteration"], entry["category"],
                entry["prev"] if entry["prev"] is not None else "-",
                score if score is not None else "BUILD FAILED",
                verdict, entry["text"], entry.get("expect") or "-"))
    return entry


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def slug_of(text):
    """Accept a bare slug or a full decomp.me URL (README Part 9)."""
    text = text.strip().rstrip("/")
    if "://" in text or "decomp.me" in text:
        text = text.split("/")[-1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", text):
        die("that does not look like a scratch slug: %r" % text[:60])
    return text


def cmd_pull(args):
    slug = slug_of(args.slug)
    scratch = _req("%s/scratch/%s" % (API, slug))
    if os.path.exists(SRC_FILE) and not args.force:
        print("src.c exists - keeping your work (use --force to overwrite)")
    else:
        with open(SRC_FILE, "w") as f:
            f.write(scratch.get("source_code") or "")
    if not os.path.exists(BEST_FILE) or args.force:
        shutil.copy(SRC_FILE, BEST_FILE)
    with open(CTX_FILE, "w") as f:
        f.write(scratch.get("context") or "")
    old = {}
    if os.path.exists(META):
        with open(META) as f:
            old = json.load(f)
    meta = {key: scratch.get(key) for key in (
        "slug", "name", "platform", "language", "compiler", "compiler_flags",
        "preset", "libraries", "diff_flags", "diff_label", "score", "max_score",
        "match_override")}
    meta["slug"] = meta.get("slug") or slug
    for key in GUARD_DEFAULTS:
        if key in old:
            meta[key] = old[key]
    meta = with_defaults(meta)
    save_meta(meta)
    if not os.path.exists(LOG):
        with open(LOG, "w") as f:
            f.write("# %s (%s)\n\ntarget: %s   %s %s\n\n## experiment ledger\n\n" % (
                meta["name"], slug, meta["diff_label"],
                meta["compiler"], meta["compiler_flags"]))
    if not os.path.isdir(".git"):
        git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "baseline")
    print("scratch   %s  [%s]" % (meta["name"], slug))
    print("platform  %s   compiler %s   preset %s" %
          (meta["platform"], meta["compiler"], meta["preset"]))
    print("flags     %s" % meta["compiler_flags"])
    print("label     %s      <-- DO NOT rename this function" % meta["diff_label"])
    print("src.c     %d lines" % (open(SRC_FILE).read().count("\n") + 1))
    print("ctx.h     %d bytes  <-- NEVER read this file, use './dcm.py ctx <regex>'" %
          os.path.getsize(CTX_FILE))
    print("published score %s / max %s" % (meta["score"], meta["max_score"]))
    print("\nguardrails: %d flat builds / %d same-category trials / %d failures / %d builds"
          % (FLAT_LIMIT, CATEGORY_LIMIT, FAIL_LIMIT, BUILD_BUDGET))
    print("every build needs a declared hypothesis first: ./dcm.py trial --help")


def cmd_categories(_args):
    print("hypothesis categories (limit %d trials each, then the harness refuses):"
          % CATEGORY_LIMIT)
    for name, description in CATEGORIES.items():
        note = "  [uncounted]" if name in UNCOUNTED else ""
        print("  %-10s %s%s" % (name, description, note))


def cmd_trial(args):
    meta = load_meta()
    block_if_halted(meta)
    text = args.text.strip()
    if len(text) < 8:
        die("state the hypothesis in one sentence - if you cannot, README Part 2 says halt")
    expect = (args.expect or "").strip()
    if len(expect) < 5:
        die("--expect is required: what should this change do to the diff?")
    allowed, reason = check_trial(meta, args.category)
    if not allowed:
        if args.category in CATEGORIES:
            do_halt(meta, reason, "category", restore=True)
        die(reason)
    trial = record_trial(meta, args.category, text, expect)
    save_meta(meta)
    print("trial armed  [%s]  from score %s" %
          (trial["category"], trial["prev_score"] if trial["prev_score"] is not None else "-"))
    print("  test:   %s" % trial["text"])
    print("  expect: %s" % trial["expect"])
    used = meta["categories"].get(args.category, 0)
    budget = category_budget(meta, args.category)
    if budget:
        print("  %s trials %d / %d" % (args.category, used, budget))
    print("\nEdit src.c minimally, then './dcm.py build'. One hypothesis per compile.")


def cmd_build(args):
    meta = load_meta()
    block_if_halted(meta)

    trial = meta.get("pending_trial")
    if trial is None:
        if meta["iteration"] == 0:
            trial = {"category": "baseline", "text": "first compile of the pulled source",
                     "expect": "establish the baseline score", "prev_score": None}
        else:
            die("no pending hypothesis. README Part 5: one hypothesis per compile.\n"
                '  ./dcm.py trial --category <cat> --expect "<effect on the diff>" "<one sentence>"\n'
                "  ./dcm.py categories   # list the categories")

    with open(SRC_FILE) as f:
        source = f.read()
    if not source.strip():
        die("src.c is empty - refusing to compile")
    label = meta.get("diff_label") or ""
    if label and label not in source:
        print("WARNING: '%s' does not appear in src.c." % label)

    body = {"compiler": meta["compiler"], "compiler_flags": meta["compiler_flags"],
            "source_code": source, "context": open(CTX_FILE).read(),
            "diff_label": label, "libraries": meta.get("libraries") or [],
            "diff_flags": meta.get("diff_flags") or []}
    started = time.time()
    response = _req("%s/scratch/%s/compile" % (API, meta["slug"]), data=body)
    elapsed = time.time() - started

    if response.get("diff_output"):
        with open(TARGET_FILE, "w") as f:
            f.write("\n".join(flat(row.get("base")) for row in response["diff_output"]["rows"]))

    output = response.get("compiler_output") or ""
    errors, seen = [], set()
    for line in output.splitlines():
        line = line.strip()
        if ("rror" in line or "arning" in line) and line not in seen:
            seen.add(line)
            errors.append(line[:160])

    # ---- build failed ----
    if not response.get("success"):
        with open(FAIL, "w") as f:
            json.dump(response, f)
        result = apply_build_result(meta, ok=False)
        meta["pending_trial"] = None
        ledger(meta, trial, "FAILED", None)
        save_meta(meta)
        print("BUILD FAILED  (iteration %d, %.1fs)  failure streak %d / %d" %
              (meta["iteration"], elapsed, meta["failure_streak"], FAIL_LIMIT))
        for error in errors[:12]:
            print("   " + error)
        if not errors:
            print("   " + output[:400])
        if result["halt"]:
            shutil.copy(SRC_FILE, "fail_iter%d.c" % meta["iteration"])
            do_halt(meta, result["halt"], result["halt_kind"], result["restore"])
        print("\nFix the build. Do not reason about codegen yet.")
        print('Next: ./dcm.py trial --category build --expect "compiles" "<the fix>"')
        raise SystemExit(1)

    # ---- build succeeded ----
    with open(LAST, "w") as f:
        json.dump(response, f)
    diff = response["diff_output"]
    score, maximum, rows = diff["current_score"], diff["max_score"], diff["rows"]
    previous_best = meta.get("best_score")
    result = apply_build_result(meta, ok=True, score=score, max_score=maximum)
    verdict = result["verdict"]

    if verdict == "IMPROVED":
        shutil.copy(SRC_FILE, BEST_FILE)
        git("add", "-A")
        git("commit", "-qm", "iter %d score %d [%s] %s" %
            (meta["iteration"], score, trial["category"], trial["text"][:60]))
    elif verdict == "REGRESSED":
        shutil.copy(SRC_FILE, "regress_iter%d.c" % meta["iteration"])

    meta["pending_trial"] = None
    ledger(meta, trial, verdict, score)
    save_meta(meta)

    print("SCORE %d / max %d   best %s   [%s]  iter %d  %.1fs" %
          (score, maximum, meta["best_score"], verdict, meta["iteration"], elapsed))
    print("trial [%s] %s  (%s -> %s)" %
          (trial["category"], trial["text"][:70],
           previous_best if previous_best is not None else "-", score))
    for warning in result["warn"]:
        print("WARNING: %s" % warning)

    if result["halt"] and result["halt_kind"] == "match":
        print("\n*** MATCH *** - stop editing.")
        do_halt(meta, result["halt"], "match", restore=False)
    if result["halt"] and result["halt_kind"] == "regress":
        do_halt(meta, result["halt"], "regress", restore=True)

    print("\ndifference categories:")
    print_hist(histogram(rows), len(rows))
    lines, count = render(rows, args.n, show_src=args.src)
    print("\nfirst %d of %d divergences (target | ours):" % (min(args.n, count), count))
    for line in lines:
        print(line)

    print("\nguardrails:")
    for line in dashboard(meta):
        print(line)

    if result["halt"]:
        do_halt(meta, result["halt"], result["halt_kind"], result["restore"])

    remaining = FLAT_LIMIT - meta["flat_streak"]
    if verdict == "SAME" and remaining <= 3:
        print("\n%d flat builds left before the harness halts you." % remaining)
    if meta["iteration"] == CHECKPOINT_AT:
        print("\nCHECKPOINT: %d builds in. If you are still making real progress, use new_task"
              % CHECKPOINT_AT)
        print("and carry over only: slug, best score, histogram, top 3 divergences, LOG.md.")


def last_diff():
    if not os.path.exists(LAST):
        die("no last.json - run './dcm.py build' first")
    with open(LAST) as f:
        response = json.load(f)
    if not response.get("diff_output"):
        die("no diff in last.json")
    return response["diff_output"]


def cmd_diff(args):
    diff = last_diff()
    lines, count = render(diff["rows"], args.n, at=args.at, show_src=args.src)
    print("score %s / %s   %d divergent rows" %
          (diff["current_score"], diff["max_score"], count))
    print("\n".join(lines))


def cmd_hist(_args):
    diff = last_diff()
    print("score %s / %s" % (diff["current_score"], diff["max_score"]))
    print_hist(histogram(diff["rows"]), len(diff["rows"]))


def cmd_target(args):
    if not os.path.exists(TARGET_FILE):
        die("no target.txt - run './dcm.py build' once")
    with open(TARGET_FILE) as f:
        lines = f.read().splitlines()
    print("target %s: %d instructions" % (load_meta()["diff_label"], len(lines)))
    for line in lines[:min(args.n, MAX_PRINT)]:
        print("  " + line[:160])
    if len(lines) > args.n:
        print("  ... +%d more (use -n)" % (len(lines) - args.n))


def cmd_ctx(args):
    if not os.path.exists(CTX_FILE):
        die("no ctx.h")
    pattern = re.compile(args.pattern)
    with open(CTX_FILE, errors="replace") as f:
        lines = f.read().splitlines()
    if args.block:
        for index, line in enumerate(lines):
            if pattern.search(line):
                for j in range(index, min(len(lines), index + min(args.block, MAX_PRINT))):
                    print("%6d: %s" % (j + 1, lines[j][:160]))
                return
        print("(no match)")
        return
    shown = 0
    for index, line in enumerate(lines, 1):
        if pattern.search(line):
            print("%6d: %s" % (index, line.strip()[:160]))
            shown += 1
            if shown >= min(args.n, MAX_PRINT):
                print("  ... truncated; tighten the regex")
                break
    if shown == 0:
        print("(no match in %d lines - the symbol is NOT in the context;" % len(lines))
        print(" you must declare it yourself in src.c)")


def cmd_family(args):
    meta = load_meta()
    if args.get:
        slug = slug_of(args.get)
        scratch = _req("%s/scratch/%s" % (API, slug))
        filename = "sib_%s.c" % slug
        with open(filename, "w") as f:
            f.write(scratch.get("source_code") or "")
        print("wrote %s (%d bytes) - read it, do not paste it blindly" %
              (filename, os.path.getsize(filename)))
        return
    family = _req("%s/scratch/%s/family" % (API, meta["slug"]))
    items = family if isinstance(family, list) else family.get("results", [])
    for item in items[:40]:
        star = "   <== MATCHED" if item.get("score") == 0 else ""
        print("%-8s score %-6s/%-6s  by %-16s %s%s" % (
            item.get("slug"), item.get("score"), item.get("max_score"),
            (item.get("owner") or {}).get("username", "?"),
            (item.get("last_updated") or "")[:10], star))


def cmd_revert(_args):
    if not os.path.exists(BEST_FILE):
        die("no best.c")
    meta = load_meta()
    shutil.copy(BEST_FILE, SRC_FILE)
    meta["pending_trial"] = None
    save_meta(meta)
    print("src.c restored from best.c (score %s); pending trial cleared" %
          meta.get("best_score"))


def cmd_resume(args):
    meta = load_meta()
    if not meta.get("halted"):
        print("not halted - nothing to resume")
        return
    ack = args.ack.strip()
    if len(ack) < 15:
        die("--ack must say, in a sentence, why continuing is the right call")
    kind = meta.get("halt_kind")
    if kind == "category" and not args.category:
        die("this halt was a category limit - pass --category <name> to grant one more trial")
    if kind == "match":
        print("NOTE: score is 0. Saving or forking the scratch is the human's call, not yours.")
    reason = meta.get("halt_reason")
    apply_resume(meta, ack, args.category)
    save_meta(meta)
    print("resumed. cleared: %s" % reason)
    print("preserved: iteration %d, best %s, %d ledger entries" %
          (meta["iteration"], meta.get("best_score"), len(meta.get("trials", []))))
    for line in dashboard(meta):
        print(line)


def cmd_log(args):
    meta = load_meta()
    with open(LOG, "a") as f:
        f.write("- #%d [%s] note: %s\n" % (meta["iteration"], meta.get("best_score"), args.text))
    print("logged")


def cmd_status(_args):
    meta = load_meta()
    print("%s [%s]  label %s" % (meta["name"], meta["slug"], meta["diff_label"]))
    print("iteration %d   best %s / %s" %
          (meta["iteration"], meta.get("best_score"), meta["max_score"]))
    history = meta.get("history", [])[-15:]
    if history:
        print("history   " + " ".join(str(x) for x in history))
    print("\nguardrails:")
    for line in dashboard(meta):
        print(line)
    pending = meta.get("pending_trial")
    if pending:
        print("\npending trial [%s] %s" % (pending["category"], pending["text"][:80]))
    trials = meta.get("trials", [])[-8:]
    if trials:
        print("\nrecent trials:")
        for entry in trials:
            print("  #%-3d %-10s %5s -> %-5s %-9s %s" % (
                entry["iteration"], entry["category"],
                entry["prev"] if entry["prev"] is not None else "-",
                entry["score"] if entry["score"] is not None else "fail",
                entry["verdict"], (entry["text"] or "")[:60]))
    if os.path.exists(LOG):
        with open(LOG) as f:
            tail = f.read().splitlines()[-6:]
        if tail:
            print("\nLOG.md tail:")
            print("\n".join("  " + line[:150] for line in tail))


# ---------------------------------------------------------------------------
# offline guardrail tests
# ---------------------------------------------------------------------------

def cmd_selftest(_args):
    def fresh(best=None):
        meta = with_defaults({"slug": "test", "best_score": best})
        return meta

    checks = []

    def check(name, condition):
        checks.append((name, bool(condition)))

    # 1. eight unchanged scores -> halted
    meta, halt = fresh(1230), None
    for _ in range(FLAT_LIMIT):
        halt = apply_build_result(meta, True, 1230, 5800)
    check("8 flat builds halt", halt["halt"] and halt["halt_kind"] == "flat" and halt["restore"])
    check("flat streak reached limit", meta["flat_streak"] == FLAT_LIMIT)

    # 2. an improvement resets the flat streak
    meta = fresh(1230)
    for _ in range(5):
        apply_build_result(meta, True, 1230, 5800)
    check("streak accumulated", meta["flat_streak"] == 5)
    result = apply_build_result(meta, True, 900, 5800)
    check("improvement resets streak", meta["flat_streak"] == 0 and result["verdict"] == "IMPROVED")
    check("best tracked", meta["best_score"] == 900)
    for _ in range(FLAT_LIMIT - 1):
        result = apply_build_result(meta, True, 900, 5800)
    check("no premature halt after reset", result["halt"] is None)

    # 3. two consecutive failures -> halted
    meta = fresh(1230)
    first = apply_build_result(meta, False)
    check("one failure does not halt", first["halt"] is None and first["verdict"] == "FAILED")
    second = apply_build_result(meta, False)
    check("two failures halt", second["halt"] and second["halt_kind"] == "fail")

    # a success in between resets the failure streak
    meta = fresh(1230)
    apply_build_result(meta, False)
    apply_build_result(meta, True, 1230, 5800)
    check("success resets failure streak", meta["failure_streak"] == 0)

    # 4. regression -> restore from best, and halt
    meta = fresh(1230)
    result = apply_build_result(meta, True, 1400, 5800)
    check("regression restores", result["verdict"] == "REGRESSED" and result["restore"])
    check("regression halts", result["halt_kind"] == "regress")
    check("regression keeps best", meta["best_score"] == 1230)

    # 5. three trials in one category -> the fourth is refused
    meta = fresh(1230)
    for n in range(CATEGORY_LIMIT):
        allowed, _ = check_trial(meta, "loop")
        if allowed:
            record_trial(meta, "loop", "hypothesis %d" % n, "expected effect")
            meta["pending_trial"] = None  # simulate the build consuming it
    allowed, reason = check_trial(meta, "loop")
    check("4th same-category trial refused", not allowed and "loop" in reason)
    allowed, _ = check_trial(meta, "types")
    check("other categories unaffected", allowed)
    check("build category uncounted", category_budget(meta, "build") is None)

    # replacing a pending trial must not double-charge the category
    meta = fresh(1230)
    record_trial(meta, "cast", "first idea", "expected effect")
    record_trial(meta, "cast", "second idea", "expected effect")
    check("replacing pending trial does not double count", meta["categories"]["cast"] == 1)

    # 6. resume clears only the halt state
    meta = fresh(1230)
    for _ in range(FLAT_LIMIT):
        result = apply_build_result(meta, True, 1230, 5800)
    meta["halted"], meta["halt_reason"], meta["halt_kind"] = True, result["halt"], "flat"
    record_trial(meta, "loop", "some idea", "expected effect")
    iteration, history, categories = meta["iteration"], list(meta["history"]), dict(meta["categories"])
    apply_resume(meta, "human reviewed the diff and wants two more loop attempts")
    check("resume clears halt", not meta["halted"] and meta["halt_reason"] is None)
    check("resume clears the triggering streak", meta["flat_streak"] == 0)
    check("resume preserves iteration", meta["iteration"] == iteration)
    check("resume preserves history", meta["history"] == history)
    check("resume preserves category counts", meta["categories"] == categories)
    check("resume records the ack", len(meta["acks"]) == 1)

    # halted meta refuses new trials
    meta = fresh(1230)
    meta["halted"], meta["halt_reason"] = True, "test"
    allowed, reason = check_trial(meta, "types")
    check("halted meta refuses trials", not allowed and "halted" in reason)

    # 7. score 0 halts as a match, without restoring
    meta = fresh(1230)
    result = apply_build_result(meta, True, 0, 5800)
    check("match halts", result["halt_kind"] == "match" and not result["restore"])

    # 8. build budget
    meta = fresh(1230)
    meta["iteration"] = BUILD_BUDGET - 1
    result = apply_build_result(meta, True, 1200, 5800)
    check("budget halt at limit", result["halt_kind"] == "budget")

    # 9. score >= max_score warns about diff_label
    meta = fresh(None)
    result = apply_build_result(meta, True, 5800, 5800)
    check("max_score warns", any("diff_label" in w for w in result["warn"]))

    # 10. slug parsing
    check("slug from url", slug_of("https://decomp.me/scratch/jgiaZ") == "jgiaZ")
    check("slug from www url", slug_of("https://www.decomp.me/scratch/i8JOn/") == "i8JOn")
    check("bare slug", slug_of("jgiaZ") == "jgiaZ")

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print("  %s  %s" % ("PASS" if ok else "FAIL", name))
    print("\n%d checks, %d failed" % (len(checks), len(failed)))
    raise SystemExit(1 if failed else 0)


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="bounded decomp.me harness with enforced tripwires")
    sub = parser.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("pull"); q.add_argument("slug"); q.add_argument("--force", action="store_true"); q.set_defaults(f=cmd_pull)
    q = sub.add_parser("trial", help="declare the ONE hypothesis the next build tests")
    q.add_argument("text"); q.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    q.add_argument("--expect", required=True); q.set_defaults(f=cmd_trial)
    q = sub.add_parser("categories"); q.set_defaults(f=cmd_categories)
    q = sub.add_parser("build"); q.add_argument("-n", type=int, default=12); q.add_argument("--src", action="store_true"); q.set_defaults(f=cmd_build)
    q = sub.add_parser("diff"); q.add_argument("-n", type=int, default=12); q.add_argument("--at"); q.add_argument("--src", action="store_true"); q.set_defaults(f=cmd_diff)
    q = sub.add_parser("hist"); q.set_defaults(f=cmd_hist)
    q = sub.add_parser("target"); q.add_argument("-n", type=int, default=60); q.set_defaults(f=cmd_target)
    q = sub.add_parser("ctx"); q.add_argument("pattern"); q.add_argument("-n", type=int, default=25); q.add_argument("--block", type=int, default=0); q.set_defaults(f=cmd_ctx)
    q = sub.add_parser("family"); q.add_argument("--get"); q.set_defaults(f=cmd_family)
    q = sub.add_parser("revert"); q.set_defaults(f=cmd_revert)
    q = sub.add_parser("resume"); q.add_argument("--ack", required=True); q.add_argument("--category", choices=sorted(CATEGORIES)); q.set_defaults(f=cmd_resume)
    q = sub.add_parser("log"); q.add_argument("text"); q.set_defaults(f=cmd_log)
    q = sub.add_parser("status"); q.set_defaults(f=cmd_status)
    q = sub.add_parser("selftest"); q.set_defaults(f=cmd_selftest)
    args = parser.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
