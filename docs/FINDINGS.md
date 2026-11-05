# Findings

All findings are validated on device (PS5 14.10) or verified against WebKit-1200 source.

## PS5 14.20 Browser Capability Snapshot (V900)

Probe V900 mapped which Web APIs are exposed in the PS5 14.20 browser.

**Available (21):** MediaSource / SourceBuffer, BroadcastChannel, CacheStorage,
localStorage / sessionStorage, FileReader / Blob / URL.createObjectURL,
Web Animations (Animation, KeyframeEffect, DocumentTimeline), SVG / ShadowRoot /
customElements, WebSocket / Worker / SharedWorker, ImageBitmap /
createImageBitmap, Streams API.

**Unavailable (14):** AudioContext / webkitAudioContext / OfflineAudioContext,
WebGL / WebGL2, RTCPeerConnection, ServiceWorker, IndexedDB, Gamepad,
Notification / Permissions, ReallocatableArrayBuffer, SharedArrayBuffer,
WebAssembly.

This rules out WebAudio, WebGL, WebRTC, ServiceWorker, IndexedDB, and
WebAssembly as attack surfaces on this firmware. The most promising remaining
browser subsystems are MediaSource Extensions (MSE), Web Animations, SVG, and
Streams API.

### MSE Recon (V910)

Basic MediaSource Extensions recon probe tested `appendBuffer` with random
junk, a truncated MP4 box, invalid `remove()` ranges, rapid `appendBuffer` +
`abort` cycles, `changeType` with multiple codecs, and rapid
`addSourceBuffer` / `removeSourceBuffer` cycles. All tests completed without
a renderer crash. Invalid inputs were rejected by validation (`TypeError` or
`DOMException`). No immediate primitive was uncovered, but deep codec-parser
fuzzing was not attempted.

### Streams API Recon (V940/V941)

Probe V940 tested ReadableStream/WritableStream/TransformStream basics,
`tee()`, `pipeTo()`/`pipeThrough()`, highWaterMark edge cases, and rapid
create/read/cancel cycles. The probe stopped at `TRANSFORM-PRE`. Follow-up
probe V941 isolated the issue: `TransformStream` creation, `getWriter()`, and
`getReader()` all succeed, but the first `writer.write()` hangs indefinitely
on PS5 14.20. Basic `ReadableStream` (without `TransformStream`) works.

**Status:** TransformStream is unusable as an attack surface due to the hang.
ReadableStream basics work, but no memory-safety primitive was uncovered.

### APNG Overread Info Leak (V674) â€” DEAD / FALSE CLAIM

Probe `v592-ctl.html?op=apng` builds an animated PNG claiming 3 frames but
providing only 2, intending to trigger an overread in the PNG decoder. On PS5
14.20 the image fails to load (`APNGERR load-fail`); no pixel data is
returned and no heap pointers are leaked.

This contradicts the GitHub repository's claim that "APNG overread leaks
1651 heap pointers (V674)". The claim appears to be documentation-only and
is not reproducible on retail PS5 14.20 hardware.

**Status:** DEAD. APNG is not a viable info-leak primitive on this firmware.

### CSSFontFaceSet reference_wrapper UAF Diagnostic (V920)

Probe V920 tested mutation of `@font-face` rules during `FontFaceSet`
iteration (`document.fonts.load()` and `check()`), including deletion of CSS
rules, removal of the parent `<style>` element, and rapid
`document.fonts.delete()` calls. All tests completed without a renderer crash.
The classic `FontFace.prototype.then` hook did not trigger during the
`STYLEMUTATION` test (`triggered=0`), suggesting the synchronous promise
thenable path is not reached in this context on PS5 14.20. The
reference_wrapper UAF remains unconfirmed as a reachable primitive.

## Confirmed Bugs

### 1. MetadataTable Integer Overflow (Bug 317632 / CVE-2026-64784)

`UnlinkedMetadataTable::finalize()` uses an `unsigned` accumulator with no overflow check. With 38,348,816 op_call sites at stride 112, the accumulator wraps from 4,295,067,392 to 100,096. The allocator reserves 100KB. The interpreter writes 4.29GB forward into heap memory.

**Status: BLOCKED.** The overflow triggers and corrupts heap objects, but the 4.29GB forward sweep crashes the process when it exits mapped virtual memory. Maximum working spray is ~240MB (2400 buffers), covering less than 6% of sweep distance. No early exit exists in finishCreation(). See `docs/bugs/metadatatable-overflow.md` for the full writeup.

### 2. JSString Header Corruption (via MetadataTable)

The sweep corrupts JSString.m_fiber in MarkedSpace cells. All 14 target strings report `.length = 81400` after the overflow. StringImpl backing data stays intact (charCodeAt returns original 0x41). The corruption is in the JSString header, not the character data.

Validated: p146, p147, p148 on device.

### 3. Forward Write Directionality (Proven)

finishCreation() sweeps FORWARD only (higher addresses). Targets placed before the metadata buffer are never reached. Bait and switch heap groom (allocate baits, then targets, free baits, trigger overflow) controls where the sweep lands.

Validated: p143 (no corruption when targets below), p144 (corruption when targets above).

### 4. CSSFontFace UAF (Source Verified)

`CSSFontFaceSet::matchingFacesExcludingPreinstalledFonts` (line 381) returns `std::reference_wrapper<CSSFontFace>` (non-owning). The fix changed this to `Ref<CSSFontFace>`. Also `fontLoadEventOccurred()` calls `pump()` and client callbacks without `Ref<CSSFontFace> protectedThis`. Only `timeoutFired()` and `fontLoaded()` have that protection.

**Status: TESTING.** Probe p170 used WOFF2 (rejected on PS5). Probe p175 uses TTF from ArrayBuffer. Awaiting device results.

### 5. Font Parser OOB Read via loca Table (DEAD)

Initial V180A tests suggested FreeType accepted fonts with loca table offsets
past the glyf table boundary. However, comprehensive probe V182 (p182) tested
padding OOB, heap OOB (offsets 4-4096), heap spray (1000 Ã— 4KB marker-filled
ArrayBuffers), and .notdef OOB. All results showed px=0 and diff=0 versus
baseline; no spray marker appeared in rendered output.

**Conclusion:** FreeType on PS5 14.20 validates loca/glyf offsets or returns a
notdef fallback. No OOB read primitive exists through this path.

### 6. ClonedArguments Butterfly UAF (DEAD: Conservative Scan)

ClonedArguments.cpp:289 butterfly pointer stale after Proxy trap reentrancy. V221/V243/V246 confirmed: Proxy trap fires, hole position returns Proxy value, but old butterfly is NEVER freed.

Root cause (source verified + device confirmed): conservative stack scanning keeps the stale `data` pointer alive. The C++ stack frame for `copyToArguments` is still on the stack when the Proxy trap fires. JSC's `ConservativeRoots.cpp:66-82` scans the stack for pointer-aligned values and adds any MarkedBlock cell pointer as a GC root. Even with JSArray spray (correct allocator space), `marksConveyLivenessDuringMarking` keeps the butterfly alive across GC cycles.

V246 device results: all 8 rounds show original sequential values at non-hole positions, `0xBEEF` at hole position 5, no CAFE spray markers anywhere. ArrayBuffer spray (V221/V243) and JSArray spray (V246) both fail.

**Status: DEAD.** Cannot free butterfly while `copyToArguments` is on the call stack.

## Confirmed Dead Ends

### Yarr Regex C3 Position Corruption
1-unit displacement in C3 character class handling always causes match failure. Cannot produce controlled out-of-bounds reads. Verified in source.

### RAB byteLength Inversion
ResizableArrayBuffer has an inverted bounds check that allows conceptual OOB access, but all sink paths (SubtleCrypto, TextDecoder, DataView) throw TypeError before reaching the underlying buffer. Every read/write path correctly re-validates length.

Validated: p160a (TypeErrors on all stale-read paths).

### ClonedArguments propertyCapacity
PreciseAllocation for ClonedArguments has outOfLineCapacity=4 and canRealloc always returns false. Cannot trigger reallocation to create a type confusion.

### Relapse WebKit CVE Set
All known Relapse bugs (prior firmware exploit chain) are patched on 14.10.

Validated: p160 on device.

### Streams API BYOB Reader
BYOB reader ctor/elementSize mismatch is real (acknowledged by FIXME comments in source) but TypedArray constructor bounds checking prevents all OOB paths. Every combination results in RangeError or truncated but in-bounds views.

### ReadableByteStreamController
Not implemented on PS5. V190A-P4-ERR: "TypeError: ReadableByteStreamController is not implemented". BYOB exploitation paths blocked.

### SVG Font GSUB Placeholder Truncation
SVGToOTFFontConversion.cpp line 119 truncates delta to uint16_t via implicit conversion. Triggers when GSUB ligature subtable exceeds 64KB (~10923 ligature pairs). However, the truncation corrupts offsets INSIDE the OTF buffer, not heap metadata. overwrite16 writes a wrong VALUE at a correct LOCATION. This is font data corruption, not a WebKit memory safety issue. Would only be exploitable if FreeType itself misparses the resulting malformed GSUB table.

## Audited Surfaces (No Bugs Found)

| Surface | Agent | Result |
|---------|-------|--------|
| Integer overflows (full JSC) | overflow-hunt | MetadataTable is unique. All other subsystems use Checked<>/RELEASE_ASSERT |
| ASLR leak primitives | aslr-binary-audit | Error.stack has no addresses, ArrayBuffer always zeroed, performance.now() is 1ms resolution |
| MetadataTable alternative strategies | metatbl-alt-strategy | No shortcut for sweep. No early exit, link() safe, destructor safe |
| SerializedScriptValue (structuredClone) | clone-deserialize-audit | Well hardened. No type confusion, no UAF, no uninit memory |
| Streams API + SubtleCrypto | streams-api-audit | BYOB mismatch is real but TypedArray bounds checking blocks all OOB |

## Device Recon Results (Session 10)

### FontFace API (p161a)
FontFace and document.fonts.add work on PS5. Parser rejects most malformed fonts (NetworkError). Two edge cases accepted:
- numGlyphs=0xFFFF (65535) loads without error
- unitsPerEm=0 loads AND renders on canvas (potential div-by-zero in layout math)
- WOFF2 is rejected
- ArrayBuffer source loading works (no data URL needed)

### Font Parser Fuzz (p180a, V180A)
12 corruption variants tested against FreeType via FontFace API from ArrayBuffer.

| Test | Corruption | Result |
|------|-----------|--------|
| T0 | Valid baseline | LOADED + RENDER + CANVAS-OK |
| T1 | numGlyphs=0xFFFF | LOADED |
| T2 | numHMetrics=0xFFFF | LOADED |
| T3 | Bad loca format | LOADED |
| T4 | Huge cmap segCount | LOADED |
| T5 | LOCA OOB OFFSET | LOADED (OOB read potential) |
| T6 | Dir size overflow | REJECTED |
| T7 | Dir offset past EOF | LOADED (OOB read potential) |
| T8 | maxp zero glyphs | LOADED |
| T9 | Bad magic number | LOADED |
| T10 | Huge numTables | LOADED |
| T11 | unitsPerEm=0 | REJECTED |

T5 and T7 are the critical findings. FreeType accepts fonts with offsets pointing outside the valid table data.

### Image Decoders (p161b)
All 7 formats supported: PNG, JPEG, GIF, WebP, BMP, SVG, ICO. createImageBitmap available. Edge cases:
- Truncated PNG IDAT loads successfully (potential uninit memory read)
- 0x0, 65535x65535, 32768x32768, INT_MAX width all rejected
- CIB huge crop clamped to 1x1

---

## Canvas UAF Exploitation Chain (CVE-2026-43720)

### IsoHeap OFF on PS5

`WTF_MAKE_ISO_ALLOCATED` compiles to standard FastMalloc on FreeBSD/PlayStation. `BPLATFORM(PLAYSTATION)` at BPlatform.h:341 disables IsoHeap. Gigacage also disabled  - AB backing stores share the same heap as JSC/WebCore objects. Confirmed by Synacktiv writeup and CSSFontFace exploitation research.

### Same-Type Reclaim + Bidirectional R/W (V573)

BMR trigger (bitmaprenderer outer + 2d inner via defineProperty getter) confirmed working on device. 500x Canvas2D spray reclaims freed 768B context slot. Stale wrapper aliases spray context at index 9. All 12 Canvas2D APIs work through alias: lineWidth, miterLimit, globalAlpha, fillStyle, strokeStyle, getTransform, setTransform, getLineDash, setLineDash, measureText, save, restore.

### State Buffer Reclaim (V587/V589)

8x `save()` inside getter grows `Vector<State>` out-of-line to ~6400 bytes (bmalloc class 6656). BMR trigger frees inner context + state buffer. AB spray can reclaim the freed state buffer. V589 confirmed BMR trigger works (`uaf-ok: inner=OK`) but crashes during spray phase  - likely GC pressure from 500+ AB allocations.

### OOB State Stack Read  - Info Leak Candidate

**Key insight:** After BMR free + same-type reclaim, the stale wrapper retains `m_stateStack.m_size = 9` (from 8 saves) while the new context has `m_size = 1`. Reading `m_stateStack.last()` through the stale wrapper indexes at `buffer[8]` = offset 3200 = **2800 bytes past the end** of the new context's 1-State buffer.

This reads from adjacent heap allocations. A 48-bit x86-64 pointer is exactly representable as IEEE 754 float64, so `lineWidth` returns the raw pointer value as a JavaScript number.

**libpas allocator behavior:** Out-of-band bitmap tracking  - freed chunks retain all stale data. No in-band freelist pointers. Freed memory is NOT zeroed.

**Status:** Probe needed to confirm non-zero pointer-like values from OOB read on device.

### Exploitation Path

1. OOB state stack read â†’ heap address leaked as float64
2. Fake lineDash `Vector<double>` in AB: set `m_buffer = TARGET`, `m_capacity = N`, `m_size = N`
3. `setLineDash([v1,...,vN])` â†’ in-place memcpy to TARGET = arbitrary write
4. `getLineDash()` â†’ reads from `m_buffer` = arbitrary read
5. Read JSGlobalObject vtable â†’ binary base â†’ ROP gadgets
6. Vtable hijack â†’ ROP chain (x86-64, no PAC, no JIT)
7. Kernel escalation via reachable syscall surface


## On-Device Beacons (Nov 2)

### V650 â€” Crash Oracle (PS5 14.20)
- UAF trigger OK (bmr=OK, getter=true, inner=OK) on every attempt.
- 30 targets scanned (stack/exe/PIE/lib/mmap/ps5-specific) â€” all crashed, no HIT.
- Result: EXHAUSTED. Forged stateStack -> lineWidth read crashes on all tested addresses.
- Implication: ASLR defeat via forged stateStack is not straightforward; tested ranges unmapped.

### V592 â€” Butterfly Harvest (PS5 14.20)
- saves=32, cap=37, buf=14800, lwOff=12848 â€” consistent across 19 runs (crash/reload ~3s).

### V660 â€” 640MB Heap Spray (PS5 14.20)
- 40x16MB spray, 72 probes, fail=false â€” succeeded without crash (3 runs).

### V569 â€” Calibration + Scan (PS5 14.20)
- AB backing stores zeroed (AB0-5 = 0) â€” Gigacage disabled / shared heap.
- Scan mode tested (0x200000000, 0x200025800, 0x20004b000) â€” no hit.
ï»¿
## On-Device Beacons (Nov 3) - V592 control harness

Harness: `probes/canvas-uaf/v592-ctl.html` (same CVE-2026-43720 trigger as `v592.html`,
then exactly one controlled action). Beacons land in `beacon log` as `V592C-*`.

### Liveness and same-type reclaim
- `op=ping` -> `PING trigger-returned` + `LATE alive=1`. Trigger and renderer survive.
- `op=reclaimctx&n=16` -> `RREAD ctxreclaim n=16,made=16,lw=0x4012456d5cfaacda` (= 4.5678),
  reproduced twice. Same-type (CanvasRenderingContext2D) reclaim of the freed 768-byte
  context object is confirmed and stable.

### V592 stage bisection (staged pre-read)
`probes/canvas-uaf/v592.html` gained `stage=1..4` (retry delay raised to 4000/8000 ms).

| stage | action | result |
|-------|--------|--------|
| 1 | trigger, beacon only | survives: `V592-STG1 trigger-ok,ctx=true` + `DONE` |
| 2 | trigger, pre-read freed ctx, beacon | crash right after `CONFIG`, no STG2 |
| 3 | trigger, pre-read + reclaim, beacon | crash right after `CONFIG`, no STG3 |
| 4 | trigger, pre-read + spray, beacon | crash right after `CONFIG`, no STG4 |

Conclusion: the crash is the *pre-read* (`savedCtx.lineWidth` etc.) on freed-but-not-yet-
reclaimed memory. Reading only after a same-type reclaim works.

`stage=5` (trigger -> butterfly spray -> post-read, no pre-read) is now deployed.
It tests whether the stage-2 crash depends on the free-list state: if the state
buffer is reclaimed by butterflies first, the stale `m_stateStack` points at live
array storage instead of a freed block. If the post-read then survives, the read
is a usable OOB primitive and the leak detector reports the marker bits.

### Direct ArrayBuffer reclaim crashes
- `op=direct&ablen=768&n=10` emits `V592C-ABSPRAY n=10,len=768,direct=true` and then
  never emits `RREAD` - the renderer dies.
- Same with `fill=zero` (new AB is already zero-initialised, so a hit would read
  `lineWidth = 0` safely). It still crashes.
- Cause: a 768-byte AB backing store landing in the freed context object overwrites
  `m_stateStack` (at +112) with zero/garbage; the first field read dereferences that
  pointer. Fixing this needs pointer forging, which is out of scope for this repo's
  probe-only work.

### APNG is not implemented
- `op=apng` returns `V592C-ERR unknown-op:apng`.
- No `v674` file and no APNG probe exist in this repo (or in the rebranded copy).
- The README table row `ASLR Defeat | CONFIRMED | APNG overread leaks 1651 heap pointers
  (V674)` is documentation only and must not be treated as a working primitive.

### Harness bug fixed (once-guard)
The once-guard wrote its key to whichever storage `storage()` returned (sessionStorage
first), while `resetall` cleared only that same storage. A guard written in one storage
survived a reset performed when the other storage was returned, producing permanent
`BLOCKED ... once-guard` loops (`V592R` was blocked 8/8 times).
Fix in `v592-ctl.html`:
- `eachStorage` / `guardRead` / `guardWrite` / `guardClear` / `guardClearAll` helpers that
  always touch **both** sessionStorage and localStorage.
- `reset=1` clears the specific key in both storages; `guard=0` bypasses the guard entirely.
- `resetall` clears all `v592c_ / v592r_ / v592w_ / v592s_` keys in both storages.
- The `DONE` timer now clears the key on a clean finish, so a successful op can be re-run
  without a manual reset; a crashing op never reaches the timer and stays guarded.

### New read-only diagnostic: `reclaimread`
`op=reclaimread&n=N` reclaims N tagged 2d contexts (each with `lineWidth=4.5678`,
`miterLimit=8.88`, `globalAlpha=0.33`, `lineDashOffset=6.66`, `shadowBlur=9.99`) and then
reads all five fields through the stale wrapper. This distinguishes a complete alias
(all five match) from a partial one (only `lineWidth` happens to look right).
No writes, no pointer forging.

## On-Device Beacons (Nov 5) - STG5 OOM + V689 intermittent + 13.60 reference

### STG5 (spray=200) â€” CRASH / OBLOCK (seq 2292-2303)
- BOOT + CONFIG repeated, no POST, no STG5, no DONE.
- Renderer dies during the butterfly spray phase.
- **Root cause:** OOM/GC pressure from 200 Ã— 14,808-byte Array allocations (~3 MB)
- **Status:** DEAD at spray=200. Not a pointer issue; the spray itself kills the renderer.

### STG5 (spray=100) â€” CRASH / OBLOCK (seq 2314-2329)
- Attempted 6 times in a row after reclaimread.
- Each attempt: BOOT + CONFIG(spray=100) then crash/reload; no POST, no STG5, no DONE.
- **Conclusion:** even halving the spray count does not avoid the OOM/GC pressure.
- **Status:** DEAD. Butterfly reclaim of the stateStack buffer is not viable on PS5 14.20.

### V689 canaries â€” all CRASH except js (intermittent)
| op | Result | Meaning |
|----|--------|---------|
| js | survived once (seq 2244), crashed once (seq 2304) | intermittent / slot unstable |
| lw0 | OBLOCK | early-return setter crashes |
| restore | OBLOCK | early-return crashes |
| save | OBLOCK | crashes |
| bg | OBLOCK | crashes |
| attr | OBLOCK | crashes |
| canvas | OBLOCK | crashes |
| scan | OBLOCK (twice) | GC churn crashes, no leak |

**Conclusion:** On AB-owned zeroed slot, **every JS->C++ call crashes** (vtable at +0 is the gate). `js` pure-JSC access is intermittent, not stable.

### reclaimread n=16 â€” SUCCESS (seq 2222, 20:41:55)
| Field | Expected | Read | Match |
|-------|----------|------|-------|
| lw | 0x4012456d5cfaacda | 0x4012456d5cfaacda | âœ… |
| ml | 0x4021c28f5c28f5c3 | 0x4021c28f5c28f5c3 | âœ… |
| ga | 0x3fd51eb851eb851f | 0x3fd51eb851eb851f | âœ… |
| ldo | 0x401aa3d70a3d70a4 | 0x401aa3d70a3d70a4 | âœ… |
| sb | 0x4023fae147ae147b | 0x4023fae140000000 | âš ï¸ close, likely float32 truncation |

**Conclusion:** Same-type alias is **essentially complete** â€” 4/5 fields match exactly.

### V682 text a=704 â€” DEAD (all variants)
- Run 1 (seq 1802): crashed (no OSTEP)
- Run 2 (seq 2280): survived but `ctxhit=1, sus=0` (tagged contexts won)
- Runs 3-10 (seq 2436-2486, ctx=1/8/16/24/32/64): all survived, all `ctxhit=1, sus=0`
- **Result:** the text buffer NEVER reclaims the 768B slot. The tagged real
  CanvasRenderingContext2D objects always win.
- **Status:** DEAD. Cross-type reclaim via text buffer is not viable.

### 13.60 Relapse Exploit reference (informational)
Local copy at `13.60/`. README states chain:
> Browser stage uses JSC info leaks and a structured clone object pool mismatch to corrupt a typedarray. The kernel stage combines an address leak with an `aio_multi_wait` uaf race to establish kernel r/w.

Key primitives (documented for reference only; **not operational on 14.10**):
1. **Scope leak via `super.foo` + Proxy receiver** â€” `leakScopeObject()` returns the JSScope chain. V588 confirmed this is patched on PS5 14.10 (binary fix, returns `undefined`).
2. **Symbol.toString oversized string** â€” leaks `fakeHost` and `targetHolder` addresses through a corrupted Symbol string length.
3. **Structured clone pool mismatch** â€” corrupts a cloned `Uint8Array` in `history.state` to redirect its vector to an attacker-controlled `ArrayBuffer`, giving arbitrary read/write memory window.
4. **Kernel stage** â€” `aio_multi_wait` UAF race for kernel r/w (Phase 5 reference only).

**Relevance to 14.20:**
- All Relapse WebKit CVEs are patched on 14.10+ (confirmed by V588 and DEAD_ENDS.md).
- RAB present on 13.x but removed on 14.20 Slim.
- Offsets and vtable layouts differ; any 13.60 code is firmware-specific.
- **Use as reference for approach, not as copyable exploit code.**

### Summary table (Nov 5)
| Probe | Result | Status |
|-------|--------|--------|
| reclaimread n=16 | âœ… 4/5 fields match | alias complete |
| STG5 spray=200 | âŒ OBLOCK (OOM) | dead at 200 |
| STG5 spray=100 | âŒ OBLOCK (OOM/GC) | dead |
| V689 js | âš ï¸ intermittent | unstable |
| V689 lw0/restore/save/bg/attr/canvas | âŒ all OBLOCK | vtable gate |
| V689 scan | âŒ OBLOCK | no leak |
| V682 text a=704 | âŒ ctxhit=1 all variants | dead |

## On-Device Beacons (Nov 4, session A + B) - reclaimread + V689 canaries

### reclaimread n=16 â€” SUCCESS (seq 2222, 20:41:55)
| Field | Expected | Read | Match |
|-------|----------|------|-------|
| lw | 0x4012456d5cfaacda | 0x4012456d5cfaacda | âœ… |
| ml | 0x4021c28f5c28f5c3 | 0x4021c28f5c28f5c3 | âœ… |
| ga | 0x3fd51eb851eb851f | 0x3fd51eb851eb851f | âœ… |
| ldo | 0x401aa3d70a3d70a4 | 0x401aa3d70a3d70a4 | âœ… |
| sb | 0x4023fae147ae147b | 0x4023fae140000000 | âš ï¸ (close, likely float32 truncation) |

**Conclusion:** Same-type alias is **essentially complete** â€” 4/5 fields match exactly. shadowBlur (sb) stored as float32 internally.

### V689 canaries â€” all CRASH except js
| op | Result | Meaning |
|----|--------|---------|
| js | âœ… survived (tag=[object CanvasRenderingContext2D]) | Pure JSC access works |
| lw0 | âŒ OBLOCK | early-return setter crashes |
| restore | âŒ OBLOCK | early-return crashes |
| save | âŒ OBLOCK | crashes |
| bg | âŒ OBLOCK | crashes |
| attr | âŒ OBLOCK | crashes |
| canvas | âŒ OBLOCK | crashes |
| scan | âŒ OBLOCK | GC churn crashes |

**Conclusion:** On AB-owned zeroed slot, **every JS->C++ call crashes** (vtable at +0 is the gate). Only pure JSC access (`js`) survives.

### V682 text a=704 â€” INTERMITTENT
- Run 1 (seq 1802): crashed (no OSTEP)
- Run 2 (seq 2280): survived (OSTEP + LATE alive=1, ctxhit=1, sus=0)
- **Result:** unstable. ctxhit=1 (tagged contexts won, not text buffer). sus=0.

### STG5 â€” NOT RUN
- 0 beacons. Pending.

### Summary table (updated)
| Probe | Result | Status |
|-------|--------|--------|
| reclaimread n=16 | âœ… 4/5 fields match | alias complete |
| V689 js | âœ… survived | pure JSC works |
| V689 lw0/restore/save/bg/attr/canvas | âŒ all OBLOCK | vtable gate |
| V689 scan | âŒ OBLOCK | no leak |
| V682 text a=704 | âš ï¸ intermittent | unstable |
| STG5 | â³ not run | pending |

## On-Device Beacons (Nov 3, session B) - V680-V688 results matrix

Second workstream, same bug, same server. Every row below is read back from
`beacon log`, not from memory. Goal: stop re-running experiments that already
have an answer.

| Probe | What it tested | Result | Conclusion |
|-------|----------------|--------|------------|
| V680-obj | 45+ candidate object types into the freed 768B slot | every entry `ctxhit=1, sus=0` | no candidate object took the slot; tagged real contexts always won |
| V681-vec | 14 vector/buffer candidates | every entry `ctxhit=1, sus=0`, `ODONE n=14` | same: cross-type vectors do not reclaim the slot |
| V682-span | exact-size array butterflies (arrX) + text | 10x `ctxhit=1, sus=0`; last entry `text a=704` crashed | butterflies miss; ONE unresolved crash (see below) |
| V683 | inline state stack after free (v=0, no saves) | `bare`, `baref`, `barew`, `baregrow` all OBLOCK; `barerec` survived | inline-state hypothesis dead: first touch faults even without an out-of-line stack |
| V684 | non-Vector members (`canvas`, `getContextAttributes`) | `probe` OBLOCK; `whoami` `made=24, hit=4, lw=0x4069800000000000, sameWrap=0` | non-Vector reads also die; same-type reclaim still works |
| V685 | ordered first touch | `OSTEP0` after the trigger, then OBLOCK | trigger is innocent; the FIRST touch of the dangling wrapper is the fault |
| V686 | AB(768) + `getContextAttributes` / path builder | `abattr` and `abpath` OBLOCK | PathImpl-pointer idea unreachable: the calls themselves fault |
| V687 | which AB size takes the slot | `sz=0 hit=7`, `sz=768 OBLOCK`, `sz=832 hit=10`, `sz=896 hit=4`, `sz=1024 hit=10` | **768 is the only size class that crashes** = AB(768) owns the slot |
| V688 | which call survives on an AB-owned slot | `idle` OK (x2), `gc` OK; `path`, `attrs`, `save` OBLOCK | slot stays AB-owned and alive (even through GC), but every JS->C++ call tested faults |
| V689 | 8 call canaries + GC write scan | deployed 20:06, **not run yet** | pending |

### Cross-type reclaim is mostly a dead end (V680-V682)
Only two reclaimer families have worked on this heap:
1. **Same-type** CanvasRenderingContext2D (V573, V684 whoami, v592-ctl reclaimctx).
2. **ArrayBuffer(768)** (V687) - which zeroes the object, so no call survives.

Everything else sprayed at the 768B slot lost to the tagged real contexts.

### Unresolved items (do not mark as dead)
- **V682 `text a=704`**: OCFG/OBUILT/OPRE landed, no OSTEP, then ODONE after the
  auto-reload. Could be a real slot takeover by a string buffer (the most interesting
  outcome) or an unrelated fault. Needs one isolated re-run before it is written off.
- **V689**: not run. `js`, `lw0`, `restore` decide whether the call machinery itself is
  the wall; `scan` looks for any byte WebKit wrote into our buffers (a leak with no call).
- **v592-ctl `reclaimread`** and **v592 `stage=5`**: deployed, not run.

### Rule that now has two independent confirmations
**Reclaim before you touch.** Any read/write/call on the freed-but-unreclaimed context
faults (V683, V684, V685, and our own stage-2 bisection). After a same-type reclaim the
same operations work.
