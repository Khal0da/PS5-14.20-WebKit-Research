# Final Report — Canvas `getContext()` Reentrancy (UAF+reclaim class) — PS5 14.20

**Date:** 2026-11-09  **Status:** P0/P1(+§8 WebKit-1400)/P2-A **adopted & frozen**  **Device:** PS5 14.20 base (`AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0`, observed)

## 1) Executive verdict
- **Confirmed (strong, source + behavior):** The documented reentrancy/replacement trigger path is **present in PS5 OSS WebKit-1400 (14.00+, covers 14.20)**. In `HTMLCanvasElement::getContext`, IDL dictionary conversion runs JS getters **without** a post-conversion `m_context` reentrancy guard (unlike upstream `main`); `createContext2d`/`createContextBitmapRenderer` overwrite `m_context`. A getter-created 2D context can be replaced by the outer bitmaprenderer context while a JS reference remains stale. On **PS5 14.20**, **V925 (DONE ×3)** reproducibly shows the stale `CTX` aliasing **live reclaimed same-type 2D contexts** with coherent state, single-target write-back, cross-draw readback, and `roundRect` ok — **consistent with UAF+reclaim**.
- **Not demonstrated:** a **symbolized native fault/root cause** (VC-04), or a **controllable exploit primitive/impact** (corruption, info leak, Cairo/write primitive; VC-05/VC-06). **No exploit primitive demonstrated.**
- **Classification:** *confirmed vulnerable trigger/lifecycle class (14.00+/14.20) with reproducible UAF+reclaim-consistent aliasing; exploit impact/primitive not demonstrated.*

## 2) Scope & method
- **In scope:** JS/WebKit canvas path — `getContext('bitmaprenderer', {get alpha(){ saved=getContext('2d'); ... }})`, stale `CTX` behavior, `roundRect`, same-type 2D reclaim. Evidence: HTTP beacons (`host-beacons.log`, crashes **inferred** only), probe definitions, PS5 OSS WebKit-1400 source mapping, upstream-main contrast.
- **Constraints followed:** no V925-style random probing, no address scans causing 14.20 memory dialog (V923E/I stopped), no PASS for “no crash”, no FAIL without evidence, no primitive claims without VC-06 proof. V925 instrumentation fixed (no in-getter sync beacons; no pre-reclaim `CTX` access).

## 3) Key behavioral evidence (P0, verified)
| Exp | Result | Notes |
|---|---|---|
| **V923G** (+ control) | **DONE**; `bp/save/rr/rr2` survive under valid 2D reclaim | Trigger viable |
| **V923J/K/L/M** | 0 observed corruption/leak (JS-observable) | No demonstrated impact on valid reclaim |
| **V923C/H** | **V923H: 10/10** inferred SAVE crashes (5×2); **V923C: 12/12 BP + 20/20 SAVE** inferred crashes (AB-zeroed reclaim, verified extracts), no native stack | Cause unattributed (VC-04 open); #59: AB reclaim can zero slot/break dispatch |
| **V923E/I** | Address scans impractical/stopped (memory dialog); no HIT/LEAK evidence | Blocked |
| **V925 ×3 (14.20)** | **DONE**: n=8→alias spray[6], n=8→spray[3], n=12→spray[3]; `sameAsOrig=false`; matching state/wb(`hitN=1`)/crossdraw(`redN=1`)/`rr ok` | Strong VC-01/VC-03; reclaim-consistent |

Extracts: `results/beacon-logs/p0-2026-11-08/` (incl. `v925-beacons.txt`). Probes: `probes/canvas-uaf/v925-alias-discrim.html`, `probes/canvas-uaf/v923*.html`.

## 4) Source mapping (P1)
- **PS5 OSS WebKit-1400 (14.00+, covers 14.20; high-likelihood alignment, not byte-verified):** `WebKit_1400.zip` → `WebKit_1400_src/HTMLCanvasElement.cpp`. `getContext` converts dict (getters run) then creates context **without** post-conversion reentrancy check for 2d/bitmaprenderer paths; `createContext2d`/`createContextBitmapRenderer` `ASSERT(!m_context)` and overwrite `m_context`. **Confirms H1b/vulnerable replacement path.**
- **Upstream `main` (contrast, §7):** post-conversion `if (m_context) return getExistingContext()` blocks the documented trigger — **14.00+/14.20 diverge (vulnerable-path present)**.
- **`CanvasPath::roundRect` (1400):** non-degenerate path mutates `m_path` with **no `hasInvertibleTransform()` guard** observed (other ops gate); Cairo backend ops via `PathCairo` (`cairo_t*` `m_platformPath`). Legacy `ensureCairoPath`/`m_path@+48` claims **not validated** on 1400 layout/runtime. Reachability characterized (VC-05 partial); **impact/primitive not proven**.

## 5) VC status
| VC | Status |
|---|---|
| VC-01 Reproducibility | Supported (V925×3, V923G) |
| VC-02 Lifecycle/replacement→stale | **Supported/confirmed at source-path level (OSS 14.00+)** + 14.20 aliasing |
| VC-03 Ref validity/aliasing | Supported |
| VC-04 Native fault/root-cause | **Open** (no symbolized stack/klog/minidump) |
| VC-05 `roundRect`/Cairo impact | **Partial (reachability/source)**, impact **open** |
| VC-06 Primitive/impact | **Not demonstrated** |
| VC-08 Version mapping | Substantially improved (OSS 14.00+ “14.00 -” covers 14.20; observed UA `AppleWebKit/605.1.15` on 14.20; trigger/lifecycle behavior matches 14.00+ source path vs `main`). Exact 14.20 WebKit binary parity to OSS bundle **not byte-verified** (no device binary dump here) — residual caveat only. |

## 6) External references (supporting, not primary evidence)
- [ZigZagBoi1/PS5-14.10-Research#184](https://github.com/ZigZagBoi1/PS5-14.10-Research/issues/184) — 14.20 Pro, p553/p554d alias context.
- [pastawithpesto/PS5-14.10-Jailbreak-Research#59](https://github.com/pastawithpesto/PS5-14.10-Jailbreak-Research/issues/59) (closed) — 14.20: trigger+same-type reclaim works; AB reclaim can zero slot/null vtable/break dispatch (consistent with V923C/H hazards; V925 used same-type 2D reclaim).
- PS5 OSS: https://www.playstation.com/en-us/oss/ps5/webkit/ (`WebKit_1400.zip`, 14.00 -), https://www.playstation.com/en-us/oss/ps5/cairo/

## 7) Open items / how to resume (gated)
1. **(B) High value:** symbolized crash diagnostics (klog/stack/minidump, symbolized PC/fault) for **V923H `SAVE`** (verified **10/10** inferred, ref ~2026-11-08 19:22:53–19:24:11) and/or **V923C** (**12/12 BP + 20/20 SAVE** inferred) on 14.20 → attribute **VC-04/05**. **Technical blocker (current setup): no klog/native crash diagnostics available on 14.20** — crashes remain beacon-inferred. **Stopped:** no klog/minidump work until device situation changes.
2. **Optional:** exact 14.20 binary parity vs OSS 14.00+ (VC-08 tightening).
3. **Do not:** run V925 variants/random probes/address scans; claim UAF primitive/impact without VC-04/06 evidence. **VC-04/VC-05/VC-06 remain open.**

## 8) Artifacts
- `docs/CANVAS_GETCONTEXT_UAF_EVIDENCE_ASSESSMENT.md`, `docs/P0_WEBKIT_UAF_EVIDENCE_BASELINE.md`, `docs/P1_SOURCE_REVIEW_UPSTREAM_REF.md` (§7/§8), `docs/P2_CONFIRMATION_PLAN.md`
- `results/beacon-logs/p0-2026-11-08/*.txt`
- `probes/canvas-uaf/v925-alias-discrim.html`, `probes/canvas-uaf/v923*.html`, `probes/index.html?cb=947`
- `WebKit_1400.zip` / `WebKit_1400_src/` (PS5 OSS 14.00+)
