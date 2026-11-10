# V982B — APNG OOB Stability Gate (G1/G3) Runbook

**Status:** prepared, **not run** (no device access in this session).  
**Scope:** read-only characterization of the APNG 321753-class OOB window already seen on 14.20.  
**Probe:** `probes/canvas-uaf/v982B-apng-oob-stability.html`  
**Analyzer:** `tools/analyze_v982b.py`

---

## 1) What this probe does — and does not do

It repeats the V947B/V948B window dump at **fixed offsets** across iterations, then reports which 8-byte slots:

- stayed byte-identical across **all** iterations in the load (G1), and
- fall into a canonical address shape / the documented libWebKit range (G2 partial shape only).

It does **not**:

- forge `m_stateStack` or any vector metadata,
- dereference a leaked value,
- spray markers,
- scan addresses,
- write to the OOB window,
- claim a pointer leak.

This is the cheapest possible test of the premise behind the only remaining plausible chain: *if APNG OOB ever exposes a stable address-like value, it should be visible without any dangerous step.*

---

## 2) Preconditions

Server-side assets (same ones used by V946B/V948B/V953B):

- `v946b_f128_fr16.apng`
- `v946b_f64_fr16.apng`
- `v946b_f64_fr32.apng`

They are referenced relatively by the probe, exactly like V948B. If they are not served, the probe emits `IT-ERR load-fail` and G1 cannot be evaluated.

---

## 3) Procedure

Run **three fresh page loads** (different `cb` values), waiting for each `DONE`:

1. `…/probes/canvas-uaf/v982B-apng-oob-stability.html?it=8&cb=982a`
2. `…/probes/canvas-uaf/v982B-apng-oob-stability.html?it=8&cb=982b`
3. `…/probes/canvas-uaf/v982B-apng-oob-stability.html?it=8&cb=982c`

Defaults: `it=8` (allowed 4–12). Three assets × 8 iterations per load, no crash-reload loop, no memory-dialog behavior.

Then collect the `V982B-` beacon lines into one file and run:

```bash
python tools/analyze_v982b.py v982b-beacons.txt
# or, against a JSONL host log:
python tools/analyze_v982b.py host-beacons.log --probe V982B --min-runs 2
```

---

## 4) Beacon events

| Event | Meaning |
|---|---|
| `BOOT` | run id, iteration count, window definition |
| `IT` | per-asset raw qwords for rows `0,1,2,3,frH-1` |
| `IT-ERR` | asset load/decode failure |
| `STABLE_N` | counts: keys, stable, canonical, known-range, filler-stable, short, loadErr |
| `STABLE` | stable non-filler entries: `run\|window\|yN\|xN\|qword\|c=..\|known=..\|pg=..` |
| `CANON` | subset with canonical address shape |
| `KNOWN` | subset inside `[0x800000000, 0x900000000)` |
| `CTRL` | in-frame green control stability (`ok`/`bad`) |
| `VERDICT` | per-load G1 + partial G2 shape + `G3=pending` |
| `DONE` | load complete |

---

## 5) Acceptance / stop matrix

| Outcome | Meaning | Action |
|---|---|---|
| `G1=INVALID` (controls bad) | Harness or asset problem; not a memory result | Fix/retry once; do not interpret |
| `G1=FAIL` (no stable non-filler offset) | APNG window is not stable even within a load | **Close the APNG pointer-harvest branch**; do not forge |
| `G1=PASS`, no cross-load match | Stable within a load only (allocator reuse/local state) | Not a leak; **stop** |
| `G1+G3`, non-canonical | Cross-load stable but not address-shaped | Not a pointer read; **stop** |
| `G1+G3`, canonical/known-range | Shape candidate only | Design **one** independent G2 corroboration (second window/asset or independent surface); still **not** a pointer leak |

**Hard rule:** even `G1+G3` canonical is **not** permission to forge `m_stateStack`. G2 (independent corroboration that the value actually identifies mapped memory) must be established first, and any forge attempt requires the VC-04 crash-capture path.

---

## 6) Expected prior

V953B already found that the seemingly stable “ptr-like” values were skeleton/filler-adjacent (`0000000000aeaeaf`, `000000000000ee3f`, …) and variable slots never repeated as a pointer. The most likely result is therefore **G1 FAIL** or **G1 PASS with filler-only / non-canonical** stability.

If that happens, the APNG 321753 branch is closed as a **disclosure without pointer/ASLR utility**, and the Canvas UAF remains capped at:
- UAF+reclaim-consistent alias,
- typed Canvas2D state-field R/W,
- crash oracle requiring a mapped anchor.

No further Canvas probe should be designed until a new, independent disclosure surface is identified.

---

## 7) Artifacts

- `probes/canvas-uaf/v982B-apng-oob-stability.html`
- `tools/analyze_v982b.py`
- `docs/CANVAS_UAF_REOPEN_REVIEW_14.20.md` §7
- Prior evidence: `docs/reports/v925-v928B-session-findings.md` (V942B–V954B, V963B, V971B)
