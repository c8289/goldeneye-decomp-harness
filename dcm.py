#!/usr/bin/env python3
"""Bounded decomp.me API harness for GoldenEye/Perfect Dark scratches."""

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
               "User-Agent": "dcm-harness/2.0"}
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


def load_meta():
    if not os.path.exists(META):
        die("no meta.json here - run './dcm.py pull <slug>' first")
    with open(META) as f:
        return json.load(f)


def save_meta(meta):
    with open(META, "w") as f:
        json.dump(meta, f, indent=1)


def git(*args):
    subprocess.run(["git", *args], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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


def cmd_pull(args):
    scratch = _req("%s/scratch/%s" % (API, args.slug))
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
    meta["best_score"] = old.get("best_score")
    meta["iteration"] = old.get("iteration", 0)
    meta["history"] = old.get("history", [])
    save_meta(meta)
    if not os.path.exists(LOG):
        with open(LOG, "w") as f:
            f.write("# %s (%s)\n\ntarget: %s   %s %s\n\n" % (
                meta["name"], args.slug, meta["diff_label"],
                meta["compiler"], meta["compiler_flags"]))
    if not os.path.isdir(".git"):
        git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "baseline")
    print("scratch   %s  [%s]" % (meta["name"], args.slug))
    print("platform  %s   compiler %s   preset %s" %
          (meta["platform"], meta["compiler"], meta["preset"]))
    print("flags     %s" % meta["compiler_flags"])
    print("label     %s      <-- DO NOT rename this function" % meta["diff_label"])
    print("src.c     %d lines" % (open(SRC_FILE).read().count("\n") + 1))
    print("ctx.h     %d bytes  <-- NEVER read this file, use './dcm.py ctx <regex>'" %
          os.path.getsize(CTX_FILE))
    print("published score %s / max %s" % (meta["score"], meta["max_score"]))


def cmd_build(args):
    meta = load_meta()
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
    meta["iteration"] += 1
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
    if not response.get("success"):
        with open(FAIL, "w") as f:
            json.dump(response, f)
        save_meta(meta)
        print("BUILD FAILED  (iteration %d, %.1fs)" % (meta["iteration"], elapsed))
        for error in errors[:12]:
            print("   " + error)
        if not errors:
            print("   " + output[:400])
        print("\nFix the build. Do not reason about codegen yet.")
        raise SystemExit(1)
    with open(LAST, "w") as f:
        json.dump(response, f)
    diff = response["diff_output"]
    score, maximum, rows = diff["current_score"], diff["max_score"], diff["rows"]
    best = meta.get("best_score")
    meta.setdefault("history", []).append(score)
    meta["history"] = meta["history"][-40:]
    verdict = "same"
    if best is None or score < best:
        meta["best_score"] = score
        shutil.copy(SRC_FILE, BEST_FILE)
        git("add", "-A")
        git("commit", "-qm", "iter %d score %d" % (meta["iteration"], score))
        verdict = "IMPROVED"
    elif score > best:
        verdict = "REGRESSED"
    save_meta(meta)
    print("SCORE %d / max %d   best %s   [%s]  iter %d  %.1fs" %
          (score, maximum, meta["best_score"], verdict, meta["iteration"], elapsed))
    if score == 0:
        print("*** MATCH *** - stop editing. Do not save or fork without approval.")
        return
    print("\ndifference categories:")
    print_hist(histogram(rows), len(rows))
    lines, count = render(rows, args.n, show_src=args.src)
    print("\nfirst %d of %d divergences (target | ours):" % (min(args.n, count), count))
    for line in lines:
        print(line)
    if verdict == "REGRESSED":
        print("\nREGRESSION. Run './dcm.py revert' before your next hypothesis.")


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
                for j in range(index, min(len(lines), index + args.block)):
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
        scratch = _req("%s/scratch/%s" % (API, args.get))
        filename = "sib_%s.c" % args.get
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
    shutil.copy(BEST_FILE, SRC_FILE)
    print("src.c restored from best.c (score %s)" % load_meta().get("best_score"))


def cmd_log(args):
    meta = load_meta()
    with open(LOG, "a") as f:
        f.write("- #%d [%s] %s\n" % (meta["iteration"], meta.get("best_score"), args.text))
    print("logged")


def cmd_status(_args):
    meta = load_meta()
    print("%s [%s]  label %s" % (meta["name"], meta["slug"], meta["diff_label"]))
    print("iteration %d   best %s / %s" %
          (meta["iteration"], meta.get("best_score"), meta["max_score"]))
    history = meta.get("history", [])[-15:]
    if history:
        print("history   " + " ".join(str(x) for x in history))
    if os.path.exists(LOG):
        with open(LOG) as f:
            print("\n".join(f.read().splitlines()[-10:]))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("pull"); q.add_argument("slug"); q.add_argument("--force", action="store_true"); q.set_defaults(f=cmd_pull)
    q = sub.add_parser("build"); q.add_argument("-n", type=int, default=12); q.add_argument("--src", action="store_true"); q.set_defaults(f=cmd_build)
    q = sub.add_parser("diff"); q.add_argument("-n", type=int, default=12); q.add_argument("--at"); q.add_argument("--src", action="store_true"); q.set_defaults(f=cmd_diff)
    q = sub.add_parser("hist"); q.set_defaults(f=cmd_hist)
    q = sub.add_parser("target"); q.add_argument("-n", type=int, default=60); q.set_defaults(f=cmd_target)
    q = sub.add_parser("ctx"); q.add_argument("pattern"); q.add_argument("-n", type=int, default=25); q.add_argument("--block", type=int, default=0); q.set_defaults(f=cmd_ctx)
    q = sub.add_parser("family"); q.add_argument("--get"); q.set_defaults(f=cmd_family)
    q = sub.add_parser("revert"); q.set_defaults(f=cmd_revert)
    q = sub.add_parser("log"); q.add_argument("text"); q.set_defaults(f=cmd_log)
    q = sub.add_parser("status"); q.set_defaults(f=cmd_status)
    args = parser.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()