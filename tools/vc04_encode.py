#!/usr/bin/env python3
"""VC-04 crash-diagnostics encoder (PS5 14.20, diagnostic only).

Encodes inferred crashes (beacon windows) together with native diagnostics
(klog snapshot / crash dump text) into a structured, timestamp-linked record,
then optionally attributes the fault to WebKit-1400 source paths.

Subcommands:
  windows    Parse a beacon log (JSONL or pipe-extract) -> crash windows JSON/MD.
  capture    Snapshot /dev/klog on the PS5 via tools/send.py + payloads/klog.js.
  correlate  Merge beacon windows + klog crash records -> encoded VC-04 record.
  attribute  Match a stack/PC against the WebKit-1400 candidate table.

Examples:
  python tools/vc04_encode.py windows results/beacon-logs/p0-2026-11-08/v923h-beacons.txt --out results/vc04/v923h-windows.json
  python tools/vc04_encode.py capture --host 192.168.1.10 --out results/vc04/runs/20261109-a
  python tools/vc04_encode.py correlate --beacons v923h-beacons.txt --klog results/vc04/runs/20261109-a/klog-snapshot.txt --case v923h-dc-save
  python tools/vc04_encode.py attribute --stackfile results/vc04/runs/20261109-a/stack.txt

Policy: diagnostic evidence encoding only. No exploit development, no
primitive/impact claims from stacks without separate (VC-06) evidence.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.parse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "vc04-encoded-crash-record/1"

# --------------------------------------------------------------------------
# Beacon parsing
# --------------------------------------------------------------------------

# Probe id: letter + digits + optional suffix (V923H, V928B, V973, V925...).
PROBE_ID = r"[A-Za-z]\d+[A-Za-z0-9]*"
# Pipe extract format: "19:22:53 | V923H-SAVE-PRE | stage=save200,try=1,..."
PIPE_RE = re.compile(r"^(?:\[?(\d\d:\d\d:\d\d)\]?)?\s*\|\s*(%s)-([A-Z0-9\-]+)\s*\|\s*(.*)$" % PROBE_ID)
# Tag with a second dash, e.g. "V923H-SAVE-PRE" -> step SAVE, phase PRE.
# The probe prefix is versioned ("V923H"), event is the rest (dashes allowed).
PROBE_EVENT_RE = re.compile(r"^(%s)-([A-Z0-9\-]+)$" % PROBE_ID)

EVENT_RE = re.compile(r"^([A-Z0-9]+?)-?(PRE|POST|OK|ERR)?$")

# Events that close a window from the right (step survived / run moved on).
SURVIVOR_EVENTS = {"POST", "OK", "CANARY", "SCAN", "AFTER", "SLOT", "LEAK",
                   "NOWRITE", "NOSLOT", "ADV", "DONE", "ALIVE1", "ALIVE3",
                   "CLEAR", "CONTROL", "CALLERR"}

CRASH_EVENTS = {"CRASH", "BLACKLIST", "GIVEUP"}


def load_beacons(path):
    """Return entries as dicts {t, iso, probe, event, body}. Supports JSONL and
    pipe-extract logs (results/beacon-logs/...)."""
    entries = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("rows:"):
                continue
            if line.startswith("{"):
                try:
                    j = json.loads(line)
                except json.JSONDecodeError:
                    continue
                probe = j.get("probe")
                event = j.get("event") or ""
                body = j.get("body", "") or ""
                # host.py stores event as remainder including query (e.g. "PRE?d=...");
                # and older host.py kept suffixed probes in event with probe=None.
                if "?" in event:
                    event_core, q = event.split("?", 1)
                    if not body:
                        try:
                            body = urllib.parse.unquote_plus(dict(urllib.parse.parse_qsl(q)).get("d", ""))
                        except Exception:
                            body = q
                    event = event_core
                if not probe:
                    m = PROBE_EVENT_RE.match(event)
                    if m:
                        probe, event = m.group(1), m.group(2)
                    else:
                        continue
                entries.append({
                    "t": j.get("t", ""),
                    "iso": j.get("ts", ""),
                    "probe": probe,
                    "event": event or "",
                    "body": body,
                    "raw": line,
                })
                continue
            m = PIPE_RE.match(line)
            if not m:
                continue
            t, probe, event, body = m.groups()
            entries.append({"t": t, "iso": "", "probe": probe,
                            "event": event, "body": body, "raw": line})
    return entries


def step_of(event, body=""):
    """'<STEP>-PRE' -> '<STEP>'; 'PRE' with body call=save -> 'SAVE'; else token."""
    ev = (event or "").upper()
    for suf in ("-PRE", "-POST", "-OK", "-ERR"):
        if ev.endswith(suf):
            return ev[:-len(suf)] or "?"
    if ev in ("PRE", "POST", "OK", "ERR"):
        m = re.search(r"call=([A-Za-z0-9_]+)", body or "")
        if m:
            return m.group(1).upper()
        m = re.search(r"mode=([A-Za-z0-9_]+)", body or "")
        if m:
            return m.group(1).upper()
    return re.match(r"^([A-Z0-9]+)", ev).group(1) if re.match(
        r"^[A-Z0-9]+", ev) else (ev or "?")


def compute_windows(entries, probe=None):
    """For each PRE beacon, window = [PRE, next event]. Classify outcome.
    Additionally, bind CRASH events to the PRE they belong to (via the pending
    marker's step when parseable)."""
    out = []
    if probe:
        entries = [e for e in entries if e.get("probe") == probe]
    for i, e in enumerate(entries):
        ev = e["event"]
        if not (ev == "PRE" or ev.endswith("PRE")):
            continue
        step = step_of(ev, e.get("body",""))
        nxt = entries[i + 1] if i + 1 < len(entries) else None
        nxt_ev = nxt["event"] if nxt else "EOF"
        nxt_step = step_of(nxt_ev, nxt.get("body","") if nxt else "")
        nxt_core = nxt_ev if nxt_ev in ("POST","OK","CLEAR","ALIVE1","ALIVE3") else (nxt_ev.split("-")[-1] if "-" in nxt_ev else nxt_ev)
        if nxt_step in CRASH_EVENTS or nxt_ev in CRASH_EVENTS:
            outcome = "crash-or-reload-after-pre"
        elif nxt_ev == "POST" or nxt_ev.endswith("POST") or nxt_ev in ("OK","CLEAR","ALIVE1","ALIVE3") or nxt_core in SURVIVOR_EVENTS:
            outcome = "survived" if nxt_ev in ("POST","OK","CLEAR","ALIVE1","ALIVE3") or nxt_ev.endswith("POST") else "post-step-survivor"
        elif nxt_ev in ("BOOT","ENV","RESET"):
            outcome = "no-post-no-crash-marker"
        else:
            outcome = "unknown-next:%s" % nxt_ev
        out.append({
            "probe": e["probe"], "step": step, "t_pre": e["t"],
            "iso_pre": e["iso"] or None,
            "body_pre": e["body"],
            "next_event": nxt_ev, "t_next": nxt["t"] if nxt else None,
            "iso_next": (nxt["iso"] or None) if nxt else None,
            "body_next": nxt["body"] if nxt else "",
            "outcome": outcome,
        })
    # Bind CRASH markers to the latest preceding PRE of the same step.
    pending_step_re = re.compile(r"pending=([A-Za-z0-9_]+):([A-Za-z0-9_]+)")
    crashes = []
    last_pre = {}
    for e in entries:
        ev = e["event"]
        if ev.endswith("PRE"):
            last_pre[ev[:-4]] = e
        if ev in ("CRASH", "BLACKLIST"):
            m = pending_step_re.search(e["body"])
            bound = None
            if m:
                bound = last_pre.get(m.group(2))
            elif step_of(ev) in last_pre:
                bound = last_pre[step_of(ev)]
            crashes.append({
                "probe": e["probe"], "event": ev, "t": e["t"],
                "iso": e["iso"] or None, "body": e["body"],
                "bound_pre": {
                    "step": bound["event"][:-4] if bound else None,
                    "t_pre": bound["t"] if bound else None,
                    "body_pre": bound["body"] if bound else None,
                } if bound else None,
            })
    return out, crashes


def windows_summary(entries, probe):
    wins, crashes = compute_windows(load_beacons(entries), probe)
    pre_steps = {}
    for w in wins:
        key = w["step"]
        pre_steps.setdefault(key, {"pre": 0, "crash_after": 0, "survived": 0})
        pre_steps[key]["pre"] += 1
        if w["outcome"].startswith("crash"):
            pre_steps[key]["crash_after"] += 1
        elif w["outcome"] != "no-post-no-crash-marker":
            pre_steps[key]["survived"] += 1
    return {
        "beacon_file": entries,
        "probe": probe or "(all)",
        "n_events": len(wins) + sum(1 for c in crashes),
        "windows": wins,
        "crashes": crashes,
        "per_step": pre_steps,
    }


# --------------------------------------------------------------------------
# klog parsing
# --------------------------------------------------------------------------

EXCEEDED_SIGNALS = {
    1: "SIGHUP", 2: "SIGINT", 3: "SIGQUIT", 4: "SIGILL", 5: "SIGTRAP",
    6: "SIGABRT", 7: "SIGEMT", 8: "SIGFPE", 9: "SIGKILL", 10: "SIGBUS",
    11: "SIGSEGV", 12: "SIGSYS", 13: "SIGPIPE", 14: "SIGALRM", 15: "SIGTERM",
}

EXITED_RE = re.compile(
    r"pid\s+(\d+)\s*\(([^)]*)\)(?:, uid\s+(\d+))?:\s*"
    r"(?:exited on|received) signal\s+(\d+)(?:\s*\(([^)]*)\))?", re.I)
UPTIME_RE = re.compile(r"^\[\s*(\d+\.\d+)\]\s*")
FAULTY_RE = re.compile(
    r"(segv|segfault|page fault|fault|trap|fatal|panic|assert|"
    r"\bpc\b|\blr\b|\bfar\b|\besr\b|\bdfsc\b|\bifsc\b|data abort|"
    r"instruction abort)", re.I)
WEBKIT_RE = re.compile(r"(webkit|webproc|webprocnp|netproc|webcontent|"
                       r"webkitnetwork|webkitweb)", re.I)


def parse_klog(path):
    """Extract crash-relevant records from a klog/crash-dump text file."""
    records, relevant = [], []
    prio_re = re.compile(r"^<\d+>\s*")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for n, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            content0 = prio_re.sub("", line)
            up = UPTIME_RE.match(content0)
            uptime = up.group(1) if up else None
            content = content0[up.end():] if up else content0
            m = EXITED_RE.search(content)
            if m:
                sig = int(m.group(4))
                records.append({
                    "line": n, "kind": "process-exit-signal",
                    "pid": int(m.group(1)), "proc": m.group(2),
                    "uid": int(m.group(3)) if m.group(3) else None,
                    "signal": sig, "signal_name": EXCEEDED_SIGNALS.get(sig, "SIG?%d" % sig),
                    "extra": m.group(5), "uptime": uptime, "text": line[:400],
                })
                continue
            if FAULTY_RE.search(content) or WEBKIT_RE.search(content):
                relevant.append({"line": n, "uptime": uptime, "text": line[:400]})
                if re.search(r"(trap|abort|fault)", content, re.I) and re.search(
                        r"(webkit|webproc|0x[0-9a-f]{4,})", content, re.I):
                    records.append({"line": n, "kind": "fault-ish",
                                    "uptime": uptime, "text": line[:400]})
    return {"file": path, "records": records, "relevant_lines": relevant}


# --------------------------------------------------------------------------
# WebKit-1400 candidate attribution table (static, from WebKit_1400_src/)
# --------------------------------------------------------------------------

CANDIDATES = [
    {"name": "CanvasRenderingContext2DBase::save()",
     "aliases": ["save()"],
     "source": "WebKit_1400_src/CanvasRenderingContext2DBase.h:143",
     "code": "void save() { ++m_unrealizedSaveCount; }",
     "mechanism": "inline, NON-virtual; single increment of a member of the "
                  "context object. Crash here implies: (a) the call never "
                  "reached it (dispatch/cast above), or (b) write to freed/"
                  "decommitted memory (IsoHeap decommit), or (c) crash is "
                  "actually after save (scan/beacon) - excluded in V973 "
                  "default run.",
     "fault_class": "SIGSEGV (unmapped write) or crash in caller frames"},
    {"name": "JS binding trampoline for save (generated JSCanvas*.cpp)",
     "aliases": ["savecallback", "castthisvalue", "jsdynamiccast"],
     "source": "generated bindings (not in extracted subset)",
     "code": "castThisValue<CanvasRenderingContext2D> + impl.save()",
     "mechanism": "jsDynamicCast/cast on the JS wrapper then direct call. "
                  "Wrapper is a live JS object; a crash here suggests "
                  "confused wrapper->impl state rather than stack damage.",
     "fault_class": "SIGSEGV near null / dispatch"},
    {"name": "CanvasRenderingContext2DBase::realizeSaves()",
     "aliases": ["realizesaves(", "realizesaves()"],
     "source": "WebKit_1400_src/CanvasRenderingContext2DBase.cpp:433",
     "mechanism": "gate for realizeSavesLoop(); reads m_unrealizedSaveCount; "
                  "console-message path touches scriptExecutionContext() on "
                  "the canvas base object.",
     "fault_class": "SIGSEGV on freed base/canvas refs"},
    {"name": "CanvasRenderingContext2DBase::realizeSavesLoop()",
     "aliases": ["realizesavesloop"],
     "source": "WebKit_1400_src/CanvasRenderingContext2DBase.cpp:445-457",
     "code": "m_stateStack.append(state()); context->save();",
     "mechanism": "state() = m_stateStack.last() (deref of stack tail); "
                  "Vector<State,1> append may copy State and/or grow buffer; "
                  "context->save() virtual on GraphicsContext (drawingContext()).",
     "fault_class": "SIGSEGV in Vector append / State copy / virtual save"},
    {"name": "CanvasRenderingContext2DBase::restore()",
     "aliases": ["restore(", "restoreimplementation"],
     "source": "WebKit_1400_src/CanvasRenderingContext2DBase.cpp:459-476",
     "mechanism": "m_path.transform(state().transform), removeLast, "
                  "drawingContext()->restore() virtual.",
     "fault_class": "SIGSEGV on m_path/state stack"},
    {"name": "CanvasPath::beginPath / Path::clear (Cairo)",
     "aliases": ["beginpath", "path::clear", "canvaspath::"],
     "source": "WebKit_1400_src/CanvasPath.* , PathCairo.cpp",
     "mechanism": "V923C bp-nospray crashed with NO reclaim at all -> "
                  "purest UAF shape: stale 2D context ref after free; "
                  "m_path/platform path deref on freed object.",
     "fault_class": "SIGSEGV in Path/Cairo dtor or clear"},
    {"name": "CanvasRenderingContext2DBase dtor (m_stateStack teardown)",
     "aliases": ["~canvasrenderingcontext2dbase"],
     "source": "WebKit_1400_src/CanvasRenderingContext2DBase.cpp:241",
     "mechanism": "dtor iterates m_stateStack; #59 noted AB reclaim can zero "
                  "slot -> destructor-side crash if freed/reclaimed context "
                  "is destroyed late (GC sweep), not at the JS call site.",
     "fault_class": "SIGSEGV in Vector dtor / Ref releases"},
    {"name": "HTMLCanvasElement::getContext (dict conversion / replace m_context)",
     "aliases": ["::getcontext"],
     "source": "WebKit_1400_src/HTMLCanvasElement.cpp",
     "mechanism": "H1b: bitmaprenderer request can replace/free the getter-"
                  "created 2D context while a JS ref remains (trigger side).",
     "fault_class": "n/a (lifetime origin, not fault site)"},
    {"name": "WTF::Vector append/removeLast (m_stateStack backing)",
     "aliases": ["wt::vector", "vector<", "vector::append", "removelast"],
     "source": "WTF (headers; not in extracted subset)",
     "mechanism": "state-stack buffer growth/shrink on a corrupted Vector "
                  "(freed/reclaimed object) -> buffer pointer or capacity "
                  "garbage; CrashOnOverflow-style traps if compiled in.",
     "fault_class": "SIGSEGV/SIGTRAP in Vector ops"},
]


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------

def cmd_windows(args):
    res = windows_summary(args.beacons, args.probe)
    text = json.dumps(res, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        md = args.out.rsplit(".", 1)[0] + ".md"
        with open(md, "w", encoding="utf-8") as f:
            f.write("# Crash windows — %s (%s)\n\n" % (res["probe"], res["beacon_file"]))
            f.write("| step | t(PRE) | next | t(next) | outcome |\n|---|---|---|---|---|\n")
            for w in res["windows"]:
                f.write("| %s | %s | %s | %s | %s |\n" % (
                    w["step"], w["t_pre"], w["next_event"], w["t_next"] or "-", w["outcome"]))
            f.write("\n## Crash markers\n\n")
            for c in res["crashes"]:
                f.write("- `%s` %s %s (bound PRE: %s @ %s)\n" % (
                    c["event"], c["t"], c["body"][:120],
                    (c["bound_pre"] or {}).get("step") or "?",
                    (c["bound_pre"] or {}).get("t_pre") or "?"))
        print("[+] wrote %s and %s" % (args.out, md))
    print(json.dumps(res["per_step"], indent=2))
    print("[+] windows: %d, crash markers: %d" % (len(res["windows"]), len(res["crashes"])))
    return 0


def cmd_capture(args):
    outdir = os.path.abspath(args.out)
    os.makedirs(outdir, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    send = os.path.join(REPO_ROOT, "tools", "send.py")
    cmd = [sys.executable, send, args.host, str(args.port),
           os.path.join(REPO_ROOT, "payloads", "klog.js"), "--arg", "raw"]
    if args.grep:
        cmd += ["--arg", "grep=" + args.grep]
    print("[*] sending klog.js snapshot to %s:%d ..." % (args.host, args.port))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
    klog_path = os.path.join(outdir, "klog-snapshot.txt")
    with open(klog_path, "w", encoding="utf-8") as f:
        f.write(proc.stdout)
    if proc.stderr:
        with open(os.path.join(outdir, "capture.stderr.txt"), "w", encoding="utf-8") as f:
            f.write(proc.stderr)
    meta = {
        "captured_at_utc": stamp,
        "host": args.host, "port": args.port,
        "payload": "payloads/klog.js (raw snapshot)",
        "returncode": proc.returncode,
        "note": "Record the DC-ENV/DC-PRE beacon wall-clock of the crashing run "
                "here: host_clock_at_PRE = HH:MM:SS.mmm (from beacon terminal/log).",
        "host_clock_at_capture_utc": stamp,
    }
    with open(os.path.join(outdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    n_lines = sum(1 for _ in open(klog_path, encoding="utf-8", errors="replace"))
    print("[+] klog snapshot: %s (%d lines)" % (klog_path, n_lines))
    print("[+] next: python tools/vc04_encode.py correlate --beacons <beacon-log> "
          "--klog %s --case <case-id>" % klog_path)
    return 0 if proc.returncode == 0 else 1


def cmd_correlate(args):
    wins = windows_summary(args.beacons, args.probe)
    klog = parse_klog(args.klog) if os.path.exists(args.klog) else {"file": args.klog,
                                                                   "records": [],
                                                                   "relevant_lines": []}
    now = datetime.datetime.now(datetime.timezone.utc)
    crash_records = klog.get("records", [])
    status = "encoded-native" if crash_records else "encoded-beacons-only"
    if crash_records and not any(r.get("kind") == "process-exit-signal" for r in crash_records):
        status = "encoded-native-partial"
    record = {
        "schema": SCHEMA,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "case": args.case,
        "firmware_base": "14.20",
        "webkit_source_ref": "WebKit-1400 OSS (14.00+, covers 14.20) — WebKit_1400_src/",
        "probe": {
            "beacon_log": wins["beacon_file"],
            "probe_filter": wins["probe"],
            "dc_probe": "probes/canvas-uaf/v973-vc04-dc.html (modes: save|bp)",
        },
        "beacon_windows": {
            "per_step": wins["per_step"],
            "windows": wins["windows"],
            "crash_markers": wins["crashes"],
        },
        "klog": klog,
        "attribution": {
            "status": "pending-symbolization",
            "pc": None, "module": None, "offset": None,
            "note": "Run `attribute` subcommand once a symbolized stack or "
                    "module+offset is available.",
        },
        "classification": status,
        "policy": "diagnostic-only; no primitive/impact claims without VC-06 evidence",
    }
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        out = args.out
    else:
        outdir = os.path.join(REPO_ROOT, "results", "vc04")
        os.makedirs(outdir, exist_ok=True)
        out = os.path.join(outdir, "VC04_%s_%s.json" %
                           (args.case, now.strftime("%Y%m%d-%H%M%S")))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    md = out.rsplit(".", 1)[0] + ".md"
    with open(md, "w", encoding="utf-8") as f:
        f.write("# VC-04 encoded crash record — %s\n\n" % args.case)
        f.write("- Generated: %s  \n- Beacon log: `%s` (probe %s)  \n"
                % (record["generated_utc"], wins["beacon_file"], wins["probe"]))
        f.write("- Klog: `%s`  \n- Classification: **%s**  \n\n" % (klog["file"], status))
        f.write("## Per-step outcomes\n\n```\n%s\n```\n\n"
                % json.dumps(wins["per_step"], indent=2))
        if crash_records:
            f.write("## Native crash records (klog)\n\n")
            for r in crash_records:
                f.write("- `%s`\n" % json.dumps(r, ensure_ascii=False)[:400])
        else:
            f.write("## Native crash records (klog)\n\nNone extracted — "
                    "klog snapshot may not contain the crash window "
                    "(ring-buffer overflow?) or capture predates the crash run.\n")
        f.write("\n## Relevant klog lines (webkit/fault keywords)\n\n")
        for rel in klog.get("relevant_lines", [])[:40]:
            f.write("- %s\n" % rel["text"][:200])
        f.write("\n## Attribution\n\nPending symbolization. Candidates: "
                "see `attribute` subcommand (WebKit-1400 table).\n")
    print("[+] record: %s" % out)
    print("[+] summary: %s" % md)
    print("[+] classification: %s (%d klog crash records)" % (status, len(crash_records)))
    return 0


def cmd_attribute(args):
    lines = []
    if args.stackfile and os.path.exists(args.stackfile):
        with open(args.stackfile, "r", encoding="utf-8", errors="replace") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]
    if args.pc:
        lines.append("pc %s" % args.pc)
    if not lines:
        print("[-] nothing to attribute (pass --stackfile and/or --pc)", file=sys.stderr)
        return 1

    print("=== WebKit-1400 candidate table (static) ===")
    for c in CANDIDATES:
        print("\n- %s\n  source: %s\n  fault class: %s\n  mechanism: %s"
              % (c["name"], c["source"], c.get("fault_class", "-"),
                 c["mechanism"][:220]))

    print("\n=== Stack lines (%d) ===" % len(lines))
    matched = []
    for l in lines[:80]:
        low = l.lower()
        best = None  # longest-alias match wins (realizeSavesLoop > realizeSaves > save)
        for c in CANDIDATES:
            for alias in c.get("aliases", []):
                if alias in low and (best is None or len(alias) > len(best[1])):
                    best = (c["name"], alias)
        if best:
            matched.append({"line": l, "candidate": best[0], "alias": best[1]})
            print("[match] %s  ->  %s" % (l[:160], best[0]))
        else:
            print("        %s" % l[:160])
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"schema": SCHEMA, "matched": matched,
                       "candidates": CANDIDATES}, f, indent=2)
        print("[+] wrote %s" % args.out)
    if not matched:
        print("[-] no candidate-name matches; without a 14.20 symbol map, "
              "PC offsets need manual mapping (module symbol table).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("windows", help="compute crash windows from a beacon log")
    w.add_argument("beacons")
    w.add_argument("--probe", default=None)
    w.add_argument("--out", default=None)
    w.set_defaults(func=cmd_windows)

    c = sub.add_parser("capture", help="snapshot /dev/klog on the PS5")
    c.add_argument("--host", required=True)
    c.add_argument("--port", type=int, default=9027)
    c.add_argument("--out", default=None)
    c.add_argument("--grep", default=None)
    c.add_argument("--timeout", type=int, default=180)
    c.set_defaults(func=cmd_capture)

    r = sub.add_parser("correlate", help="encode windows + klog into a VC-04 record")
    r.add_argument("--beacons", required=True)
    r.add_argument("--probe", default=None)
    r.add_argument("--klog", required=True)
    r.add_argument("--case", required=True)
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_correlate)

    a = sub.add_parser("attribute", help="match stack/PC against candidates")
    a.add_argument("--stackfile", default=None)
    a.add_argument("--pc", default=None)
    a.add_argument("--out", default=None)
    a.set_defaults(func=cmd_attribute)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
