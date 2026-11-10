# Canvas `getContext()` UAF — Reopen Review (PS5 14.20)

**Date:** 2026-11-10  
**Type:** Static/source + evidence re-audit. **No device probes were run for this review.**  
**Question (operator):** reopen the Canvas UAF, state exactly what was exploited/proven, and determine whether a **real raw pointer-read info leak** is still missing.

---

## 0) Answer up front

Yes — **a real pointer-read leak is still missing.** Nothing in the extract-backed 14.20 record shows JavaScript obtaining a raw WebContent/WebKit address.

What *is* established:

1. The **reentrancy/replacement path is real** in the PS5 OSS WebKit-1400 source that covers 14.20.
2. The trigger is **operational on 14.20** and consistently produces a stale wrapper whose behavior is **consistent with UAF + same-type reclaim** (V925 ×3).
3. The stale wrapper gives **typed Canvas2D state-field read/write** on the reclaimed live context (e.g. `lineWidth`, `globalAlpha`, `fillStyle`, `getLineDash`, `getTransform`), plus coherent save/restore/draw behavior.

What is **not** established, despite older wording:

- No arbitrary memory read/write.
- No raw pointer read.
- No “OOB state-stack read” primitive. That specific candidate is logically broken as written and is contradicted by V683/V908.
- No native-crash attribution (VC-04 open) and no controllable corruption/leak (VC-05/VC-06 open).

**Correct classification:** *confirmed reentrancy/replacement lifecycle class (14.00+/14.20) with reproducible UAF+reclaim-consistent aliasing; typed state-field R/W through the alias; no pointer leak and no arbitrary R/W.*

---

## 1) Evidence hierarchy used here

Newer, extract-backed/adjudicated documents win over older optimistic notes:

| Rank | Source | Use |
|---|---|---|
| 1 | `docs/CANVAS_GETCONTEXT_UAF_EVIDENCE_ASSESSMENT.md` | Newest verdict: lifecycle confirmed, **no primitive** |
| 1 | `docs/FINAL_REPORT_CANVAS_GETCONTEXT_UAF_14.20.md` | Frozen 14.20 report; VC-04/05/06 open |
| 2 | `docs/reports/v925-v928B-session-findings.md` | Per-probe 14.20 results, incl. APNG OOB |
| 2 | `results/beacon-logs/p0-2026-11-08/v925-beacons.txt` | Only raw 14.20 Canvas extract present in repo |
| 3 | `docs/DEAD_ENDS.md` | Exhaustive negative map (V650–V920), with corrections |
| 4 | `docs/CONFIRMED_VULNS.md` | Historical campaign summary — **overstated**, corrected in this review |

**Evidence caveat:** the OSS bundle is `WebKit_1400` (“14.00 -”), not a byte-verified 14.20 binary. Source conclusions are high-likelihood, not byte-exact.

---

## 2) What was actually proven

### 2.1 Source path: missing post-conversion reentrancy guard (strong)

Authoritative file: `WebKit_1400_src/HTMLCanvasElement.cpp`.

- `getContext()` checks `m_context` at **line 226**, then converts the IDL dictionary at **line 268** (`2d`) / **line 279** (`bitmaprenderer`). Dictionary conversion runs JS getters.
- There is **no `m_context` re-check after conversion** on either branch. `createContext2d` is called at **line 271**; `createContextBitmapRenderer` at **line 282**.
- Both creators assert `!m_context` and then overwrite it:
  - `createContext2d` — **lines 345–358** (`ASSERT(!m_context)` at 348, assignment at 350).
  - `createContextBitmapRenderer` — **lines 479–492** (`ASSERT(!m_context)` at 482, assignment at 484).
- `m_context` is a `std::unique_ptr`, so the overwrite destroys/replaces whatever the getter installed.

This is the documented **H1b trigger**: inner `getContext('2d')` installs a 2D context during conversion; the outer `bitmaprenderer` call replaces it, and the captured JS reference becomes stale.

Contrast: upstream `main` has the post-conversion guard, which blocks this trigger. 14.00+/14.20 diverge — vulnerable path present.

### 2.2 Trigger and aliasing on 14.20 (strong, behavioral)

| Probe | Result | What it proves |
|---|---|---|
| V923G + control | `bp/save/rr/rr2` survive under valid 2D reclaim | Trigger is operational on device |
| **V925 ×3** | `n=8→spray[6]`, `n=8→spray[3]`, `n=12→spray[3]`; `sameAsOrig=false`; `hitN=1`; coherent state/write-back/cross-draw; `rr ok` | Stale wrapper resolves to a **live reclaimed same-type 2D context**, reproducibly |
| V926B (session-reported) | `ALIAS idx=8`/`idx=4`, `lw=7777.77`, write-back `9999.99` | Same behavior; **no extract file in `results/`** — treat as secondary |

V925 is consistent with UAF+reclaim. It does **not**, by itself, prove a freed-slot access signature: every observed access lands on a live reclaimer object.

### 2.3 Typed state-field R/W through the alias (moderate, behavioral)

Through the stale wrapper, the Canvas2D API reads and writes the reclaimer’s live `State` fields:

- `lineWidth`, `miterLimit`, `globalAlpha` (doubles)
- `fillStyle` / `strokeStyle` (color strings)
- `font` (string)
- `getLineDash` / `setLineDash` (`Vector<double>`)
- `getTransform` (`DOMMatrix`)
- `save`/`restore`, patterns, `measureText`

This is real but **typed**: it is the Canvas2D object model operating on a valid, live context. It is not byte-granular access to the reclaimed object, and it exposes no storage addresses.

### 2.4 Confirmed negatives (important, usually omitted)

- `roundRect` / path writers on the live alias survive but the internally written Cairo pointer is **not readable through any Canvas API** (V929B: `ptr-written-but-unreadable-via-API`).
- Typed-setter overlap/corruption oracles on `lineDash` (V957B/V958B/V959B), save-stack × dash/transform/clip/filter/font (V960B–V966B), reset/resize (V965B): **no corruption, no crash, no inconsistency**.
- Cross-type 768-byte reclaim is possible, but every readable-fake attempt crashed (V907/V908/V911: 0 SUSPECT across 191 cases).
- JSC butterflies do not reclaim the WebCore 768 slot (V910).
- No pointer-derived number from recon (V912); `tee()` returns self-data only (V913).

### 2.5 Crash families are real but unattributed

- V923H: **10/10 inferred SAVE crashes** (5 stages ×2).
- V923C: **12/12 BP + 20/20 SAVE** inferred crashes on AB-zeroed reclaim.
- No klog/stack/minidump/symbolized PC. **VC-04 remains open.** A crash is not a primitive.

---

## 3) Corrections to older claims

### 3.1 “Same-type reclaim + R/W WORKING” → typed state-field R/W only

`docs/CONFIRMED_VULNS.md` #1 currently reads as if arbitrary R/W exists. It does not. The demonstrated operation is: *read/write documented Canvas2D state properties on a live reclaimed context through a stale wrapper*. That is a **logic/alias primitive**, not memory R/W.

### 3.2 “OOB state-stack read via save-count mismatch” → not a live candidate

The claimed mechanism in `CONFIRMED_VULNS.md`:

> Inner ctx has `m_size=9`; reclaimer has `m_size=1`; stale wrapper uses stale `m_size=9` to read `buffer[8]`, 2800 bytes past the 1-State buffer.

This cannot work as written, for three independent reasons:

1. **There is no “stale `m_size`” to use.** `m_size` lives inside the freed `CanvasRenderingContext2D`. If the C++ object is reclaimed, the reclaimer’s `m_size` is read (same-object behavior); if it is not reclaimed, the destructor has already run.
2. **Heap-backed state stack destruction nulls the base.** `~Vector` for a heap buffer calls `resetBufferAndCapacity()` → `m_buffer=nullptr`. `state()` then dereferences `nullptr + (size-1)*400 + 48` and faults. This is exactly V627’s result.
3. **Inline state stack does not help.** For `Vector<State,1>` the inline buffer destructor early-returns without nulling, but the first touch of the dangling wrapper still faults (V683/V684/V685/V916). V908’s `oob-v0` and `oob-v32` both **MISS** — the stale wrapper reads the reclaimer’s current state, i.e. the same-object model holds. Forged `size/cap=9` with a null buffer (`oob-ab9`) crashes as expected, with no leak.

So “save-count mismatch leaks adjacent heap” is **refuted by device evidence**, not merely untested.

### 3.3 “State buffer reclaim (6400 B)” → not a demonstrated read primitive

The 6400-byte out-of-line buffer can be replaced, but there is no evidence that a stale read reaches it with attacker-controlled metadata. The read path still requires a valid, mapped `m_buffer` plus a consistent `m_size` in the object that owns the wrapper.

### 3.4 Historical V460/V461/V548–V550/V562/V573/V630 claims → unverified in this repo

Those numbers are cited as complete successes but **no beacon extracts exist under `results/`** in this workspace. V562 (“all 12 APIs”) and V630 (“comprehensive alias diagnostic”) are not re-verified here. They are plausible and consistent with V925, but should be labeled **historical / session-reported**, not extract-backed 14.20 evidence.

### 3.5 “Exploitation chain: fake lineDash Vector → arbitrary R/W → vtable hijack → ROP”

This is an aspiration, not a chain. Its first prerequisite — a mapped address to forge `m_buffer`/`m_size` — is the missing pointer leak. The second prerequisite — a controlled write into the freed/reclaimed object that survives to the read — is only partially shown (AB owns the slot in V906, but AB is zero-filled).

### 3.6 APNG OOB (Bug 321753 class) → real disclosure, not a pointer leak

V942B/V946B/V947B/V948B show a genuine **JS-readable OOB read of variable live memory** in 14.20 image decoding. That is an information disclosure. But:

- V944B/V945B/V950B/V963B/V971B: **all marker sprays = 0**; no controllability.
- V953B’s “stable ptr-like” candidates were **heuristic false positives** (filler/skeleton-adjacent `0000000000aeaeaf`, `000000000000ee3f`, etc.); no value stable across iterations as a pointer.
- Content varies across iterations and loads; no cross-read self-validation, no module/ELF identification.

It is the most interesting remaining *disclosure* surface, but it is **not** a pointer/ASLR leak as evidenced.

---

## 4) Why the alias cannot produce a pointer read (source-level)

1. **No raw-storage API.** Every `State` accessor returns a typed scalar, string, or JS object (`CanvasRenderingContext2DBase.h` lines 102–234). `State` contains `String`, `CanvasStyle`, `Color`, `AffineTransform`, `Vector<double>` — no accessor returns an address or backing store.
2. **`state()` is size-gated.** `state()` = `m_stateStack.last()` (line 311); `last()` uses `m_size-1`. All Canvas2D property reads go through it, so no API reads past `m_size`.
3. **Wrapper identity is not exposed.** The JS wrapper is `ScriptWrappable::m_wrapper` (`JSC::Weak<JSObject>`); the C++ context holds `WeakRef<CanvasBase> m_canvas`. Neither is returned as a number or byte view.
4. **`roundRect` writes a pointer internally, but the path is opaque.** `CanvasPath`/`PathCairo` mutates `m_path` and stores a `cairo_t*` in the platform path. No Canvas API surfaces that pointer (V929B confirms).
5. **The forged-stack read needs a mapped address.** The only genuine pointer-mediated read found is `*(m_buffer + (m_size-1)*400 + 48)` in V906/V919/V920. It works mechanically, but `m_buffer` and `m_size` must be supplied by us inside a reclaiming allocation. Without a mapped base, it is a crash oracle, not a leak.

**Net:** the alias operates on a valid object's typed interface. To read a pointer you must first corrupt the object's vector metadata with a **known mapped address** — which is precisely what the missing leak would provide. This is circular, and that circularity is the wall.

---

## 5) Pointer-read surface audit

| Surface | Mechanism | 14.20 evidence | Verdict |
|---|---|---|---|
| Canvas2D property getters | Typed `State` fields | V925/V926B (typed) | **Typed only; no pointer** |
| `getContextAttributes()` | `m_settings` bytes, typed | V684/V688 (fault on freed) | **No pointer; first touch faults** |
| `ctx.canvas` | `WeakRef` → object/null | V684/V685 | **No address** |
| `roundRect` / path ops | Internal `cairo_t*` write | V929B | **Pointer written, unreadable** |
| Forged `m_stateStack` (V906) | `[ptr,1,1]` → deref | V906/V919/V920 | **Needs mapped base; oracle only** |
| Stale inline/zero-save stack | Inline buffer survives free | V683/V908 `oob-v0/v32` | **DEAD (fault / same-object)** |
| Cross-type 768 reclaim | Reclaim + steer read | V907/V908/V909/V911 | **DEAD (0 readable fake)** |
| JSC butterfly/StructureID/etc. | JSC-level objects | V910, 10-path audit | **DEAD** |
| AB `DontInitialize` | Uninit ArrayBuffer | V641 | **DEAD (zeros)** |
| Canvas backing store | `tryFastCalloc` | V905 | **DEAD (zero-init)** |
| libpas race (CVE-2025-43531) | Allocator race | source + zero-init | **DEAD (zero-init)** |
| `tee()` nonce | Self-data readback | V913 | **Self-data only** |
| `performance.now` / `Error.stack` | Timing/stack strings | V912/V967B | **No address tokens** |
| `createImageBitmap` edges | Crop/resize OOB | V968B | **Clamped; no leak** |
| `structuredClone` / `Intl` | Clone/format edges | V969B | **Negative** |
| RAB / CVE-2025-43541 canaries | Resize/offset pressure | V970B/V970B2 | **No signal (not proof absent)** |
| **APNG OOB (321753)** | Decoder edge-past-frame read | V942B–V948B | **Real disclosure; variable/uncontrolled** |
| APNG controllability | Marker/typed sprays | V944B/V945B/V950B/V963B/V971B | **DEAD (markers=0)** |
| APNG pointer harvest | Cross-iteration stability | V953B | **DEAD (false positives)** |
| BMP RLE OOB (321752/321754) | RLE absolute-run read | V952B/V954B | **DEAD (no anomaly)** |
| FilterImage uninit (324896) | SVG filter uninit | V956B | **DEAD (false positive, `0xC0`)** |
| WebCodecs (325886) | Codec surfaces | V955B | **API absent** |

---

## 6) The exact missing primitive

Define the missing primitive precisely, so it is testable:

> **P-leak:** JavaScript obtains at least 8 bytes of a WebContent address (or WebKit module address), such that:
> (a) the value is a canonical mapped user-space address;
> (b) it is stable for the lifetime of a load and reproducible across loads;
> (c) the bytes' origin is identified (which OOB/decoder/object produced them); and
> (d) it can be validated without crashing the process (e.g. two reads agree, or the pointed-to page yields a known magic).

V906 does **not** satisfy this: it can only distinguish “mapped” from “unmapped” by **crashing**, one guess per reload. A successful mapped probe would itself be the leak, and no HIT was ever observed. V919’s 20/20 miss and the documented computational wall reinforce that blind ASLR search is not a substitute for P-leak.

APNG OOB does **not** satisfy this either: it yields variable live bytes, but no controlled marker, no stable pointer, and no validation. It is a *candidate substrate* for P-leak, not P-leak.

---

## 7) The one remaining plausible chain (gated)

`APNG 321753 OOB disclosure → pointer-shaped word → validation → forge m_stateStack → typed/arbitrary read`

This is the only surface in the current record that both (i) discloses live memory to JS and (ii) is still present on 14.20. It should be pursued only under explicit gates, and it should be **stopped** if the gates fail.

### Acceptance gates (all required before any forge)

| Gate | Requirement | Current status |
|---|---|---|
| **G1 Self-consistency** | Same qword at the same OOB offset across ≥3 reads in one load | **Not met** — slots vary |
| **G2 Shape validation** | Value is canonical, 0x4000-aligned or module-range plausible, and points into a mapped page corroborated by a second independent leak | **Not met** — V953B candidates were filler-adjacent |
| **G3 Reproducibility** | Same class of value in ≥2 of 3 loads | **Not met** — cross-run variation |
| **G4 Containment** | No address scan, no memory-dialog-triggering loop; single documented window | Design constraint |
| **G5 Fault capture** | If the forge faults, VC-04 capture path (klog/stack/minidump) is available | **Prepared, not executed** |

**Rule:** G1–G3 failing means the chain is **not** ready for a forge probe; do not spend crash-reloads on address guesses. G1–G3 passing would justify **one** single-case, source-grounded probe with explicit PASS/FAIL, not a sweep.

### Minimal next experiment (only if G1/G2 can be tested cheaply)

A read-only, no-forge, no-crash probe: repeat the V948B window dump at fixed offsets across several iterations/loads, compute per-offset stability, and emit only offsets whose 8-byte value is unchanged across all samples *and* falls in the canonical user range. This produces evidence for/against G1/G3 without dereferencing anything. It is not a pointer leak by itself and must not be reported as one.

**Prepared (2026-11-10):** `probes/canvas-uaf/v982B-apng-oob-stability.html` + `tools/analyze_v982b.py`; procedure and stop matrix in `docs/V982B_APNG_STABILITY_RUNBOOK.md`. Status: **not run**. It performs no forge/deref/spray/scan and emits `G1` per load plus partial `G2` shape flags; `G3` is computed offline across three loads.

---

## 8) Required corrections in the repo

| File | Problem | Correction |
|---|---|---|
| `docs/CONFIRMED_VULNS.md` #1 | “R/W WORKING”, “full R/W”, “OOB state stack read” | Reword to typed state-field alias R/W; mark OOB read refuted; mark pointer leak missing |
| `docs/CONFIRMED_VULNS.md` summary rows | “R/W CONFIRMED, info leak candidate found” | “Typed state-field R/W via alias; no arbitrary R/W; no pointer leak” |
| `docs/CONFIRMED_VULNS.md` #1 evidence list | Un-extracted V460…V630 presented as complete | Label historical/session-reported; note only V925/V926B are 14.20-backed |
| `docs/DEAD_ENDS.md` line ~137 | “bidirectional R/W all CONFIRMED WORKING” | Qualify as typed field R/W; pointer leak still missing |
| `docs/FINAL_REPORT…` / `EVIDENCE_ASSESSMENT` | Already correct | No change needed |

These corrections were applied in this review (see the updated banners/notes). The frozen report and evidence assessment remain the authoritative verdict.

---

## 9) Bottom line

- **Exploited/proven:** reentrant `getContext()` replacement → stale Canvas2D wrapper → reproducible alias to a live reclaimed same-type context → typed Canvas2D state-field read/write; reliable crash families on AB-zeroed reclaim (unattributed).
- **Not exploited/proven:** arbitrary memory R/W, controlled corruption, native fault attribution, and **any raw pointer read**.
- **Is a real pointer-read leak still missing?** **Yes.** It is the blocking prerequisite for the alleged forge chain, and every candidate surface in the current record is either typed-only, zero-initialized, faulting, variable/uncontrolled, or absent.
- **What would change the answer:** a reproducible, self-validating 8-byte value derived from a WebContent address (P-leak), or native diagnostics proving a non-fatal read path on a provably freed slot with a surviving call. Nothing in the current evidence meets either bar.

---

## Appendix — key references

- Source: `WebKit_1400_src/HTMLCanvasElement.cpp:224–319` (getContext), `:345–358` (createContext2d), `:479–492` (createContextBitmapRenderer); `WebKit_1400_src/CanvasRenderingContext2DBase.h:102–234` (typed accessors), `:267–311` (State/state), `:436` (`m_stateStack`).
- Behavior: `results/beacon-logs/p0-2026-11-08/v925-beacons.txt`; `docs/reports/v925-v928B-session-findings.md`.
- Refutations: `docs/DEAD_ENDS.md` §“Crash Oracle”, §“Inline State Stack Read”, V907–V920 updates.
- Verdict: `docs/CANVAS_GETCONTEXT_UAF_EVIDENCE_ASSESSMENT.md`, `docs/FINAL_REPORT_CANVAS_GETCONTEXT_UAF_14.20.md`.
- Policy: `docs/P2_CONFIRMATION_PLAN.md` (no random probes, no address scans, no primitive claims without VC-06).
