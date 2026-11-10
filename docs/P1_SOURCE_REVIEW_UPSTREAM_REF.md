# P1 — Source Code Review (Upstream Reference, PS5 14.20 delta unknown)

**Date:** 2026-11-08  
**Basis:** WebKit/WebKit `main` (raw GitHub, fetched 2026-11-08) — *reference only*. **PS5 14.20 (AppleWebKit 605.1.15 / WebKit-1400 lineage) source not available in repo; behavior/layout may differ.** No V925/probes.  
**Inputs:** P0 `docs/P0_WEBKIT_UAF_EVIDENCE_BASELINE.md`, beacons `results/beacon-logs/p0-2026-11-08/`, `docs/bugs/canvas-getcontext-uaf.md`, `docs/WK1400_SOURCE_AUDIT.md`.  
**Note:** `canvas-getcontext-uaf.md` states fix commit `2693828e8d73` (2026-06-29, “not present in WK-1400”); fetching that hash resolves to a **YARR JIT fix** (307791@main), not canvas. Treat the *hash* as unverified; the relevant behavior difference must be confirmed against 14.20-aligned source (VC-08/VC-05).

## Files reviewed (upstream main)
- `Source/WebCore/html/HTMLCanvasElement.cpp` — `getContext` / context creation / re-entrancy checks
- `Source/WebCore/html/canvas/CanvasRenderingContext2DBase.{h,cpp}` — `save/restore/beginPath`, state stack, path ownership
- `Source/WebCore/html/canvas/CanvasRenderingContext2D.cpp` — 2D context specifics
- `Source/WebCore/html/canvas/CanvasPath.{h,cpp}` — path ops, `roundRect`, transform gate
- `Source/WebCore/platform/graphics/Path.h` — `Path`/`m_path` abstraction
- `Source/WebCore/platform/graphics/cairo/PathCairo.cpp` — Cairo backend (reference; 14.20 uses Cairo but internal layout/refactor differs upstream)

## 1) Trigger / lifecycle path (VC-02, VC-03)

### Observed trigger (probes/docs)
`canvas.getContext('bitmaprenderer', { get alpha(){ saved = canvas.getContext('2d'); /* use/save ref */ return true; } })` — re-entrant getter creates 2D context while outer call requests bitmaprenderer; `saved` becomes stale ref to freed 2D context (per docs/probes).

### Upstream `main` behavior (reference)
`HTMLCanvasElement::getContext` (JS overload) does:
1. If `m_context` exists → `getExistingContext()` (type-checked; requesting bitmaprenderer over existing 2D returns `nullopt`).
2. For 2d/bitmaprenderer/webgl/webgpu: **convert IDL dictionary from `arguments[0]`** (runs JS getters) → on exception return; **`if (m_context) [[unlikely]] return getExistingContext();`** → then create requested context.

**Implication (upstream):** On a fresh canvas, requesting `bitmaprenderer` converts options first; getter runs `getContext('2d')` and sets `m_context` to 2D; post-conversion `m_context` is set → returns `getExistingContext()`; existing is 2D but request is bitmaprenderer → returns `nullopt`. **2D context persists; bitmaprenderer not created; no replacement/free of 2D context.** This blocks the documented trigger.
- **14.20/WK-1400 delta (critical, unknown):** If 14.20 converted options and/or handled re-entrancy differently (e.g., allowed replacement, or ordered checks such that bitmaprenderer replaced the 2D context created during conversion), the stale-ref condition becomes plausible. **Cannot confirm from upstream main.** Requires 14.20-aligned `HTMLCanvasElement`/bindings.

### 2D context ownership
- `CanvasRenderingContext2DBase` holds `Path m_path` (inherits `CanvasPath` in base design shown) and rendering state stack. It is tied to `CanvasBase`/element; destruction/freedom on context replacement is implementation-specific (WK-1400 era). Upstream refactors ownership/lifetime patterns — **not directly mappable to 768B/offset layout in docs**.

**VC-02/03 status:** **INCONCLUSIVE.** Trigger reproducibly *exercised* in probes and V923G shows stale-ctx calls survive under valid 2D reclaim (consistent with aliasing/reclaim), but **independent proof that the original 2D context ended lifetime and ref is used-after-free (vs alias to live same-type object) is missing** without 14.20 lifecycle trace/source.

## 2) `CanvasPath` / transform gate / `roundRect` (VC-05 candidate)

### Upstream `CanvasPath.cpp` (main)
- `moveTo/lineTo/rect/quadraticCurveTo/bezierCurveTo/arc/arcTo/ellipse` guard with `if (!hasInvertibleTransform()) [[unlikely]] return;` (or return `{}`).
- `closePath()` does `if (m_path.isEmpty()) return; if (m_path.hasSubpaths()) m_path.closeSubpath();` — **no invertible-transform guard**.
- `roundRect` (radii overloads): validates finiteness/radii/ranges, handles degenerate `!width || !height` by calling `rect()` (which *is* gated), else computes rounded geometry and performs `m_path.moveTo(...)`, `m_path.addRoundedRect(...)` / `m_path.addBezierCurveTo`/`addLineTo`, `m_path.closeSubpath()`, `m_path.moveTo(...)`. **No `hasInvertibleTransform()` check in the non-degenerate `roundRect` path** (as read from fetched main). This is consistent with the probe/context note that radii-`roundRect` reaches path mutation without that gate.
- `CanvasPath::hasInvertibleTransform()` reads `m_hasInvertibleTransform` (member of `CanvasPath`). `CanvasRenderingContext2DBase` tracks/syncs it with transform state.

### `CanvasRenderingContext2DBase`
- `save()` (inline): `void save() { ++m_unrealizedSaveCount; }` (unrealized fast path) — **no virtual dispatch** shown in header.
- `beginPath()`: `m_path.clear()` (observed in base implementation region).
- `restore()/realizeSaves()` manipulate `m_stateStack`/graphics state; `state()`/`modifiableState()` access stack. Operations that realize/touch state stack can dereference state buffers — hazardous on reclaimed non-2D/zeroed memory; consistent with V923C/H crashes at `SAVE` under AB spray (exact fault undetermined without stack trace/14.20 source).

### Cairo / `m_path @ +48` hypothesis (14.20-specific)
Docs/context state: Cairo `Path` holds `RefPtr<cairo_t>` (+ optional elements), and `ensureCairoPath()`/first path mutation can allocate/store a heap `cairo_t*` at `context+48` (Path word 12), `roundRect` radii triggers it gate-free. **Upstream main `PathCairo` is refactored** (PathImpl/PathStream, `cairo_create` on operations, `m_platformPath` in `PathCairo` impl) — **field offsets and function names (`ensureCairoPath`) do not map 1:1.** V923G/J/K/L/M show execution survives and no JS-observable corruption/leak; they **do not read raw memory**. **Offset/write-address remains an unverified hypothesis for 14.20** (VC-05 gap).

## 3) Heap/reclaim context (relevant, not sufficient)
- PS5: `IsoHeap/Gigacage OFF` (per `canvas-getcontext-uaf.md`/`BPlatform.h` refs in docs) → cross/same-type FastMalloc reuse plausible; 2D context ~768B. V923G same-type reclaim (250 `getContext('2d')`) makes stale calls safe; V923C/H AB spray + `SAVE` crashed (vptr/invalid state or no reclaim). `WK1400_SOURCE_AUDIT.md` notes IsoHeap on Canvas 2D contexts (cross-type) — **does not resolve same-type stale-ref lifetime nor this trigger path**.

## 4) VC mapping (P1 delta)
| VC | P1 assessment |
|----|---------------|
| VC-02 | **INCONCLUSIVE** — lifecycle/free point on 14.20 unproven; upstream re-entrancy blocks trigger but 14.20 may differ. |
| VC-03 | **INCONCLUSIVE** — stale ref vs aliased valid reclaim indistinguishable from current evidence. |
| VC-04 | **INCONCLUSIVE** — no stack/klog; crashes uninterpreted; no confirmed UAF fault signature. |
| VC-05 | **PARTIAL (upstream-ref only)** — candidate paths identified (`getContext` re-entrancy, `CanvasPath::roundRect` non-gated path mutation, Cairo/Path storage). **Not 14.20-confirmed.** |
| VC-08 | **OPEN** — need 14.20/WK-1400-aligned source or build mapping. |

## 5) P2 confirmation plan (gated; no exploit primitives)
*Only if 14.20-aligned source confirms a free-before-use or equivalent violation (VC-02/04/05).*
1. **Lifecycle proof (VC-02/03):** instrument/trace or minimally targeted probe to distinguish “stale freed object accessed” vs “same-slot aliased live object” (without address scans that trigger memory dialogs). Any probe must have explicit acceptance criteria and no random spray variants.
2. **Crash root-cause (VC-04):** obtain native crash report/stack for V923H-class `SAVE` crash and for controlled stale-access cases on 14.20; map faulting PC to 14.20 source.
3. **`roundRect`/Cairo write (VC-05/06):** with 14.20 source, confirm actual function/offset writing `cairo_t*` (or equivalent) and whether it’s reachable on a truly freed object vs only on valid reclaim. Assess impact bounds without assuming R/W primitives.
4. **Rule:** if P1 on 14.20 source shows trigger is blocked / no lifetime violation, **reclassify to non-UAF** and close P2.

## 6) Blockers to close P1
- 14.20/WK-1400-aligned source (at minimum: `HTMLCanvasElement` context creation/getContext, `CanvasRenderingContext2DBase`, `CanvasPath`, Cairo `Path` implementation) or authoritative diff vs upstream.
- Any native crash diagnostics (klog/minidump/stack) for V923C/H/E/I-class crashes.
- Confirmation whether beacon extracts are accepted as full P0/P2 evidence.

## 7) Concrete upstream-main inspection (2026-11-09, local checkout — **reference only**)
**Tree:** `C:\Users\Khaled.ADMINISTRATOR\Downloads\14.20JB\WebKit-605.1.15` (`origin/main`, partial checkout; `Source/WebCore/html/*` present). **Not a PS5 14.20/605.1.15 match.**

### `HTMLCanvasElement::getContext` (main) — reentrancy guard present
After IDL dictionary conversion (**JS getters run**), main checks **`if (m_context) [[unlikely]] return getExistingContext();`** before `createContext2d` / `createContextBitmapRenderer`. `createContext*` assert `!m_context` and set `m_context`. **Effect:** the documented trigger (outer `bitmaprenderer` + getter creates `2d`) is blocked on main (returns existing/type-checked result; no replacement/free). **This diverges from PS5 OSS WebKit-1400 (§8).**

### `CanvasPath::roundRect` (main)
Non-degenerate path mutates `m_path` (`moveTo`/`addRoundedRect`/bezier/`closeSubpath`) with **no `hasInvertibleTransform()` guard** observed (other ops gate). Cairo backend manages `cairo_t*` internally. Reference only.

## 8) PS5 OSS **WebKit-1400** (14.00+, covers PS5 14.20) — **source-mapped (primary for VC-02/03/05/08)**
**Source:** PlayStation OSS `WebKit_1400.zip` (“For PlayStation®5 system software version **14.00 -**”, https://www.playstation.com/en-us/oss/ps5/webkit/), downloaded to `C:\Users\Khaled.ADMINISTRATOR\Downloads\14.20JB\WebKit_1400.zip`; key files extracted to `C:\Users\Khaled.ADMINISTRATOR\Downloads\14.20JB\WebKit_1400_src\` (`HTMLCanvasElement.cpp`, `CanvasRenderingContext2DBase.{h,cpp}`, `CanvasPath.{h,cpp}`, `Path.h`, `PathCairo.cpp`). **Caveat:** OSS bundle covers 14.00+; device under test reports **PS5 14.20 / AppleWebKit 605.1.15** — alignment is high-likelihood but not byte-verified against the exact 14.20 binary.

### 8.1 `HTMLCanvasElement::getContext` (WebKit-1400) — **no post-conversion reentrancy guard; replacement overwrite**
`HTMLCanvasElement::getContext(JSGlobalObject&, contextId, arguments)`:
1. **If `m_context` exists:** returns existing context (placeholder/type checks; 2d/bitmaprenderer/webgl/webgpu). **No dictionary conversion of the new call’s arguments in this path.**
2. **If `m_context` is null:**
   - **2d:** `convert<IDLDictionary<CanvasRenderingContext2DSettings>>(state, arguments[0]...)` (JS getters run) → `RETURN_IF_EXCEPTION` → **`createContext2d(contextId, settings)`** → set/return. **No check for reentrantly-created `m_context` after conversion.**
   - **bitmaprenderer:** `convert<IDLDictionary<ImageBitmapRenderingContextSettings>>(...)` (JS getters run) → **`createContextBitmapRenderer(...)`**. **No post-conversion reentrancy check.** (WebGL follows same convert-then-create pattern; WebGPU differs.)
3. **`createContext2d`:** `ASSERT(!m_context); m_context = CanvasRenderingContext2D::create(...); return m_context`.
4. **`createContextBitmapRenderer`:** `ASSERT(!m_context); m_context = ImageBitmapRenderingContext::create(...); return m_context`.

**Critical difference vs main (§7):** the `if (m_context) [[unlikely]] return getExistingContext()` guard **after** dictionary conversion is **absent** in WebKit-1400 for the relevant paths. `createContext*` **overwrites `m_context`** (and asserts it was null — assertion behavior may be compiled out/ignored in release; the overwrite is unconditional in logic shown).

### 8.2 Trigger realizability in WebKit-1400 (matches probe pattern)
On a fresh canvas (`m_context == null`), outer `canvas.getContext('bitmaprenderer', opts)` where `opts.alpha` getter does `saved = canvas.getContext('2d')`:
1. Outer enters bitmaprenderer branch, converts `ImageBitmapRenderingContextSettings` → **getter executes**.
2. Getter calls `getContext('2d')` (no/benign args) → 2D path converts settings, `createContext2d` sets **`m_context = 2D`**, returns 2D JS context; getter stores `saved` and returns.
3. Control returns to outer bitmaprenderer path → **no post-conversion guard** → `createContextBitmapRenderer` **overwrites `m_context` with bitmaprenderer**. The prior 2D rendering context is displaced from element ownership; the JS wrapper/reference captured as `saved` can become **stale with respect to the freed/replaced backing context**. With **same-type 2D reclaim** (allocations reusing the slot/object), that stale reference can alias a live 2D context — consistent with the UAF+reclaim class (CVE-2026-43720).

This explains **V925 (14.20, DONE ×3)** — coherent aliasing to reclaimed live spray 2D contexts (`sameAsOrig=false`, matching state/write-back/cross-draw, `rr ok`) — and **V923G** survival under valid 2D reclaim.

### 8.3 `CanvasPath::roundRect` / Cairo (WebKit-1400)
- `CanvasPath::roundRect` (non-degenerate): validates finiteness/radii (1–4, positive), normalizes/scales radii, computes geometry, then mutates via `m_path.moveTo`, `m_path.addRoundedRect(...)` (clockwise) or bezier/line sequence (counter-clockwise), `m_path.closeSubpath()`, `m_path.moveTo()`. **No `hasInvertibleTransform()` guard** observed in the non-degenerate body (other path ops in `CanvasPath` gate on `hasInvertibleTransform()`; degenerate falls to `rect()`).
- Cairo backend present (`PathCairo.cpp`); `Path`/`PathImpl` abstractions differ from old offset notes. `ensureCairoPath`/`m_path@+48`/`cairo_t*`-at-fixed-offset claims from legacy docs are **not validated against this 14.00+ layout**. V923C/H `SAVE/beginPath` crashes under AB-zeroed reclaim remain **unattributed without native stacks** (VC-04/05) — #59 reports AB reclaim can zero the slot/null vtable and break dispatch (consistent); our working path is **same-type 2D reclaim** (V925/V923G).

### 8.4 Net assessment (with 14.20 behavior)
- **VC-02 (lifecycle/free-before-use class):** **Supported/confirmed at source-path level in OSS WebKit-1400 (14.00+)** — the reentrancy replacement path exists and matches the trigger. Combined with V925×3 aliasing on 14.20, this is **strong evidence the stale ref arises from context replacement/free+reclaim (UAF+reclaim) on 14.20**. Residual caveat: exact 14.20 binary parity to OSS 14.00+ not byte-verified; no symbolized fault of the freed object in hand (V925 shows alias to *live* reclaimed object — expected for reclaim).
- **VC-03:** **Supported (behavioral + source-path)** — stale ref validity loss explained by replacement; alias to live same-type reclaim demonstrated.
- **VC-01:** strengthened (reproducible V925×3 + source-path explanation).
- **VC-04:** **still open** — crashes beacon-inferred; no native stack/klog/minidump for V923H/C.
- **VC-05:** **partially advanced** — `roundRect` reachability/absence of invertible-transform gate noted in 1400; 14.20 Cairo/write-address/impact not proven; no demonstrated corruption primitive.
- **VC-06:** no demonstrated controllable primitive.
- **VC-08:** substantially reduced by OSS 14.00+ (“14.00 -”) covering 14.20; exact build mapping not fully pinned.

**Decision:** Classify as **confirmed vulnerable reentrancy/replacement path in OSS WebKit-1400 (14.00+, covering 14.20) with reproducible UAF+reclaim-consistent aliasing on PS5 14.20 (V925×3)**. **Not a demonstrated exploit primitive**; root-cause-attributed crash (VC-04) and Cairo impact (VC-05/06) remain open without native diagnostics / deeper 14.20 runtime mapping.