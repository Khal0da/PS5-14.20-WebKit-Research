# Dead-End Investigations

Comprehensive list of all investigated attack vectors confirmed dead on PS5 firmware 14.10. Documented to prevent duplicate effort.

All investigations were performed against retail PS5 hardware running firmware 14.10, targeting the built-in browser (Safari 17.0 / WebKit-1400, LLInt-only, no JIT).

---

## JSC / JavaScript Engine

### MetadataTable Integer Overflow (Bug 317632)  - DEAD: OOM

38M entries x 104 bytes/node = 3.7 GB AST needed. PS5 WebContent OOM-kills at ~1.5 GB.

Mathematically impossible within PS5 memory limits. ThrowableExpressionData adds 36 bytes per call node, and no opcode can overflow within available memory. The `.length=81400` and `.length=79600` results were false positives (correct literal lengths: 817-char or 796-char chunks x 100). Inner function CodeBlocks are created lazily at first call, so the sweep never ran without an IIFE wrapper.

### ClonedArguments Butterfly UAF  - DEAD: Conservative GC

All 9 bypass angles exhausted. Conservative GC scanning pins butterfly memory.

Conservative GC rooting blocks all butterfly reclaim strategies. The GC scans the stack conservatively and will pin any cell that looks like a heap pointer, preventing reuse of freed butterfly storage. Confirmed with V240/V241 (CORRUPT-0 result).

### DirectArguments OOB Write  - DEAD: Bounds Check

`isMappedArgument(i)` checks `i < m_length` before `setIndexQuickly`.

Both the interpreter path and DFG path (irrelevant on PS5 anyway) perform bounds checking. No path from JavaScript to write past the mapped arguments boundary.

### sort() Detach UAF  - DEAD: Cleared

On detach: `m_vector` cleared, `m_length` zeroed. All access returns `undefined`.

Device-confirmed with V422. TypedArray sort with concurrent detach is fully handled.

### Yarr C3 Position Corruption  - DEAD: Match Failure

1-unit displacement always causes match failure, not exploitable state.

The corruption affects the pattern matcher's position tracking, but the resulting mismatch causes the regex engine to report "no match" rather than producing corrupted output that could be leveraged.

### Yarr Lookbehind Forward Reference  - DEAD: Fixed in WK-1400

`{0}` quantification cleanup fixed at YarrPattern.cpp:1534-1537.

The bug allowed a forward reference inside a lookbehind to skip quantification cleanup, but WK-1400 contains the fix.

### structuredClone Re-entry  - DEAD: Pool Roots Objects

`m_objectPool` roots all objects during serialization. No re-entry possible.

The serialization pool maintains strong references to all objects being cloned, preventing GC collection during the operation.

### structuredClone Pool Mismatch  - DEAD: Fix Present

V287 confirmed gcBuffer split fix present on PS5 14.10 binary.

The pool mismatch vulnerability (where serialization and deserialization could reference different buffer pools) has been patched.

### structuredCloneForStream OOB  - DEAD: Zero-Fill

V330 stale metadata confirmed on device but mmap zero-fill blocks info leak.

The stale metadata is real but newly mapped pages are zero-filled by the kernel, preventing information disclosure. V345 confirmed proper bounds checking on the JS `.length` property.

### ProxyObject JSScope Leak  - DEAD: Binary Fix

14.10 has binary-level fix. Receiver is constructor, not JSScope.

The Relapse Stage-1 primitive. 54/54 attempts fail deterministically on 14.10. The binary contains a fix that ensures the receiver object is the constructor rather than leaking the JSScope chain.

### jsCast Unchecked Paths  - SAFE: All Type-Guarded

Complete audit of all unchecked `jsCast<>` in JSC runtime.

Every unchecked jsCast is preceded by a C++ type check (@isRegExpObject, @isMap, etc.). No exploitable type confusion reachable from JavaScript.

---

## Streams API

### tee() Type Confusion  - DEAD: JS Builtin Wall

Private-name inversion confirmed. BUT all operations go through JS builtins.

Can write ReadableStream private slots onto arbitrary objects via yielding the same object twice to tee(). However, ALL InternalReadableStream operations dispatch through `invokeReadableStreamFunction` to JS builtins, which call proper methods on the target. No direct C++ field access bypasses this wall.

### tee() OOB Read  - DEAD: CrashOnOverflow

`Vector::at()` has CrashOnOverflow bounds check that kills the process before stale pointer access.

Device-confirmed with V438b: crashes were CrashOnOverflow trap (process termination), not exploitable stale pointer dereferences. AB cross-pollution approach also dead because it was premised on the OOB read.

### Stream Tee OOB via RAB Resize  - DEAD: Bounds Checks

Per-element `inBounds()` checks `bufferByteLength`. IDL converters reject RAB views.

All WebCore APIs reject resizable views at `toWrapped()`, and the stream internals perform per-element bounds checking.

### BYOB Stream Prototype Poison  - DEAD: No BYOB

PS5 14.10 lacks `ReadableStream` type:bytes entirely.

The `ReadableByteStreamController` and BYOB reader are not available. Device fingerprint confirms this.

---

## RAB (ResizableArrayBuffer)

### RAB TOCTOU (set/clone/copyWithin)  - DEAD: Per-Element Bounds

`set()` has per-element `inBounds`. `copyWithin` bounded by `maxByteLength`. `structuredClone` within bounds.

V416 was a false positive (signed/unsigned comparison bug in analysis, not in WebKit). V418 showed zero corruption. V419 detach is caught.

### RAB byteLength Inversion  - DEAD: Sinks Guarded

Inverted OOB check in byteLength getter is real but all downstream sinks have correct guards.

The inversion allows a view to report an incorrect byte length, but every consumer that uses this value performs its own bounds checking.

### RAB IDL Gate  - SAFE

ALL WebCore APIs reject resizable views at `toWrapped()`. Only `structuredCloneForStream` bypasses this gate, and that path is separately bounded.

---

## DOM / Rendering

### CSSFontFace UAF (CVE-2026-43715)  - DEAD: DoS-Only

UAF exists but free and use are synchronous. All grooming fails.

Eager promise + setProperty adopt path writes `m_status 0x03` to freed FastMalloc memory. However, no JS re-entry window exists between free and use. The 192-byte size class contains only CSSFontFace  - no type confusion target. All spray strategies (AB, string, Blob) fail. Confirmed DoS-only with p504.

### Canvas getContext() UAF (CVE-2026-43720)  - ~~DEAD~~ ALIVE: IsoHeap is OFF on PS5

**RETRACTED.** IsoHeap (`WTF_MAKE_ISO_ALLOCATED`) compiles to standard FastMalloc on FreeBSD/PlayStation. Confirmed by `BPLATFORM(PLAYSTATION)` in BPlatform.h:341 and Synacktiv writeup. Same-type reclaim, AB reclaim, and bidirectional R/W all CONFIRMED WORKING on device. See CONFIRMED_VULNS.md #1.

### OffscreenCanvas getContext()  - DEAD: API Missing

Identical reentrant pattern at OffscreenCanvas.cpp:243-263. IsoHeap is actually OFF (see Canvas UAF retraction), but `OffscreenCanvas` constructor is `undefined` on PS5 14.10  - API completely absent.

### EventTarget UAF  - DEAD: isJSExecutionForbidden

Guard blocks second handler execution. Document never freed during dispatch.

`isJSExecutionForbidden()` prevents handler re-entry in the critical window. V405 confirmed on device.

### XMLParser Custom Element UAF  - DEAD: Fragment Guard

Line 810: `!m_parsingFragment` skips CE check. `innerHTML` cannot trigger.

The XMLParser custom element instantiation path is guarded by a fragment-parsing check. Since innerHTML uses fragment parsing, it cannot reach the vulnerable code. XHTML iframes are dead on PS5. Main-frame XHTML requires specific content-type serving.

### Font loca OOB  - DEAD: Validated on PS5

PS5 renderer validates loca table offsets. All OOB produce notdef fallback glyph.

Device-confirmed with V260. The PS5 font renderer (possibly Sony-specific) performs offset validation that upstream WebKit may not.

### BMP OOB Read  - DEAD: Fixed

V400 and V402 returned fill values instead of leaked memory.

PS5 binary has the fix or uses a different BMP decoding codepath.

### Popover API Re-entrancy  - MOOT: Not Available

Popover API not available on PS5 14.10.

No `popoverAttribute`, `showPopover`, or `ToggleEvent`. Analysis showed the pattern is safe anyway (EventDispatcher Ref + validity rechecks).

### Clipboard Iterator UAF  - DEAD: No Clipboard

Clipboard API not available on PS5 despite `isSecure:true`.

CVE-2026-43727 clearItemTypeLoaders invalidation requires SecureContext + user gesture, but the API itself is absent.

### NodeIterator Adoption  - SAFE: RefPtr

All 5 tests passed. `RefPtr` keeps nodes alive through adoption, GC, removal.

---

## CVE Audit

### CVE-2023-42917  - DEAD: Patched

Fix present in WK-1400 Structure.cpp:917-933.

### All 2023-2024 WebKit CVEs  - DEAD: JIT-Dependent

Every CVE from this period targets DFG, FTL, or B3 JIT tiers.

These tiers are completely unavailable on PS5 (LLInt-only execution).

### All WSA-2026-0003/0004 CVEs  - DEAD

39 CVEs audited individually. All require WASM, JIT, WebGL, or user-interaction APIs not available on PS5.

### MSE SourceBuffer Re-entrancy  - SAFE

All events use `queueTaskToDispatchEvent` (async delivery).

Device-confirmed: re-entrant append, SourceBuffer removal during callback, ArrayBuffer detach after append  - all handled correctly.

---

## Kernel / Syscall (from browser context)

### UMTX CVE-2024-43102  - DEAD: SHM Stubbed

Sony removed shared memory subsystem on firmware 14.10.

The `USHMF_LINKED` single flag check is impossible because the SHM syscalls are stubbed. PS5Dev/PS5-UMTX-Jailbreak covers FW up to 13.60 only. Our probe 10 used the wrong syscall number, confirming the stub.

### AutoFillButtonElement Raw m_owner&  - DEAD: InjectedBundle Only

Same unfixed raw `AutoFillButtonOwner& m_owner` pattern as CVE-64783 DataListButtonElement. But `setShowAutoFillButton()` is only callable from `InjectedBundleNodeHandle.cpp:319`  - a native C++ API requiring browser chrome code execution. No JS/HTML/CSS path creates an AutoFillButton. SpinButton has the same pattern but is protected by `removeSpinButtonOwner()` in `destroyShadowSubtree()`.

### Relapse Scope Leak  - DEAD: Binary Fix on 14.10

ALL Relapse Stage-1 scope leak variants tested (V588): direct `leakScopeObject()`, eval variant, 5 `super` sub-tests. All return `undefined` on PS5 14.10. Binary-level fix present.

### RAB Bugs 312513 + 285876  - DEAD: Mitigated

V563 confirmed both mitigated on PS5 14.10. `grow()` zeros new bytes. No info leak.

### WebGL readPixels Uninit Leak  - DEAD: No WebGL

`readPixelsForPaintResults` has no error check → `toDataURL` could leak heap on GL failure. But `WebGLRenderingContext` constructor is absent on PS5 14.10 (V566: `WebGL=NO`). Unreachable.

### SVG Filter Integer Overflow  - DEAD: All Paths Checked

`CheckedUint32` overflow detection, `RELEASE_ASSERT`, 4096 dimension clamp, and NaN→empty result. All four SVG filter overflow angles are mitigated.

### CVE-2026-64783  - DataListButtonElement UAF  - DEAD: No Datalist on PS5

**Bug 313521.** `DataListButtonElement::defaultEventHandler()` holds raw `DataListButtonOwner& m_owner`. Changing `<input>` type inside click handler frees `TextFieldInputType` while event dispatch is in progress. Fixed in commit `be08720593` (WeakPtr + removeOwner).

**Why dead:** Requires `<input type="text" list="...">` with a visible datalist dropdown button, plus user click interaction on that button. PS5 Guide browser has no datalist UI. Even if it did, exploitation requires TextFieldInputType-sized heap spray and user interaction timing  - not viable from automated JS.

**WSA-2026-0005 advisory, CVSS 8.8.** Fixed in Safari 26.6 / WebKitGTK 2.52.6.

### Kernel Probes (CVE-2026-49418, CVE-2026-7270, poll/select UAF)  - BLOCKED

All require code execution outside browser sandbox. Unreachable from JavaScript.

CVE-2026-49418 (msync device-pager UAF), CVE-2026-7270 (execve memmove OOB), and the poll/select race condition all need native syscall access that the browser sandbox restricts.

### Sony Crash Tests  - DEAD: Harness-Only

54 `[Crash]` tests in PS5 TestExpectations all require `testRunner` or `UIHelper` APIs.

None are triggerable from the browser. Mostly UI/viewport tests. The postMessage OOM test was the only interesting candidate but requires the test harness.

---

## Info Leak Paths (Canvas UAF Context)

All paths investigated with 13+ independent agent audits. None produce a raw heap pointer.

### Canvas2D API Surface  - DEAD: All Typed Values

V630 confirms ALL 12 Canvas2D APIs work through the V573 alias (lineWidth, miterLimit, globalAlpha, fillStyle, strokeStyle, font, getLineDash, setLineDash, getTransform, createPattern, measureText, save/restore). Every API returns a typed JS value (number, string, or object). No API exposes raw memory.

### CanvasStyle Variant Type Confusion  - DEAD: Chicken-and-Egg

std::variant with index byte at State+24. Flipping index 2→1 would reinterpret gradient RefPtr as Color uint64. But changing the index byte requires raw byte access to the State, which requires the info leak this would produce.

### WTF::Vector Stale Data (restore)  - DEAD: API-Unreachable

removeLast() decrements m_size but never frees buffer. Stale pointer data SURVIVES in buffer past m_size after restore(). But Vector::size() gates ALL Canvas2D API reads  - no API reads past m_size. State copy constructor fully overwrites stale slots on re-save.

### AB Zero-Init Wall  - DEAD: All Paths

ArrayBuffer allocation: tryMalloc + memset(0) on every path. Confirmed on device (V566, V641). DontInitialize paths (Blob/Fetch/XHR/Worker segment gaps) also return zeros on PS5 (V641).

### Freed Memory Read  - DEAD: Destructor Invalidates

V627 confirms reading through freed Canvas2D context crashes regardless of grooming. The ~CanvasRenderingContext2D destructor runs ~Vector on m_stateStack which calls resetBufferAndCapacity() setting m_buffer=nullptr. state() then dereferences nullptr+offset → SIGSEGV.

### JSC-Level Paths  - DEAD: 10 Paths Checked

Butterfly overlap, StructureID confusion, JSFunction pointer leak, structured clone pointer exfiltration, FinalizationRegistry/WeakRef callback timing, stateStack realloc overlap, CanvasStyle forge, AB overlay scan  - all confirmed dead. Structure validation present, GC conservative scan blocks all butterfly reclaim.

### DontInitialize AB Paths  - DEAD: Zero on Device

Blob segment gap, Worker Float64Array, Fetch response body, XHR response ArrayBuffer  - all tested on device (V641). Every path returns zeros. The DontInitialize codepath may not be reachable or the kernel zero-fills the backing pages.

### libpas CVE-2025-43531 Race  - DEAD: Zero-Init Blocks Leak

libpas confirmed on PS5 (BPLATFORM(PLAYSTATION) at BPlatform.h:341). The bmalloc/libpas race condition is theoretically present but zero-init on allocation destroys any stale data that survives the race window.

### MSE buffered()  - DEAD: DoS Only

MediaSource.buffered returns a TimeRanges object. Heap layout manipulation via append/remove cycles confirmed but no info leak primitive  - only DoS via OOM.

### Canvas Backing Store Uninit  - DEAD: tryFastCalloc

Canvas backing store uses tryFastCalloc (calloc = zero-init). Even if freed backing store memory contains pointers, reclaiming it with a new canvas zeros it. getImageData always returns zero-initialized pixel data.

### Cross-Type Object Reclaim (V680/V681)  - Reclaim real, readable fake DEAD (V907 isolated, V908 full-52)

**CORRECTION (2026-11-06, from `host-beacons.log` re-parse).** The earlier claim "every
entry ended ctxhit=1, sus=0, no cross-type object reclaimed it" is wrong. It was written
from the `V680-OSTEP` lines only and ignored the cases that produced **no OSTEP at all**.

Per-index reconstruction of V680 (52 configs, 24 tagged contexts each, log seq 1502-1597):

| i | type | args | result |
|---|------|------|--------|
| 16 | style | 24 × 48 props | **NO OSTEP → crash (HIT)** |
| 23 | matchmedia | 8 | **NO OSTEP → crash (HIT)** |
| 35 | text | 24 × 704 chars | **NO OSTEP → crash (HIT)** |
| 47 | strfake8 | 24 × 720 (8-bit) | **NO OSTEP → crash (HIT)** |
| 48 | strfake16 | 24 × 360 (16-bit) | **NO OSTEP → crash (HIT)** |
| 49 | abfake | 16 × ArrayBuffer(768) | **NO OSTEP → crash (HIT)** |
| 50 | abzero | 16 × ArrayBuffer(768) | **NO OSTEP → crash (HIT)** |
| other 45 | elem/attrs/xhr/grad/path/... | — | `ctxhit=1` (miss) |

A missing OSTEP is not a silent abort: the run continued at index+1 about 1.7-1.9 s later,
i.e. the page had to be reloaded. That is a WebProcess crash, and it happened **at the
dangling read**, after the spray. It means the sprayed allocation took the freed slot:
the tagged 2d contexts could no longer win it, and `savedCtx.lineWidth` faulted.

All seven hits are consistent with a 768-byte size class: StringImpl 20+720 = 740 -> 768
(704 chars 8-bit, 720 chars 8-bit, 360 chars UTF-16), ArrayBuffer(768), and the 48-prop
style div (a WTF::Vector that rounds into 768). `matchmedia` is the only loose end.

**Consequence:** cross-type reclaim is *proven possible*. The blocker is not "find a type
that lands in the slot" — it is "make the reclaimed bytes steer a read". A zeroed
ArrayBuffer makes `state()` dereference null and faults; V650 tried to forge
`m_stateStack` at +112 and every one of its 30 target addresses crashed.

Exact-size butterflies (V682 arrX) missed.

**UPDATE (2026-11-06, V907 isolated, beacons 10038-10062, 12 cases 16:02:17-16:02:58):**
5 MISS, 7 CRASH, 0 SUSPECT — readable fake is DEAD.
- Confirmed at read (`S3-tagged` = after candidate + 24 taggers, i.e. at `lineWidth`):
  `style48`, `strfake8`, `abfake`, `abzero`. Controls `same` MISS (`lw=205`) and
  `abzero` CRASH validate the harness.
- Polarity proves 768-byte geometry, not count: `style48` CRASH vs `style16`/`attrs48`
  MISS; `text704` CRASH vs `text1024` MISS.
- `matchmedia` MISS (`lw=202`, kept=8) — V680 hit NOT reproduced in a single isolated
  run. V680's one-pass sweep order / leftover heap state / GC load may have caused the
  original missing OSTEP (sweep contamination). Needs repeat before any claim.
- `text704` and `strfake16` crashed at `S2-candidate` (before taggers finished),
  i.e. during/just after candidate allocation, NOT at the dangling read. That is
  spray-phase instability (allocator / GC / OOM pressure), not a read deref. Do not
  count them as read proof. This breaks the V680 assumption "no OSTEP = read crash".
- `strraw8` (payload-only string, +112/+120 left untouched) CRASH at `S3-tagged`:
  real StringImpl header bytes are not a readable Vector either. Leave-header dead.

**UPDATE (2026-11-06, V908 full-52, beacons 10068-10182, 57 cases 16:31-16:45):**
45 MISS, 12 CRASH, 0 SUSPECT — readable fake still DEAD, exhaustive now.
- Crash at read (`S3-tagged`): `style48`, `strfake8`, `strfake16`, `abfake`, `abzero`,
  `text704` (was `S2` in V907, now `S3` — stage is race-unstable), plus two NEW hits the
  V680 single-pass sweep called miss: `urlsp96` and `imagedata-16x12` (768 backing;
  `imagedata-16x11` MISS, `urlsp32` MISS). A single sweep undercounts flaky 768 types.
- `matchmedia`: 3/3 CRASH here (r1 `S3`, r2 `S3`, r3 `S2`) vs 0/1 MISS in V907 —
  flaky race (4 runs total: 3 crash, 1 miss), not a V680 sweep artifact.
- OOB matrix: `oob-v0` (saves=0) MISS (`lw=207`), `oob-v32` (saves=32) MISS (`lw=205`):
  save-count mismatch gives no adjacent-heap read; stale wrapper reads the reclaimer's
  current state (same-object model holds). Forged-size `oob-ab9` (size/cap=9, null
  buffer) CRASH at `S3` as expected — no leak, just a pointer fault.

**UPDATE (2026-11-06, V909 geometry, beacons 10183-10217, 17 cases 17:43-17:44):**
7 MISS, 10 CRASH, 0 SUSPECT — geometry tuning closed, readable fake still dead.
- `urlsp` peak only at 96 (2/2 across V908+V909, `S3-tagged`); 64/80/112/128/160 all MISS.
- `imagedata` 768 family: `16x12`/`24x8`/`12x16`/`32x6`/`48x4` all `S3-tagged` read,
  `96x2` `S2-candidate` spray-phase (not read proof), controls `16x11`/`22x8` MISS.
  Backing size (768) matters, shape does not (except extreme `96x2`).
- `matchmedia` 3/3 new `S3` (6/7 total, V907 outlier). Highly reliable.
Next: V910 mapped-anchor harvest.

**UPDATE (2026-11-06, V910 harvest, beacons 10256-10284, 14 cases 18:41-18:42):**
11 MISS, 3 CRASH, 0 SUSPECT — JSC pointer harvest dead.
- All 10 JSC candidates MISS (`arr-obj` 80/90/96/100 + `arr-ab`/`arr-str`/`arr-dbl` + `map`/`set`/`obj-props`):
  JSC butterflies do not reclaim the WebCore 768 slot (not just a size miss; GC/allocator split).
- Controls confirm harness: `imagedata-16x12`/`abzero`/`abfake` CRASH at `S3`, `same-none` MISS.
Next: WebCore 768 fine-tune (V911) to shift +112 onto a valid Vector.

**UPDATE (2026-11-06, V912 recon, beacons 10379-10395, 19:02 UTC):**
15 families, no crash — no pointer-derived anchor. `performance.memory`/`AudioContext`/`eventCounts` absent;
`toString` shows no `0x...`; error stack URL:line:col; typed offsets exact; randoms fresh per load; RAND hex
was just `double(3593486815/1000)=0x4089780000000000`, unrelated. Constants confirmed (no WASM/SAB/WebGL).
Next: V913 tee-nonce (self-data equality proof).

**UPDATE (2026-11-06, V911 fine-tune, beacons 10297-10355, 29 cases 18:54-18:56):**
23 MISS, 6 CRASH, 0 SUSPECT — fine-tuning finds crashes, never a readable value.
- New read hits (`S3-tagged`): `blob-8x768`, `blob-16x768`, `text-736`, `urlsp-92` (plus `imagedata`/`abzero` controls).
- `headers`/`formdata`/`rules`/`grad`/`path` all MISS in this sweep; `blob-800` MISS, `text-768`/`800` MISS,
  `urlsp-88`/`100`/`104` MISS. Size hits the 768 class, but +112 never becomes a valid Vector.
Next: V912 pointer-derived numbers recon.

### Crash Oracle (V650-V655)  - Mechanism CONFIRMED by V906, addresses NOT FOUND

**UPDATE (2026-11-06, V906 full run, beacons 9997-10034):**
- Control `same` = MISS `lw=201` — trigger/reclaim works, tagged context won the slot.
- All 15 AB cases crashed, 0 HIT, 0 MISS for AB. 14 crashed at `S4-tagged` (during `lineWidth` read, after 8 taggers completed); `pe_512m` crashed at `S3-spray200` (during spray, before read — OOM candidate, not a deref proof alone).
- `dbl` (every lane = 4.5678 float64) crashed instead of returning 4.5678. That proves the read is **not** a direct double read from the slot: the wrapper dereferences a **pointer** stored inside the slot.
- The probe is offset-agnostic: `[ptr,1,1]` repeats every 16 bytes in both phases (`pe`/`po`), so every 8-byte-aligned Vector offset sees the same `[ptr,1,1]`. Because all guessed pointers crashed, the failure is due to **unmapped target addresses**, not a wrong +112 offset. This separates the two hypotheses that were open after V650: (2) "slot never read" is now excluded; (1) wrong offset is also excluded — the bytes *are* read, at whatever offset WebKit uses.
- Why V650 had 0 HIT: its 30 targets were all unmapped (stack guesses `0x00007fff...`, exe guesses `0x400000/0x800000`, etc.). V906 tried 6 more top guesses (`stack1/stack2/4m/64k/512m/4g` in both phases) and all were unmapped too.

**Still missing:** a mapped address. The oracle proves "this pointer is unmapped" vs "this pointer is mapped" would return 8 bytes, but no HIT has ever been observed because no correct pointer has been tried. Finding a mapped address is equivalent to the info-leak problem: blind guesses of user-space addresses on a PIE/ASLR process are hopeless without a leak.

V650A (`V650A-SETUP/SPRAY/SPRAYCTX/READ=before`) and V650 (`BOOT/TGT/UAF/SPRAY`) showing no `HIT` is now explained: correct mechanism, wrong addresses.

### Inline State Stack Read (V683)  - DEAD: First Touch Faults

Hypothesis: with zero saves the state stack is inline (`m_buffer = this+128`), so
`~VectorBuffer` early-returns and the fields survive the free. On device `bare`, `baref`,
`barew` and `baregrow` all crashed at v=0, while the same-type control `barerec` worked.
The first touch of the dangling wrapper faults regardless of where the stack lives.

### Non-Vector Member Read (V684/V685)  - DEAD: First Touch Faults

`getContextAttributes()` (pure `m_settings` byte read) and `savedCtx.canvas` (`m_canvas`
pointer load) both crash on the unreclaimed slot. V685 proves the ordering: OSTEP0 lands
right after `getContext('bitmaprenderer')` returns, then the renderer dies on the first
touch. The trigger is not the problem.

### AB-Owned Slot + JS->C++ Calls (V686/V688)  - DEAD: Every Call Tested Faults

V687 proves ArrayBuffer(768) is the size class that takes the slot (the only size that
crashes). But on that AB-owned, zeroed slot: `beginPath`, `getContextAttributes` and
`save` all crash (V686, V688). Only `idle` and forced `gc` survive. The PathImpl-pointer
leak idea (two `moveTo` calls writing a heap pointer into our buffer) is unreachable
because the calls fault before any pointer is written.

### Canvas Dimension / Dirty-Rect Arithmetic (V905)  - DEAD: All Clamped

19 cases, one per page load, three independent detectors (crash stage, pixel pattern,
8 x Uint32Array(2048) canaries at 0xDEADBEEF). Full run 2026-11-06 10:26:34-10:26:59,
beacon seq 9940-9977. Result: **no OOB read, no OOB write, no anomalous byte.**

- `canvas.width/height` 8192 and 65535: accepted, blank reads returned transparent.
  16384x16384 (exactly 1 GiB backing store) crashed the WebProcess at `S4-read`,
  i.e. when `getImageData` first forced the allocation. No corrupted byte was observed
  before the crash. Classified as OOM/abort (DoS), not memory corruption, because the
  area 16384*16384*4 = 2^30 has no integer overflow and the context had already been
  created successfully.
- `createImageData(0x40000000,1)`, `(0x10000,0x10000)`, `(0xFFFF,0xFFFF)`:
  `RangeError: Cannot allocate a buffer of this size`.
- `getImageData(-1,-1,100,100)` on a 64x64 pattern canvas: `len=40000, lenMatch=true,
  n=0` (64x64 pattern exact, 1-pixel border transparent black per spec).
- `getImageData(0,0,0x7fffffff,0x7fffffff)`: `InvalidStateError`.
- `putImageData` with dirty rect (-1,-1,1e9,1e9), (0,0,1e9,1e9), `0x7fffffff,0x7fffffff`,
  fully-outside destination, and 3-arg outside: `n=0, canary=ok` in every case.
- `drawImage` src rect (32,32,128,128) onto 64x64: exact clip, `n=0`.
  src rect (-32,-32,128,128): WebKit clamps the source to (0,0,64,64) but does **not**
  shift the destination (spec says adjust proportionally). The detector reported
  `n=15324`, and the dumped hex `0b2845ff 122f4cff ...` is exactly the probe's own
  `pat(x,y,c)` for source coords (0,0),(1,0),... — i.e. the alarm is the detector's
  expected-model being wrong, **not** foreign data. Non-spec, but not memory unsafe.

Conclusion: dimension/dirty-rect integer arithmetic is fully guarded on 14.20.
The only new finding is the 1 GiB canvas DoS.

### Unresolved - Do Not Treat As Dead

- **V906 slot-steer oracle** (2026-11-06): **RESOLVED.** See "Crash Oracle" above.
  Mechanism confirmed (slot bytes dereferenced as pointer, 14/15 at S4, dbl crashes).
  No mapped address found. Next work is finding a mapped address, which is the
  info-leak problem.
- **V680 seven hits** (style/48, matchmedia, text/704, strfake8, strfake16, abfake,
  abzero): **RESOLVED.** Re-run as **V907** (`probes/canvas-uaf/v907-cross-isolate.html`,
  2026-11-06 16:02, beacons 10038-10062). 0 SUSPECT — readable fake is dead.
  `style48`/`strfake8`/`abfake`/`abzero` confirmed at read; `text704`/`strfake16`
  crash during spray, not at read; `matchmedia` not reproduced (single-shot MISS).
  See "Cross-Type" above for per-case detail.
- **Full-52 + OOB + matchmedia x3** (2026-11-06): **RESOLVED.** **V908** (`probes/canvas-uaf/v908-full52-oob.html`,
  2026-11-06 16:31-16:45, beacons 10068-10182): 57 cases = 45 MISS, 12 CRASH, 0 SUSPECT.
  `urlsp96` + `imagedata-16x12` NEW hits missed by V680's single-pass sweep (it undercounts
  flaky 768 types). `matchmedia` 3/3 CRASH here (`S3` x2, `S2` x1) vs 0/1 MISS in V907 —
  flaky race, 3/4 crash across probes, not a sweep artifact. `oob-v0`/`oob-v32` MISS
  (save-count OOB dead, same-object holds), forged-size `oob-ab9` CRASH as expected.
  Readable fake DEAD 0/57. See "Cross-Type" UPDATE below. Next: geometry tuning of the two
  new hit families (V909).
- **Geometry tuning + matchmedia x3 more** (2026-11-06): **RESOLVED.** **V909** (`probes/canvas-uaf/v909-geometry.html`,
  2026-11-06 17:43-17:44, beacons 10183-10217): 17 cases = 7 MISS, 10 CRASH, 0 SUSPECT.
  `urlsp` peak only at 96 (2/2, others MISS); `imagedata` 768 family 5x `S3-tagged` read + 1x `S2`
  spray (`96x2`), controls `16x11`/`22x8` MISS; `matchmedia` 3/3 new (`S3` x3, 6/7 total).
  Readable fake DEAD 0/17. See "Cross-Type" UPDATE below. Next: mapped-anchor harvest (V910).
- **Mapped-anchor harvest** (2026-11-06): **RESOLVED (JSC dead).** **V910** (`probes/canvas-uaf/v910-anchor.html`,
  2026-11-06 18:41-18:42, beacons 10256-10284): 14 cases = 11 MISS, 3 CRASH, 0 SUSPECT.
  All 10 JSC pointer candidates MISS (`lw=206`, taggers won) — they do not reclaim the 768B WebCore slot even at
  80/90/96/100. Controls `imagedata`/`abzero`/`abfake` CRASH at read, `same-none` MISS. Conclusion: JSC butterflies
  do not share the WebCore FastMalloc 768 class (or GC pins them). Anchor must come from WebCore 768, not JSC.
  Next: WebCore fine-tune (V911).
- **WebCore fine-tune** (2026-11-06): **RESOLVED (tuning dead for leak).** **V911** (`probes/canvas-uaf/v911-finetune.html`,
  2026-11-06 18:54-18:56, beacons 10297-10355): 29 cases = 23 MISS, 6 CRASH, 0 SUSPECT.
  New read hits: `blob-8x768` + `blob-16x768` (768 exact, 800 MISS), `text-736` (768/800 MISS — narrow sweet spot),
  `urlsp-92` (92-96 window, 88/100/104 MISS). Plus `imagedata`/`abzero` controls CRASH. Fine-tuning finds more
  crashes, never a readable value. Size alone does not make +112 a valid Vector.
  Next: pointer-derived numbers recon (V912, no UAF).
- **Pointer recon** (2026-11-06): **RESOLVED (no anchor).** **V912** (`probes/canvas-uaf/v912-recon.html`,
  2026-11-06 19:02-19:02, beacons 10379-10395): ~15 families in one load, no crash — no pointer-derived number found.
  `performance.memory`/`AudioContext`/`eventCounts` absent; `toString` shows no `0x...`; error stack is URL:line:col;
  typed offsets exact; randoms are fresh per load. Constants confirmed (no WASM/SAB/WebGL/Offscreen/IDB).
  Next: tee nonce readback (V913, fresh nonces vs foreign data).
- **Page sweep engine (2026-11-07): **V920** (probes/canvas-uaf/v920-pagesweep.html).
  The full exploitation of BOTH forge dimensions: m_buffer (64-bit base) AND m_size (32-bit index,
  x400 multiplier, JS-rewritable between reads). Engine: random 0x4000-aligned candidates in the
  libWebKit range [0x800000000, 0x900000000); each candidate probes its page at 400B steps
  (41 probes = the page content); mapped = 40 bytes leaked per probe and the sweep continues to
  the next page; unmapped = crash = the region boundary. Resumes across reloads automatically
  (memory-paced: 60 probes/load, reused views, 4s delays; zone override ?zone=0x...).
  The first V920-HIT beacon = the first leaked memory bytes on 14.20 - the wall breaks.
  Open until the sweep completes (100 candidates) or a hit pins a module base
  (ELF 0x464C457F backward sweep in the follow-up).
- **m_size address sweep (2026-11-07): **V919 RUN 1 - mechanism works, range wrong (2026-11-06
  23:32-23:33 UTC, beacons 11012-11062).** forge-ctl CRASH at k=1 = the forge+deref mechanism
  VALIDATED. All 20 random 0x4000-aligned candidates in [0x800000000, 0x900000000) crashed at k=1
  (base-unmapped) - 20/20 miss. Either 14.20 module density in that range is very low, or (more
  likely) 14.20 loader moved the modules out of the 7.00-13.60 range. same-none MISS + controls
  CRASH (harness valid). NOTE: 21 back-to-back crash-reloads in ~90s triggered the PS5 system
  "not enough free memory" dialog - fixed: views reused (no per-probe allocations), probes/load
  100->60, sweep reload delay 700ms->4000ms. **Assessment: without ONE known-mapped anchor, a
  crash-oracle search over a 48-bit ASLR space is computationally infeasible (sparse mappings,
  1 candidate per crash-reload). The browser-only path has hit a hard computational wall.**
  Remaining realistic unblocks: (a) RTSP post-auth research (needs PSN registration), (b) new
  WebKit info-disclosure bug (WK-1400 source audit), (c) scene intel - a single 14.x
  WebContent address from anyone with klog access immediately unblocks the sweep.
  (probes/canvas-uaf/v919-msize-sweep.html).
  The missing dimension from the review: V906 fixed m_size=1 (one address per load), but the read is
  *(m_buffer + (m_size-1)*400 + 48) with BOTH m_buffer and m_size in our AB - m_size is a 32-bit index
  (x400 multiplier) JS-rewritable between reads. From any base, m_size covers base..base+1.7TB in
  400B steps; a mapped probe leaks 8 bytes (x5 offsets) and the sweep CONTINUES in the same load;
  an unmapped probe crashes (= the region boundary - the crash itself maps memory). Target:
  libWebKit base range [0x800000000, 0x900000000) 0x4000-aligned (site.js). 24 cases: forge-ctl +
  20 random candidates + controls; sweeps resume across loads (100 probes/load, 1500/case cap).
  Open until beacons are read. A hit pins a module base (ELF 0x464C457F) and unblocks the whole chain.
- **V917+V918: the official PS5 WebKit chain on 14.20 - BOTH bugs PATCHED (2026-11-07).**
  **V917** (probes/canvas-uaf/v917-replacestate.html, beacons 10585+): establishPrimitive()
  (the FW 7.00-13.60 ARW chain, inlined) fails at its FIRST step on 14.20: every attempt =
  setup failed: Error: Scope not leaked. - the super+Proxy scope leak returns undefined
  (= spec behavior = the JSC bug is fixed in 14.20 WebKit).
  **V918** (probes/canvas-uaf/v918-clone-probe.html, beacons 11001+): (a) the ROOT bug -
  history.state returning the corrupted internal clone graph (len 0x50001, index-2 desync) -
  is ALSO dead on 14.20: the exact 13.60 storeHistoryGraph() returns a CLEAN clone
  (len=65536, idx1eq2=SAME, idxLast=-64000 as a plain number). (b) 9 scope-leak variants
  (target trap / fixed obj / Reflect / super-set / plain proxy / computed key / call-this /
  proto swap): all spec-compliant, no internal object leaked. Also verified from Windows
  (identical results) - the probe itself is sound.
  **Verdict: the official chain requires two WebKit bugs; BOTH are patched in 14.20 WebKit
  (WK-1400). The chain is definitively dead on 14.10/14.20.**
  **Surviving intelligence:** PS5 libWebKit base lives in [0x800000000, 0x900000000),
  0x4000-aligned (site.js validation across FW 7.00-13.60) - feeds the V919 m_size sweep.
- **Dual-UAF + stale-read + dash-forge** (2026-11-07): **RESOLVED - all four surfaces DEAD.**
  **V916** (probes/canvas-uaf/v916-dual-uaf.html, 2026-11-06 22:32-22:33 UTC, beacons 10551-10583):
  16 cases = 15 CRASH + 1 MISS + 0 SUSPECT.
  (1) **Stale-read DEAD (wall real):** single-ctl CRASH at S4-read-w1, dual-zero CRASH at S4-read-w1 -
  reading an unreclaimed freed context crashes, period. The 11-07 re-interpretation of V683
  (blaming uncontrolled reclaim) was WRONG; the wall is structural (vtable/wrapper gate). The
  freed-memory read channel does not open.
  (2) **Dual-UAF structurally impossible (as designed):** the second getter's getContext('2d')
  returns the EXISTING context (w2 = null in every DONE detail; dual-t12 lw1=205 with no lw2) -
  a canvas holds one 2d context, so no second 768B slot ever frees. Two slots would need two
  canvases = two triggers (the known heap-corruption hazard).
  (3) dash-forge / dash-zero: never reached - blocked by the W1 unreclaimed crash (no-alias path).
  (4) fill-* reads: blocked by the same W1 crash (fill-alias/fill-freed/fill-pattern all CRASH at
  S4-read-w1; fill-pdrop CRASHED at S1-trigger - pattern creation inside the getter is unstable).
  mmcl eq24/mix24/12/32: 4/4 CRASH at S4-read - the matchMedia clause family reproduces 8/8 across
  V914+V916 regardless of clause shape/count; crash family confirmed, still no read.
  Controls imagedata-16x12 + abzero CRASH (harness valid).
  **Verdict: in-browser research is now COMPLETELY exhausted.** 191 cases across V907-V916 +
  recon + tee, 0 SUSPECT. The canvas UAF is capped browser-side at: reliable DoS (5 crash-at-read
  families), state-field R/W via alias (V573/V630), and the mapped/unmapped oracle (V906).
- **Class census: pointer-at-+112 candidates** (2026-11-07): **RESOLVED (0 SUSPECT, allocator-math candidates dead).**
  **V914** (probes/canvas-uaf/v914-classcensus.html, 2026-11-06 21:11-21:15 UTC, beacons 10404-10543):
  46 cases = 40 MISS, 6 CRASH, 0 SUSPECT.
  - rules 64-100 (7 cases): ALL MISS - the Vector<RefPtr<CSSRule>> capacity math did not land; CSSRuleList
    allocations never took the 768B slot.
  - toklist 86-98 (4): ALL MISS - SpaceSplitStringData exact-size math also wrong (header size or allocator path differs).
  - mmcl 16/20/24/28: **4/4 CRASH at S3-tagged - NEW reliable crash-at-read family** (matchMedia with
    clause-chained queries; corroborates matchmedia flaky hits in V908/V909 - the media-query parse path
    allocates in the 768B class). +112 in that allocation is not a readable pointer.
  - 18 rich events + 10 misc constructibles: ALL MISS (sizes outside the class).
  - Controls: same-none MISS (lw=213), imagedata-16x12 + abzero CRASH (harness valid).
  Verdict: 175 total cases across V907-V914 + recon + tee, all 0 SUSPECT. Even structure allocations that
  land in the class carry no readable pointer at +112. **In-browser leak hunt formally exhausted.**
  The chain is capped browser-side at: reliable DoS (urlsp96/imagedata-768/blob-768/text-736/mmcl crash-at-read)
  + state-field R/W via alias (V573/V630) + mapped/unmapped oracle (V906).
- **tee() nonce readback** (2026-11-06): **RESOLVED (self-data only, tee closed).** **V913** (`probes/canvas-uaf/v913-tee-nonce.html`,
  2026-11-06 19:11, beacons 10396-10403, no crash): fresh `crypto.getRandomValues` nonce per case + `0xA5` pad.
  `NONCE-BOTH`: nonce `820bf1ed...` -> r0 `64:m=1:o=1`, r1 `64:m=1:o=1` (both branches return exactly the enqueued
  bytes, same object, exact length). `NONCE-64`: nonce `02d78b43...` (different) -> r0 `96:m=1:o=1` exact.
  `INC` (+7 control) `m=1`. Two independent nonces inside one run both round-tripped exactly: the V827 fixed hex
  was self-data, not heap determinism. **No foreign bytes, no length mismatch, no pointer-like hex — tee() gives
  no controlled read.** Combined with V904 (under-yield = short-vector DoS), the tee() branch is closed.

### Nov 4 additions (V689 canaries + scan) - DEAD
- **V689 `lw0` / `restore` / `save` / `bg` / `attr` / `canvas`:** all OBLOCK on
  AB-owned zeroed slot. Early-return setters/getters do NOT survive the vtable gate
  at +0. Confirms V688's conclusion: only pure JSC access (`js`) survives; every
  JS->C++ call on a zeroed slot faults.
- **V689 `scan`:** OBLOCK (twice). GC churn kills the renderer on AB-owned slot.
  No leak from scan.
- **V689 `js`:** survived once (seq 2244) then crashed once (seq 2304). Pure JSC
  access is intermittent, not stable, on AB-owned slot.

### Nov 5 additions (STG5 + V682 text) - DEAD
- **v592 `stage=5` with `spray=200`:** OBLOCK during the butterfly spray phase,
  before POST. Repeated BOOT + CONFIG with no STG5/DONE beacon. Root cause is
  OOM/GC pressure from 200 × 14,808-byte Array allocations (~3 MB), not a pointer
  dereference. The spray itself kills the renderer.
- **v592 `stage=5` with `spray=100`:** OBLOCK during the butterfly spray phase,
  before POST. Six consecutive attempts (seq 2314-2329) all crashed after
  BOOT + CONFIG(spray=100). Halving the spray count does not avoid OOM/GC
  pressure. The butterfly reclaim path for the stateStack buffer is not viable
  on PS5 14.20.
- **V682 `text a=704`:** all variants (ctx=1/8/16/24/32/64) resulted in
  `ctxhit=1, sus=0`. The text buffer never reclaimed the 768B slot; tagged real
  CanvasRenderingContext2D objects always won. Cross-type string-buffer reclaim
  is dead.

### Nov 5 additions (HTMLParser CE microtask bypass) - DEAD
- **V700 CE double-parent / microtask bypass:** all 5 tests completed without
  crash. `document.open()`, `document.write()`, `appendChild(this)` to an
  alternate parent, `removeChild(this)`, and `iframeDoc.open()` inside a custom
  element constructor all executed, but the parser's post-construction
  validation correctly handled each case. No dual parentNode, no bypass, no
  UAF. The lead from CONFIRMED_VULNS.md is dead on PS5 14.20.

### Nov 5 additions (Font parser loca OOB) - DEAD
- **V182 font parser OOB read via loca table:** comprehensive probe (p182)
  tested padding OOB, heap OOB (offsets 4-4096), heap spray (1000 × 4KB
  marker-filled ArrayBuffers), and .notdef OOB. All results showed px=0 and
  diff=0 versus baseline; no spray marker appeared in rendered output.
  FreeType on PS5 14.20 either validates loca/glyf offsets or returns a
  notdef fallback. The info-leak path is dead. This confirms the DEAD_ENDS.md
  entry and contradicts the optimistic note in FINDINGS.md.

### Nov 5 additions (WebAudio unavailable) - NOT A SURFACE
- **V800 WebAudio recon probe:** `AudioContext`, `webkitAudioContext`, and
  `OfflineAudioContext` are all undefined on PS5 14.20 browser. Every test
  threw `TypeError: undefined is not a constructor`. The entire WebAudio
  subsystem is unavailable as an attack surface.

### Nov 5 additions (APNG overread) - DEAD / FALSE CLAIM
- **V674 APNG overread info leak:** The `op=apng` probe in
  `canvas-uaf/v592-ctl.html` builds a malformed animated PNG (3 frames
  claimed, 2 provided). On PS5 14.20 the image fails to decode with
  `APNGERR load-fail`. No pixel data is returned and no heap pointers are
  leaked. The claim that "APNG overread leaks 1651 heap pointers" is not
  reproducible on retail PS5 14.20 hardware.

---

## Summary

| Category | Investigated | Dead | Alive/Safe |
|----------|-------------|------|------------|
| JSC Engine | 10 | 10 | 0 |
| Streams API | 4 | 4 | 0 |
| RAB | 4 | 3 | 1 |
| DOM / Rendering | 13 | 9 | 4 (1 ALIVE: Canvas UAF) |
| CVE Audit | 5 | 5 | 0 |
| Kernel / Syscall | 3 | 3 | 0 |
| Info Leak (Canvas UAF) | 10 | 10 | 0 |
| **Total** | **49** | **44** | **5** |

**Nov 3 update:** +4 more dead ends from the V680-V688 on-device runs (cross-type object
reclaim, inline state stack read, non-Vector member read, AB-owned slot calls). They are
listed above but not folded into the 49/44/5 counts, which describe the original audit.

Note: Canvas getContext() UAF (CVE-2026-43720) was previously listed as dead due to IsoHeap but has been **retracted**  - IsoHeap is OFF on PS5. It is now the primary exploitation vector with confirmed R/W. See CONFIRMED_VULNS.md.
