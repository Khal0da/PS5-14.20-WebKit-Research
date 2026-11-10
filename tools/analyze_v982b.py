#!/usr/bin/env python3
"""V982B analyzer - APNG 321753 OOB stability gate (G1 within-load, G3 cross-load).

This tool NEVER claims a pointer leak by itself. It only answers:
  G1: did any fixed OOB offset repeat the exact same 8 bytes across all iterations
      in a load (with valid in-frame controls)?
  G3: did any (window,row,x) key repeat the exact same qword in >=2 loads?
  G2: only SHAPE flags (canonical/non-canonical, known libWebKit range) - independent
      corroboration is still required before calling anything a pointer read.

Usage:
    python tools/analyze_v982b.py v982b-beacons.txt
    python tools/analyze_v982b.py host-beacons.log --probe V982B --min-runs 2
    python tools/analyze_v982b.py v982b-beacons.txt --json

Accepts:
  - text extracts:   HH:MM:SS | STABLE | run|name|yN|xN|QWORD|c=..|known=..|pg=..
  - JSONL beacons:   {"probe":"V982B","event":"STABLE","body":"run|name|..."}
"""
import argparse
import json
import re
import sys
import urllib.parse
from collections import defaultdict

TEXT_RE = re.compile(r"^\d{2}:\d{2}:\d{2}\s*\|\s*([^|]+?)\s*\|\s*(.*)$")

# Known allocator/decoder filler patterns observed in the APNG 321753 OOB window.
# These are NOT addresses: 00aeaeaf/aeaeaeaf is uninitialized-pattern filler and
# 0000ee3f is a float constant (0.465...) that recurs across unrelated slots.
FILLER_EXACT = {
    "0000000000000000",
    "000000000000ee3f",
    "00ff00ff00ff00ff",
    "ff0000ffff0000ff",
}
FILLER_SUBSTRINGS = ("aeaeaf", "aeaeaee5", "0000ee3f")


def is_filler(q):
    if q in FILLER_EXACT:
        return True
    return any(s in q for s in FILLER_SUBSTRINGS)


def parse(path, probe="V982B"):
    events = []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = TEXT_RE.match(line)
            if m:
                events.append({"event": m.group(1).strip(), "body": m.group(2).strip(), "probe": probe})
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(e.get("probe", "")).find(probe) < 0:
                continue
            # host.py may leave the query string inside "event" and keep the
            # payload in "path" (?d=...). Normalize both for analysis.
            event = str(e.get("event", "")).split("?", 1)[0]
            body = str(e.get("body", "") or "")
            if not body:
                path = str(e.get("path", ""))
                qs = urllib.parse.urlparse(path).query
                body = (urllib.parse.parse_qs(qs).get("d") or [""])[0]
            events.append({"event": event, "body": body, "probe": probe})
    return events


def split_events(events):
    out = defaultdict(list)
    for e in events:
        out[str(e.get("event", ""))].append(str(e.get("body", "")))
    return out


def parse_stable(body):
    """run|name|yN|xN|q|c=..|known=..|pg=.. (multiple entries separated by ';')."""
    entries = []
    for part in body.split(";"):
        f = part.split("|")
        if len(f) < 5:
            continue
        run, name, y, x, q = f[0], f[1], f[2], f[3], f[4]
        if not re.match(r"^[0-9a-f]{16}$", q):
            continue
        flags = {}
        for extra in f[5:]:
            if "=" in extra:
                k, v = extra.split("=", 1)
                flags[k] = v
        if flags.get("c") == "f" or flags.get("c") == "k" or q == "0000000000000000":
            continue
        # Defensive: older probe builds shipped aeaeaf/0000ee3f as c=n. Never
        # let filler reach the G1/G3 matcher regardless of upstream flags.
        if is_filler(q):
            continue
        entries.append({
            "run": run,
            "key": name + "|" + y + "|" + x,
            "q": q,
            "cls": flags.get("c", "?"),
            "known": flags.get("known", "0") == "1",
            "pg": flags.get("pg", "0") == "1",
        })
    return entries


def parse_ctrl(body):
    """run|ok=N|bad=N[|badlist] -> (run, ok, bad)."""
    f = body.split("|")
    run = f[0] if f else "?"
    ok = bad = 0
    for part in f[1:]:
        if part.startswith("ok="):
            ok = int(part[3:] or 0)
        elif part.startswith("bad="):
            bad = int(part[4:] or 0)
    return run, ok, bad


def main():
    ap = argparse.ArgumentParser(description="V982B APNG OOB stability gate analyzer")
    ap.add_argument("log", help="beacon log (text extract or JSONL)")
    ap.add_argument("--probe", default="V982B", help="probe id filter (default V982B)")
    ap.add_argument("--min-runs", type=int, default=2, help="runs required for a G3 match (default 2)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    events = parse(args.log, args.probe)
    if not events:
        print("No V982B events found.", file=sys.stderr)
        return 1

    by_ev = split_events(events)
    run_ctrl = {}
    for body in by_ev.get("CTRL", []):
        run, ok, bad = parse_ctrl(body)
        prev = run_ctrl.get(run, (0, 0))
        run_ctrl[run] = (prev[0] + ok, prev[1] + bad)

    stable = []
    for body in by_ev.get("STABLE", []):
        stable.extend(parse_stable(body))

    runs = sorted({e["run"] for e in stable} | set(run_ctrl))
    per_run = defaultdict(dict)  # run -> key -> entry
    for e in stable:
        per_run[e["run"]][e["key"]] = e

    # G1 per run: any stable offset + valid control.
    g1 = {}
    for run in runs:
        ok, bad = run_ctrl.get(run, (0, 0))
        valid = ok > 0 and bad == 0
        n = len(per_run.get(run, {}))
        g1[run] = "PASS" if (valid and n > 0) else ("INVALID" if not valid else "FAIL")

    # G3: same key + same qword in >= min_runs distinct runs.
    keys = sorted({k for r in per_run for k in per_run[r]})
    matches = []
    for key in keys:
        vals = defaultdict(list)
        for run in runs:
            e = per_run.get(run, {}).get(key)
            if e:
                vals[e["q"]].append(run)
        for q, rlist in vals.items():
            if len(rlist) >= args.min_runs:
                e = next(per_run[r][key] for r in rlist if key in per_run[r])
                matches.append({
                    "key": key,
                    "q": q,
                    "runs": sorted(rlist),
                    "cls": e["cls"],
                    "known": e["known"],
                    "pg": e["pg"],
                })
    matches.sort(key=lambda m: (-len(m["runs"]), m["cls"] != "c", m["key"]))

    summary = {
        "runs": runs,
        "g1": g1,
        "g3_matches": matches,
        "g3_pass": bool(matches),
        "stable_counts": {r: len(per_run.get(r, {})) for r in runs},
        "ctrl": {r: {"ok": v[0], "bad": v[1]} for r, v in run_ctrl.items()},
    }

    any_g1 = any(v == "PASS" for v in g1.values())
    canon_matches = [m for m in matches if m["cls"] == "c"]
    if not any_g1:
        verdict = "NO-G1 (no stable non-filler offset with valid controls)"
    elif not matches:
        verdict = "G1-ONLY (stable within a load, not across loads; NOT a leak)"
    elif not canon_matches:
        verdict = "G3-STABLE-NONCANON (cross-load stable but non-canonical; NOT a pointer read)"
    else:
        verdict = "G1+G3 SHAPE-CANDIDATE (still requires independent G2 corroboration; NOT a proven leak)"
    summary["verdict"] = verdict

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print("=== V982B: APNG OOB stability gate ===")
    print("runs: " + (", ".join(runs) if runs else "(none)"))
    for run in runs:
        c = summary["ctrl"].get(run, {"ok": 0, "bad": 0})
        print(f"  {run}: G1={g1.get(run, '?')} stable={summary['stable_counts'].get(run, 0)} ctrl(ok/bad)={c['ok']}/{c['bad']}")
    print()
    if matches:
        print(f"Cross-load matches (same key+qword in >= {args.min_runs} runs):")
        for m in matches[:40]:
            flags = f"class={m['cls']} knownRange={int(m['known'])} pageAligned={int(m['pg'])}"
            print(f"  {m['key']} = {m['q']}  runs={','.join(m['runs'])}  {flags}")
        if len(matches) > 40:
            print(f"  ... {len(matches) - 40} more")
    else:
        print("Cross-load matches: none")
    print()
    print("G2 status: PARTIAL only (shape/range flags). Independent corroboration is required.")
    print("VERDICT: " + verdict)
    print()
    print("Reminder: G1/G3 stability is necessary, not sufficient. Do not forge m_stateStack or")
    print("report a pointer leak unless G1+G3 pass AND G2 is independently corroborated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
