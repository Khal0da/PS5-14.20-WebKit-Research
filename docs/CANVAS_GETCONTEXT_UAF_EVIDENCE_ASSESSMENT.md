# Canvas `getContext()` UAF — Evidence Assessment (PS5 14.20 base)

**Date:** 2026-11-09 (updated with PS5 OSS WebKit-1400 source-mapping). **Verdict:** **Vulnerable reentrancy/replacement path confirmed in PS5 OSS WebKit-1400 (14.00+, covering 14.20) with reproducible UAF+reclaim-consistent aliasing on PS5 14.20 (V925×3).** **No exploitation primitive demonstrated.** Root-cause-attributed native crash (VC-04) and proven Cairo/impact primitive (VC-05/VC-06) remain open.  
**Scope:** PS5 14.20 base (`AppleWebKit/605.1.15`). Evidence: JS beacons (`host-beacons.log`, crashes **inferred**), probe defs, **PS5 OSS `WebKit_1400.zip` (14.00 -)** source mapping, upstream-main reference (contrast). **No V925+ random probing; V923I STOPPED.**  
**Caveats:** OSS bundle is “14.00 -” (high-likelihood alignment to 14.20, not byte-verified against the exact 14.20 binary). V925 shows aliasing to a **live reclaimed** 2D context (expected for reclaim) — consistent with the free/replacement path in 1400 source. Third-party refs: [#184](https://github.com/ZigZagBoi1/PS5-14.10-Research/issues/184) (14.20 Pro, p553/p554d), [#59](https://github.com/pastawithpesto/PS5-14.10-Jailbreak-Research/issues/59) (14.20: AB reclaim zeroes slot/dispatch issues; same-type reclaim path relevant).

## 1) Trigger / hypothesis (under test)
Re-entrant `Object.defineProperty(... 'alpha', { get(){ saved = canvas.getContext('2d'); ... return true }})` passed to `canvas.getContext('bitmaprenderer', dict)` (per `docs/bugs/canvas-getcontext-uaf.md`, probes V923*/V925). Hypothesis: bitmaprenderer replaces/frees the 2D context while `saved`/`CTX` remains usable → stale reference; `roundRect` (radii overload) considered gate-free path candidate (Cairo `m_path`/`cairo_t*` write hypothesis, 14.20-unverified).

## 2) What is established (verified)
| Finding | Evidence | Status |
|---|---|---|
| Trigger executes and stale `CTX` operations survive under **valid 2D reclaim** | V923G DONE (bp/save/rr/rr2 OK); V923J/K/L/M DONE (ops/surveys, 0 observed anomaly) | **Operational** |
| **Behavioral aliasing is reproducible** on 14.20 base: stale `CTX` resolves to a **live reclaimed spray 2D context** (not original), with coherent state, write-back to same index, cross-draw/readback to same index, `roundRect` ok | **V925 DONE ×3** (21:24:18 n=8→spray[6]; 21:28:00 n=8→spray[3]; 21:34:02 n=12→spray[3]; `sameAsOrig=false`, `hitN=1`) — `results/beacon-logs/p0-2026-11-08/v925-beacons.txt` | **Strong (VC-01/VC-03 behavioral)** |
| Control confirms environment/trigger viable | V923G control DONE (2026-11-09 21:15:20+) | **Confirmed** |
| No observable corruption/leak primitive from tested `roundRect`/surface paths | V923J/K/L/M, V925 (JS-observable only) | **Negative (no demonstrated impact)** |
| AB-zeroed reclaim + `save/beginPath` crashes consistently (unattributed) | **V923H: 10/10 inferred SAVE crashes** (5 stages ×2); **V923C: 12/12 BP + 20/20 SAVE** inferred crashes (verified `v923h-beacons.txt`,`v923c-beacons.txt`, 14.20), no SLOT/CANARY | **Consistent negative / cause unknown (VC-04 open)** |
| Address-scan/self-forge read path impractical (14.20 memory dialog) / no HIT evidence | V923E tail, V923I STOPPED (attempt 120, 0 HIT/LEAK), V569 HIT/LEAK search 0 | **Blocked** |
| 14.20 scope (third-party, supporting) | #184: p553 canvas UAF 3/3 on 14.20 Pro | **Supporting ref** |

## 3) Status by VC (updated)
| VC | Status | Basis |
|---|---|---|
| **VC-01** Reproducibility | **Supported** | V925 **DONE ×3** (alias spray[6]/[3]/[3], coherent state/wb/crossdraw/`rr ok`) on 14.20 base; V923G + control. #184/#59 support 14.20 scope (external). |
| **VC-02** Lifecycle (replacement/free→stale) | **Supported / confirmed at source-path level (OSS 14.00+)** | **PS5 OSS WebKit-1400** `getContext`: converts dict (getters run) with **no post-conversion `m_context` reentrancy guard** (unlike main); `createContext2d`/`createContextBitmapRenderer` overwrite `m_context`. Trigger realizable → 2D replaced by bitmaprenderer while getter-captured ref remains stale. V925×3 shows alias to live reclaimed 2D (UAF+reclaim-consistent). *Caveat:* exact 14.20 binary parity to OSS 14.00+ not byte-verified. |
| **VC-03** Reference validity / aliasing | **Supported** | Explained by VC-02 replacement; V925 discriminates alias to specific reclaimed spray object (not original). |
| **VC-04** Native fault/root-cause | **Open** (capture path prepared 2026-11-09) | Inferred crashes only (V923H **10/10** SAVE, V923C **12/12 BP + 20/20 SAVE**, verified). **No native crash diagnostics (klog/stack/minidump/symbolized PC) captured yet** — crashes remain beacon-inferred. #59 AB-reclaim/dispatch hazard consistent; attribution requires (B). *History:* klog/minidump work was stopped earlier; **resumed by explicit operator decision 2026-11-09** — capture path prepared: DC probe `v973-vc04-dc.html` (frozen V923H-SAVE/V923C-BP replay, sub-second bracketing), `tools/vc04_encode.py` (windows/capture/correlate/attribute), precomputed anchors `results/vc04/v923{h,c}-windows-2026-11-08.*`; runbook: `VC04_CRASH_DIAGNOSTICS_CAPTURE_CHECKLIST.md` §Runbook v2. |
| **VC-05** `roundRect`/Cairo impact path | **Partially characterized (source)** / impact **Open** | WebKit-1400 reachability noted (no `hasInvertibleTransform()` guard on non-degenerate `roundRect` path); legacy offsets unvalidated. **No attributed crash/primitive.** Depends on VC-04/(B) + runtime mapping. |
| **VC-06** Impact / primitive | **Not demonstrated** | No pointer read; no observed corruption/leak/controlled primitive. Remains **open**; not claimed. |
| **VC-08** Version mapping | **Substantially improved** | OSS `WebKit_1400.zip` = “14.00 -” (covers 14.20); exact build/revision parity to device not fully pinned. |

## 4) P1/P2 status
- **P1 (source-mapped):** `docs/P1_SOURCE_REVIEW_UPSTREAM_REF.md` — **§8 WebKit-1400 (14.00+) confirms missing post-conversion reentrancy guard** and replacement overwrite (vulnerable trigger path), explaining V925/V923G; §7 contrasts with `main` (guard blocks). Cairo/offset specifics for 14.20 runtime remain open (VC-05).
- **P2:** `docs/P2_CONFIRMATION_PLAN.md`. With VC-02/03 now strongly supported by (A=OSS 14.00+)+behavior, remaining high-value: **(B) native crash diagnostics** for V923H/C to close VC-04 and attribute impact; deeper 14.20 runtime/Cairo mapping for VC-05/06 (only if a specific, acceptance-criteria hypothesis is pursued).

## 5) What would still strengthen closure
1. **(B) Native crash diagnostics** (14.20 base): symbolized stack/klog/panic/minidump for **V923H `SAVE`** (~2026-11-08 19:22:53–19:24:11, 2/2) and/or V923C → **VC-04/05** attribution. *(Capture path prepared 2026-11-09 — Runbook v2 in `VC04_CRASH_DIAGNOSTICS_CAPTURE_CHECKLIST.md`.)*
2. **Exact 14.20 binary parity check** to OSS 14.00+ (if available) → tighten VC-08 caveat.
3. **Cairo/runtime mapping on 14.20** (only with a specific hypothesis) → VC-05/06; **no random probing**.

## 6) Bottom line
- **Confirmed (strong):** On PS5 OSS **WebKit-1400 (14.00+, covering 14.20)** the `getContext` reentrancy/replacement path for the documented trigger is present (no post-conversion guard; bitmaprenderer overwrites `m_context` after getter-created 2D). On **PS5 14.20 base**, V925×3 reproducibly shows a stale `CTX` aliasing reclaimed **live** 2D contexts with coherent state/write-back/cross-draw and `roundRect` ok — **consistent with UAF+reclaim** (and with #184/#59 scope).
- **Not demonstrated:** a symbolized native UAF fault signature (**VC-04**), a proven exploitable **Cairo/write primitive** (**VC-05/VC-06**), or controllable corruption/leak. **Report as:** *confirmed vulnerable trigger/lifecycle class on 14.00+/14.20 with reproducible aliasing; exploit impact/primitive not demonstrated.*

## References
- Baseline: `docs/P0_WEBKIT_UAF_EVIDENCE_BASELINE.md` | P1: `docs/P1_SOURCE_REVIEW_UPSTREAM_REF.md` | P2: `docs/P2_CONFIRMATION_PLAN.md`
- Bug context: `docs/bugs/canvas-getcontext-uaf.md` (fix hash noted unverified/YARR) | Prior: `docs/WK1400_SOURCE_AUDIT.md`
- Extracts: `results/beacon-logs/p0-2026-11-08/` (v569,v923c,e,g,h,i,j,k,l,m,**v925**)
- Probes: `archive/v569.html`, `probes/canvas-uaf/v923*.html`, `probes/canvas-uaf/v925-alias-discrim.html` (ACTIVE refs in `probes/index.html?cb=947`, V923I STOPPED)
- External: https://github.com/ZigZagBoi1/PS5-14.10-Research/issues/184, #216 (method/attribution context)