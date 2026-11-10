# VC-04 Pre-Analysis (WebKit-1400, 14.00+) — Ready for (B) Attribution

**Purpose:** Map likely crash-relevant paths *before* native diagnostics arrive, so (B) can be attributed quickly. **Not proof** of V923H/V923C root cause. Source: PS5 OSS `WebKit_1400.zip` (14.00+, covers 14.20) — `WebKit_1400_src/`.

## 1) Correlation anchors (beacons → capture)
- **V923H (priority):** inferred `SAVE`-path crash **2/2**; ref window ~2026-11-08 19:22:53–19:24:11 (14.20 base). Correlate device crash time to `*-SAVE-PRE` (and absence of `*-SAVE-POST`/completion) in `results/beacon-logs/p0-2026-11-08/v923h-beacons.txt`.
- **V923C:** `beginPath/save` crashes under AB-zeroed reclaim (2/2 inferred) — `v923c-beacons.txt`.
- Confirm UA/firmware 14.20 base and probe/cb lineage.

## 2) Relevant 1400 code paths (to match against symbolized PC/stack)
### `CanvasRenderingContext2DBase` state/stack
- Owns `Vector<State, 1> m_stateStack` (init with 1 state). Inherits `CanvasPath` (`m_path`).
- `save()`: `void save() { ++m_unrealizedSaveCount; }` (fast/unrealized; low direct deref of stack contents).
- `restore()`: checks/asserts `m_stateStack.size() >= 1`; if `<=1` handles unrealized; else `m_stateStack.removeLast()`, `restoreImplementation()`. (Touches stack + graphics state.)
- `realizeSaves()`/`realizeSavesLoop()`: asserts `m_stateStack.size() >= 1`; appends state while unrealized count; bounds vs `MaxSaveCount`. **Many operations call `realizeSaves()`** (grep showed widespread calls) — so “SAVE”-labeled crash in probes may manifest in realize/restore/stack access or in a later op that realizes, depending on probe sequencing.
- `beginPath()` clears path (`CanvasPath`/`m_path.clear()` region in base behavior).

### Context/lifetime (trigger context)
- 1400 `getContext` lacks post-conversion reentrancy guard; bitmaprenderer can overwrite `m_context` after getter-created 2D (confirmed). Under **same-type 2D reclaim** (V925/V923G) backing object is valid → ops safe. Under **AB-zeroed/invalid reclaim** (V923C/H pattern), object memory/state invariants can be violated.

### #59 (14.20, supporting) vs 1400 symptoms to check in (B)
- #59 reports AB reclaim can **zero the slot** and getters die on **null vtable at +0** (dispatch gate); `save()` still worked in that report’s mode. V923H/C crashed at save/beginPath under AB-zeroed reclaim — (B) must determine: null/bad vtable dispatch, invalid `m_stateStack` (buffer/size/capacity/inline) during `restore/realizeSaves/removeLast/append`, invalid `CanvasPath/m_path`/backend, or other.

## 3) Attribution checklist when (B) arrives
1. Identify faulting module/image (WebCore/WebKit/JSC/other), symbol/PC offset, exception/signal, fault address (esp. near 0 / vtable-like / stack-buffer-like).
2. Map PC to 1400 function (`realizeSaves*`, `restore*`, `restoreImplementation*`, `beginPath*`/path clear, `CanvasPath::*`, Cairo path, JS binding dispatch, etc.).
3. Classify VC-04: **attributed** (UAF/lifetime/type-confusion-consistent, null-vtable/invalid-state-consistent, or unrelated) vs inconclusive.
4. Update: `docs/CANVAS_GETCONTEXT_UAF_EVIDENCE_ASSESSMENT.md` (VC-04/05), `P2_CONFIRMATION_PLAN.md` (T2/H3), `FINAL_REPORT`.
5. **No primitive/impact claims** from stack alone unless VC-06 evidence exists.

## 4) Blocked / stop condition
- **Blocked until (B):** native fault signature, exact crashing instruction, register/fault-address evidence (must be provided from 14.20). VC-04/05/06 remain **open**; V923H **10/10** and V923C **12/12 BP + 20/20 SAVE** are **beacon-inferred** counts (verified).
- **Stop:** no further klog/minidump work until device/diagnostics situation changes. When (B) arrives, resume §3 attribution.