# Confirmed Vulnerabilities  - PS5 14.10

Real memory safety bugs confirmed on device. Each hit a secondary wall that prevents full exploitation without an additional primitive.

> **Status key:** CONFIRMED = bug triggers on device. BLOCKED = exploitation blocked by secondary defense. The bugs are real  - they become exploitable if the blocking wall is bypassed.

---

## 1. CVE-2026-43720  - Canvas getContext() Reentrant UAF

**Status:** CONFIRMED on device  - IsoHeap OFF on PS5; UAF+reclaim-consistent aliasing with **typed Canvas2D state-field R/W** through the stale wrapper. **Not arbitrary memory R/W; no raw pointer read.** See `docs/CANVAS_UAF_REOPEN_REVIEW_14.20.md`.

**Bug:** `HTMLCanvasElement::getContext()` checks `m_context` at line 226, then calls `convert<IDLDictionary>()` at line 268 for settings. Dictionary conversion invokes JS property getters. A getter re-enters `getContext('2d')` on the same canvas  - inner call creates context, outer call overwrites `m_context` via `unique_ptr` assignment, freeing the inner context while its JS wrapper survives.

**Correct trigger (bitmaprenderer outer + 2d inner):**
```javascript
var innerCtx;
var canvas = document.createElement('canvas');
var settings = {};
Object.defineProperty(settings, 'alpha', {
  get: function() { innerCtx = canvas.getContext('2d'); return true; }
});
var outerCtx = canvas.getContext('bitmaprenderer', settings);
// innerCtx is now a dangling reference to freed memory
```

The bitmaprenderer outer avoids same-size-class reuse (80B vs 768B) that kills the Proxy+2d trigger.

**Device evidence:**

> **Review note (2026-11-10):** the entries below are historical campaign notes. Only V923G/V925 (plus session-reported V926B) have extract-backed 14.20 evidence in this repo; V460/V461/V548–V550/V562/V573/V630 extracts are **not present** and are **not re-verified** here. “R/W” in these notes means **typed Canvas2D state-field access**, not arbitrary memory access. See `docs/CANVAS_UAF_REOPEN_REVIEW_14.20.md` §3.

- V460/V461: Re-entry confirmed, same-type state-field R/W confirmed
- V527/V527b (cobra PR#13): AB reclaim of 768B slot, lineWidth=9999.99 readback
- V548-V550: Alias CONFIRMED, full state R/W via aliased pair
- V562: ALL 12 Canvas2D APIs work through alias  - clean complete run
- V573: Full same-type reclaim + bidirectional R/W on PS5 14.10
- V589: BMR trigger confirmed working (`uaf-ok: inner=OK`)
- V630: Comprehensive alias diagnostic  - ALL 12 Canvas2D APIs confirmed working through alias:
  - lineWidth/miterLimit/globalAlpha: bidirectional double R/W
  - fillStyle/strokeStyle: color string R/W
  - font: string R/W
  - setLineDash(500)/getLineDash: 500-double array round-trip PERFECT
  - getTransform: DOMMatrix object read
  - save/restore: 3-level cycle (333→222→111) works
  - createPattern: HTMLCanvasElement pattern creation works
  - measureText: TextMetrics object returned correctly
- V632: Two-stage test (alias + zero-alloc freed reads)  - Stage 1 alias confirmed
- V641: Blob/Worker/Fetch transfer race tests  - all DontInitialize paths return zeros

**IsoHeap is OFF on PS5.** `WTF_MAKE_ISO_ALLOCATED` compiles to standard FastMalloc on FreeBSD/PlayStation. Gigacage also disabled  - AB backing stores share the same heap as JSC/WebCore objects. Confirmed by Synacktiv writeup + BPlatform.h:341 `BPLATFORM(PLAYSTATION)`.

**Confirmed primitives:**
1. Same-type Canvas2D reclaim: 500x canvas spray reclaims the freed 768B slot (behavioral alias, V925)
2. Typed state-field R/W: `lineWidth`, `miterLimit`, `globalAlpha`, `fillStyle`, `getTransform`, `getLineDash` work through the stale wrapper — **typed values only, not byte-granular/arbitrary memory**
3. State buffer reclaim: 8 saves → 6400B out-of-line buffer, AB spray can reclaim — **not demonstrated as a readable primitive**

**Info leak candidate (OOB state stack read)  - CORRECTED 2026-11-10: NOT a live candidate.** The “stale `m_size=9`” premise is invalid: `m_size` lives inside the freed `CanvasRenderingContext2D`, so either the reclaimer overwrites it (same-object behavior) or the destructor already ran. In the heap-backed case `~Vector` calls `resetBufferAndCapacity()` and sets `m_buffer=nullptr`, so `state()` faults at `nullptr+(size-1)*400+48` (V627). In the inline `Vector<State,1>` case the buffer pointer survives, but the first touch of the dangling wrapper still faults (V683/V684/V685/V916). V908 `oob-v0`/`oob-v32` both **MISS** (stale wrapper reads the reclaimer’s current state); forged `size/cap=9` with a null buffer (`oob-ab9`) **CRASHES** with no leak. The only genuine pointer-mediated read is `*(m_buffer + (m_size-1)*400 + 48)` (V906/V919/V920), and it requires a **known mapped address** to forge `m_buffer`/`m_size` — which is exactly the missing leak.

**Current blocker:** INFO LEAK. All 12 Canvas2D APIs return typed JS values  - no path found to read a raw heap pointer. 10 dedicated info leak paths exhausted (see DEAD_ENDS.md "Info Leak Paths" section). Freed memory reads crash (destructor nulls `m_stateStack.m_buffer`). AB reclaim zeros data. DontInitialize AB paths return zeros on device. APNG 321753-class OOB gives variable live bytes but no controllability/stable pointer (V944B/V945B/V950B/V953B/V963B/V971B). Community help wanted on the info leak primitive.

**Exploitation chain once info leak is solved:** fake lineDash Vector → arbitrary R/W → vtable hijack → ROP → kernel. *(Aspirational: both the mapped anchor and a surviving controlled write are still missing.)*

**Fix:** Commit 2693828e8d73 (2026-06-29): re-checks `m_context` after dictionary conversion. Not present in WK-1400.

---

## 2. CVE-2026-43715  - CSSFontFace UAF Write

**Status:** CONFIRMED on device, BLOCKED by Timer RELEASE_ASSERT

**Bug:** During `CSSFontFace::setStatus()`, `iterateClients` copies `Ref<Client>` (not `Ref<CSSFontFace>`). Client callback resolves a `DOMPromiseProxy` which fires a synchronous `.then` getter. The getter modifies `@font-face` rules via `setProperty()`, triggering `remove()` + `adopt()` which drops the last `Ref<CSSFontFace>`. The old face is FREED. `iterateClients` returns and `m_status = newStatus` at line 595 **writes to freed memory**.

**Device evidence (p458):**
- `A-RESULT: THEN-1-status=loading` → `.then` fires DURING `iterateClients`
- `B-CHECK: loadedIdx:[55]` → spray face #55's `m_status` overwritten to Success(3)
- `C: CRASHED` → AB sentinel data had invalid enum → `RELEASE_ASSERT`

**CSSFontFace layout (192 bytes):**
- Offset 130: `m_status` (1 byte)  - **UAF write target** (writes 3=Success or 4=Failure)
- Offset 144-191: `m_timeoutTimer` (Timer, 48 bytes)
  - Offset 176: `m_thread` (Ref<Thread>)  - **RELEASE_ASSERT blocker**

**Why it's blocked:**
`setStatus(Success)` unconditionally calls `m_timeoutTimer.stop()`, which calls `setNextFireTime()` at Timer.cpp:469: `RELEASE_ASSERT(canCurrentThreadAccessThreadLocalData(m_thread))`. AB spray puts garbage at offset 176 → Thread check fails → crash. Same-type groom works but 1-byte `m_status=3` write is harmless (no secondary corruption). CSSFontFace is the **sole occupant** of the 192-byte size class.

**Unblock condition:** Leak of `Thread::current()` address to craft valid Timer at offset 176. Or find a `setStatus()` code path that avoids Timer access (none exists for Success/Failure triggers).

**14.20 live re-confirmation (V974B v2, 2026-11-10 ~00:01 UTC server):** p458 recipe reproduced exactly on 14.20 —
eager `face.loaded` + `face.load()` (CSS-connected `src:local('Arial')`) → `.then` getter fires **during
iterateClients with status=loading** (TRIG 9/9 runs incl. control) → getter does
`rule.style.setProperty('font-weight','bold')` + forced layout (**adopt frees the old CSSFontFace**) + zeroed
`ArrayBuffer(192)` wave ×48 → **CRASH 3/3 in-window** (between WAVE beacon and promise settle = the post-free
`m_status=Success(3)` write + `m_timeoutTimer.stop()` on AB-zeroed reclaim ⇒ `m_thread=null` → RELEASE_ASSERT,
matching this section's Timer chain), while **`arm=0` control (same trigger/Success load, no free/spray) survived
6/6**. Beacons: `results`/server `host-beacons.log` seq ~300-380 (2026-11-10). Readback (WB/HIT at +0x58/+0x68)
blocked by the Timer crash — process dies before JS can scan. **Wall confirmed live on 14.20; same unblock
conditions apply** (valid Thread* at +176, or a free-path whose post-free writes skip Timer).

**14.20 tail-survival pivot (V975/V976, 2026-11-10 17:24–17:36 UTC):** instead of skipping the unskippable
`setStatus` tail (the only unprotected thenable host), V975 reclaimed the freed 192B block with **live CSSFontFaces**
(`new FontFace` inside the getter, via=js) so the tail ran on a valid object (`m_thread` intact ⇒ `m_timeoutTimer.stop()`
passed) — **face armed: STATUS-HIT ×4/5 with 4 survivals** (1/64 sprayed never-pumped face became `loaded` each hit);
control arm=0 6/6 survived. **AB-deferred (no reclaim during tail): CRASH 3/3 before scan** (freed-but-intact tail
fatal). V976 characterization (6/7 HIT, hit slots vary 3/55/62/45/13/55): JS-observable corruption limited to `status`
(`loaded` vs `unloaded`); all other JS-exposed FontFace properties identical to baseline — **no JS-readable pointer
leak** (+0x58/+0x68 not surfaced by FontFace API; AB readback path fatal). Result: **repeatable, narrow status-flip
UAF writeback primitive with survival on 14.20**; info-leak/arb-RW from this path remains blocked by lack of a
JS-readable corruption channel on the reclaimed live face. via=style comparison pending.

---

## 3. ReadableStream tee() Type Confusion

**Status:** CONFIRMED on device, BLOCKED by JS builtin wall

**Bug:** `InternalReadableStream::fromObject()` (line 76-79) wraps ANY JSObject as InternalReadableStream with zero type check. By poisoning `Array.prototype[Symbol.iterator]` during `rs.tee()`, the SequenceConverter accepts attacker objects as stream branches.

**Two primitives confirmed:**

**Object substitution (V432):** Replace branch2 with any JSObject → `fromObject()` wraps it as a real ReadableStream (`instanceof` = true). `.locked` returns false, `.getReader()` throws.

**OOB read (V430/V432):** Return only 1 element from iterator → `results[1]` reads 8 bytes past Vector allocation. ASSERT compiled out on PS5. Crashes on ungroomed heap.

**Device evidence (V432):**
- Plain object wrapped as ReadableStream: confirmed
- ArrayBuffer wrapped as ReadableStream: confirmed
- OOB read: crashes at INTERCEPT (ungroomed)

**Why it's blocked:**
Every InternalReadableStream method goes through `invokeReadableStreamFunction()` → JS builtins. JS builtins read private slots via `@getByIdDirectPrivate`, which returns `undefined` on fake objects. No C++ code path directly accesses internal stream fields. Type confusion only manifests in JavaScript-level behavior, not memory corruption.

---

## 4. Private-Name Inversion via tee()

**Status:** CONFIRMED LIVE on device

**Bug:** Poisoning `Array.prototype[Symbol.iterator]` to yield the same object X twice to `tee()` → engine writes ReadableStream private slots (`disturbed`, `state`, `readableStreamController`) onto X.

**Device evidence:**
- `pidInverted=true`  - `firstThrow=TypeError, secondThrow=none`
- Signal: `pair[0].cancel()` writes slots → `pair[1].cancel()` sees `state==@streamClosed` → resolves without throw

**Why it's contained:**
Same JS builtin wall as #3. Controller written to X is real, but operations go through JS builtins that handle state correctly. No memory corruption path from this alone.

---

## 5. TransformStream Double-Iteration Disconnect (V429)

**Status:** CONFIRMED on device

**Bug:** Override `Array.prototype[Symbol.iterator]` during `new ReadableStream(underlyingSource, strategy)` where strategy returns a TransformStream's readable/writable. The C++ layer stores attacker-supplied streams while JS internals use the real streams. This creates a disconnect where data flows through the real pipeline but control references point to attacker objects.

**Device evidence (V429):**
- Double-iteration substitution confirmed
- C++ stores attacker streams, JS internals use real streams
- Pipeline stays consistent under test

**Why it's contained:**
Same JS builtin wall. All stream operations on the confused references go through JS builtins.

---

## 6. HTMLParser Custom Element Double-Parent

**Status:** UNFIXED in WK-1400 source, BLOCKED by post-construction validation

**Bug:** HTML parser `insert()` at HTMLConstructionSite.cpp:137 has `ASSERT(!task.child->parentNode())`  - stripped in release. `parserAppendChild()` blindly appends without checking parentNode. A custom element constructor that calls `altDiv.appendChild(this)` creates dual membership  - element in both parent's child list and altDiv's child list.

**Why it's blocked:**
Post-construction validation at JSCustomElementInterface.cpp:173 checks `wrappedElement->parentNode()`  - if non-null, throws NotSupportedError and creates HTMLUnknownElement fallback. Device-confirmed (V415): fallback inserted in original container, real element stays in altDiv.

**Open lead:** Microtask checkpoint at line 156 runs BETWEEN construction and validation. `document.write()`, DOM removal, or `document.open()` might bypass validation  - untested.

---

## 7. CVE-2026-43727  - Clipboard Iterator UAF

**Status:** Real bug, BLOCKED by missing API

**Bug:** `clearItemTypeLoaders` invalidates iterators during clipboard operations.

**Why it's blocked:**
Clipboard API is absent on PS5 14.10 (`navigator.clipboard` undefined despite `isSecureContext: true`).

---

## Summary

| Vuln | Bug Class | Wall | Status |
|------|-----------|------|--------|
| CVE-2026-43720 Canvas | UAF | ~~IsoHeap~~ OFF | **Typed state-field R/W via alias**; no arbitrary R/W; **no pointer leak** |
| CVE-2026-43715 CSSFontFace | UAF write | Timer RELEASE_ASSERT | DoS-only, sole 192B occupant |
| tee() type confusion | Type confusion | JS builtin dispatch | Contained |
| Private-name inversion | Slot injection | JS builtin dispatch | Contained |
| TransformStream disconnect | Reference confusion | JS builtin dispatch | Contained |
| HTMLParser CE | Double-parent | Post-construction validation | Microtask bypass untested |
| CVE-2026-43727 Clipboard | Iterator UAF | Missing API | Dead (no Clipboard API) |

**CVE-2026-43720 is the primary exploitation vector.** IsoHeap is OFF on PS5  - same-type reclaim gives **typed Canvas2D state-field R/W** through the stale wrapper, not arbitrary memory R/W. The OOB state-stack read via save-count mismatch was **refuted** by V683/V908 (see #1). A real pointer leak remains missing; without a mapped anchor the forged `m_stateStack` read is only a crash oracle. Chain once a leak exists: fake lineDash Vector → arbitrary R/W → vtable hijack → ROP → kernel.
