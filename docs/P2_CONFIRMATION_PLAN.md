# P2 — UAF Confirmation Plan (Gated; no exploit primitives)

**Prereq:** P0 baseline + P1 upstream-ref review complete (`P0_WEBKIT_UAF_EVIDENCE_BASELINE.md`, `P1_SOURCE_REVIEW_UPSTREAM_REF.md`).  
**Current verdict:** Canvas getContext **suspected UAF — NOT confirmed** (VC-02/03/04/05/06 INCONCLUSIVE).  
**Policy:** no V925/random probes; no address scans causing 14.20 memory dialogs; no R/W/exploit assumptions. Every probe requires hypothesis + acceptance criteria + crash root-cause path.

## Blocking inputs (must obtain for P1→P2 closure)
1. **14.20/WK-1400-aligned source/diff** for: `HTMLCanvasElement::getContext` (dict conversion order, re-entrancy, context replacement), `CanvasRenderingContext2DBase` lifecycle/dtor, `CanvasPath`/`Path`/Cairo (`roundRect`, path mutation, `cairo_t*`/`m_path` layout & function names). Maps **VC-02/03/05/08**.
2. **Native crash diagnostics** (klog/panic/minidump/symbolized stack) for: V923H `SAVE` crash (2/2/stage), V923C `beginPath/save` crashes, representative LWCRASH/memory-dialog context if capturable. Maps **VC-04/05**.
3. **Confirm** beacon extracts (`results/beacon-logs/p0-2026-11-08/`) + probe defs accepted as full P0 evidence; share any V569 HIT/exports if they exist.

## Hypotheses to test (derived from P0+P1 upstream-ref)

### H1 — Lifetime violation on 14.20 trigger (VC-02, VC-03)
- **H1a (upstream-like, blocks):** 14.20 matches main’s re-entrancy behavior → getter-created 2D context persists, bitmaprenderer not swapped in; stale-ref is not a freed-object use (would **refute** UAF). *Conflict with observed stale usability under reclaim must be explained (aliasing/reclaim semantics).*
- **H1b (WK-1400 vulnerable):** dict conversion/re-entrancy ordering allows bitmaprenderer to replace/free the 2D context created in getter while a JS ref remains → **lifetime violation candidate**.
- **Acceptance:** Source-trace on 14.20 build **or** a P2 probe that distinguishes freed-slot access from same-slot live aliasing with defined, non-crashing (or diagnostically captured) evidence. **PASS** = independent evidence of end-of-life before use; **FAIL** = proven alias/no-free; else **INCONCLUSIVE**.

### H2 — `roundRect` gate-free path relevance (VC-05)
- Upstream: `CanvasPath::roundRect` (non-degenerate radii) mutates `m_path` without `hasInvertibleTransform()` guard (unlike most path ops). `beginPath()` clears `m_path`; `save()` unrealized increments count.
- **Acceptance:** Confirm on 14.20: which `roundRect` overload/impl is called, whether gate bypass exists, and whether `m_path`/Cairo platform pointer is written at the hypothesized offset (`+48`/word12) on valid reclaim and/or on a provably freed object. **No address leak required** for P2 confirmation; only controlled evidence of the memory operation’s target/safety.

### H3 — Crash mechanism classification (VC-04)
- V923H: AB spray + `CTX.save()` → crash 2/2 across stages (no `SLOT`). V923C similar for AB cases. V923G (valid 2D reclaim) survives `save/beginPath/roundRect`.
- **Candidates:** wrong reclaim target/type → virtual dispatch or state deref; or 14.20-specific `save()` realization path touches invalid state. **Not classified.**
- **Acceptance:** Symbolized/native stack maps to function/offset on 14.20 source. **PASS** = root cause explained & tied to lifecycle/type confusion; else **INCONCLUSIVE**.

### H4 — Cairo heap-pointer write is not an exploit primitive by itself (VC-06)
- V923J/K/L/M: no JS-observable corruption/leak after `roundRect` on valid 2D reclaim. Pointer read blocked (vptr/AB address). 
- **Acceptance:** P2 documents impact bounds only if H1/H2 show a true violation; otherwise classify as **no demonstrated impact**.

## Gated P2 test design (only after blocker 1 or a justified diagnostic path)
| Test | Goal | Method constraints | Evidence required |
|------|------|--------------------|-------------------|
| P2-T1 | VC-02 lifecycle on 14.20 | Source trace preferred; if probe, single controlled case, capture diagnostics | 14.20 call/lifetime trace or native stack proving free/use ordering |
| P2-T2 | VC-04 crash RCA | Repro V923H-equivalent with crash capture enabled | Symbolized stack + faulting instruction/module |
| P2-T3 | VC-05 `roundRect`/`m_path` | Source review on 14.20; optional instrumented build if available | Confirmed call path + written field/offset (or refutation) |
| P2-T4 | VC-03 alias vs freed | Compare same-type reclaim vs isolated lifetime evidence | Disambiguating result (not “no crash”) |

## Stop/go criteria
- **STOP (reclassify):** 14.20 source/trace proves no free-before-use and behavior matches safe aliasing/persistence → close UAF hypothesis; record as *not a confirmed UAF*.
- **GO P3 (impact characterization):** H1 PASS + H2/H3 mapped with 14.20 evidence → characterize bounds (still no primitive claims without VC-06 proof).
- **HOLD:** any of VC-02/04/05 remain unmapped to 14.20 → remain **suspected/inconclusive**.

## P2-A static outcome (2026-11-09, WebKit-1400 OSS)
**Input (A, partial/full for P1):** PS5 OSS `WebKit_1400.zip` (14.00+, covers 14.20) — `HTMLCanvasElement::getContext` lacks post-conversion reentrancy guard and overwrites `m_context` on replacement (**H1b path present**; T1 resolved at source-path level for 14.00+). V925×3 on 14.20 shows reclaim-consistent aliasing (VC-02/03 supported).
- **T3 (partial):** `CanvasPath::roundRect` (1400) non-degenerate mutates `m_path` with no `hasInvertibleTransform()` guard observed. Cairo backend present; 14.00+ `Path`/`PathCairo` layout/legacy `ensureCairoPath`+`m_path@+48` claims **not validated** for runtime impact.
- **Impact/primitive:** On **valid same-type 2D reclaim** (V925/V923G/J/K/L/M) no JS-observable corruption/leak. AB-zeroed/invalid reclaim paths (V923C/H; #59: AB can zero slot/break dispatch) crash **inferred** without native stacks. `CanvasRenderingContext2DBase` uses `m_stateStack`/`realizeSaves()` widely — invalid object state plausibly explains crashes, but **not attributable without (B)**.
- **Conclusion:** **No safe, acceptance-criteria device probe identified** to prove controllable impact/primitive from current evidence without (B) native diagnostics and/or specific runtime/Cairo mapping. **GO P3 not justified** (VC-04/05/06 open). Avoid random/scan probing.

## Immediate next action
1. **(B) Native crash diagnostics** (symbolized stack/klog/minidump) for **V923H `SAVE`** and/or V923C on 14.20 → P2-T2/H3, VC-04/05. **Prepared 2026-11-09 (resumed by operator decision):** DC probe `probes/canvas-uaf/v973-vc04-dc.html` + `tools/vc04_encode.py` (`windows`/`capture`/`correlate`/`attribute`) + precomputed anchors `results/vc04/v923{h,c}-windows-2026-11-08.*`. Procedure: `docs/VC04_CRASH_DIAGNOSTICS_CAPTURE_CHECKLIST.md` §Runbook v2. P2-T2 acceptance unchanged: symbolized stack + faulting instruction/module.
2. If a *specific, source-grounded, safely-observable* hypothesis emerges (no memory dialog, clear pass/fail), design a single gated probe with acceptance criteria.
3. Otherwise: **freeze** as *confirmed vulnerable trigger/lifecycle class (14.00+/14.20) with reproducible aliasing; exploit impact/primitive not demonstrated*. Do **not** run V925/random variants.

> **Direction note (2026-11-09):** "Convert V925 aliasing into arbitrary WebContent R/W" was evaluated and **rejected for now** — V925's post-free matrix shows any call on the stale wrapper crashes (`pf-lw`/`pf-save`/`pf-spray-save` CRASH; survivor `pf-spray-scan` hits=0), the crash-oracle address sweep hit a documented computational wall (DEAD_ENDS), and the info leak remains the blocked prerequisite (CONFIRMED_VULNS). The only evidence-changing step currently executable is (B) above; a primitive discussion may reopen only if VC-04 reveals a non-fatal fault mechanism and a *surviving call path* on a provably freed slot (explicit P2-policy override required otherwise).