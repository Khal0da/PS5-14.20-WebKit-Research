#!/usr/bin/env python3
"""Offline analyzer for host-beacons.log (JSON lines).

Usage:
    python tools/analyze_beacons.py host-beacons.log
    python tools/analyze_beacons.py host-beacons.log --probe V592
    python tools/analyze_beacons.py host-beacons.log --tail 50
"""
import argparse
import json
import sys
from collections import defaultdict, OrderedDict


def load(path):
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def summarize(entries, probe_filter=None):
    by_probe = defaultdict(list)
    for e in entries:
        by_probe[e.get("probe") or "---"].append(e)

    if probe_filter:
        by_probe = {k: v for k, v in by_probe.items() if k == probe_filter}

    print("=== Probe summary ===")
    for probe in sorted(by_probe):
        evs = by_probe[probe]
        events = defaultdict(int)
        for e in evs:
            events[e.get("event", "?")] += 1
        seqs = [e.get("seq") for e in evs if e.get("seq") is not None]
        gaps = []
        if seqs:
            s = sorted(seqs)
            for a, b in zip(s, s[1:]):
                if b - a > 1:
                    gaps.append((a, b))
        print(f"\n{probe}: {len(evs)} beacons")
        for ev, n in sorted(events.items()):
            print(f"  {ev}: {n}")
        if gaps:
            print(f"  seq gaps: {gaps}")
        # show last data payload
        last = evs[-1]
        body = last.get("body", "")
        if body:
            print(f"  last body: {body[:200]}")

    # timeline of unique (probe,event) in order
    print("\n=== Timeline (first occurrence) ===")
    seen = OrderedDict()
    for e in entries:
        key = (e.get("probe"), e.get("event"))
        if key not in seen:
            seen[key] = e.get("t")
    for (p, ev), t in seen.items():
        print(f"  {t}  {p}  {ev}")

    # reload detection: count BOOT events per probe (each BOOT = new run/page load)
    print("\n=== Run counts (BOOT events per probe) ===")
    runs = defaultdict(int)
    for e in entries:
        if e.get("event", "").startswith("BOOT"):
            runs[e.get("probe") or "---"] += 1
    for p in sorted(runs):
        print(f"  {p}: {runs[p]} run(s)")

    # crash detection: seq gaps
    print("\n=== Crash detection (seq gaps > 1) ===")
    all_seqs = sorted(e.get("seq") for e in entries if e.get("seq") is not None)
    gaps = [(a, b) for a, b in zip(all_seqs, all_seqs[1:]) if b - a > 1]
    if gaps:
        for a, b in gaps:
            print(f"  gap {a}->{b} (lost {b - a - 1} beacons)")
    else:
        print("  no gaps")


def main():
    ap = argparse.ArgumentParser(description="Analyze host-beacons.log")
    ap.add_argument("log", help="path to host-beacons.log")
    ap.add_argument("--probe", help="filter to a single probe id")
    ap.add_argument("--tail", type=int, help="only analyze last N entries")
    args = ap.parse_args()

    entries = load(args.log)
    if args.tail:
        entries = entries[-args.tail:]
    if not entries:
        print("No entries found.", file=sys.stderr)
        sys.exit(1)
    summarize(entries, args.probe)


if __name__ == "__main__":
    main()
