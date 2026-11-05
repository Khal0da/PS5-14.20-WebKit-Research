# Strategy

## Current Phase: Exploitation (Phase 4)

CVE-2026-43720 (Canvas getContext() reentrant UAF) is confirmed exploitable. Same-type reclaim gives full R/W of Canvas2D state fields. The current blocker is an info leak primitive to defeat ASLR.

## Phases

### Phase 1: Recon probes on device -- DONE

Fingerprinted the PS5 WebView. Determined API availability, format support, parser paths reachable from JavaScript.

Results:
- p163 / V399: Full API availability matrix
- p161a: FontFace API recon (15 tests)
- p161b: Image decoder recon (19 tests)
- V520: MSE SourceBuffer re-entrancy -- all safe
- V521: Structure spray, butterfly realloc, megamorphic IC -- no anomalies

### Phase 2: Source audit -- DONE

15+ WebKit subsystems audited against WK-1400 source. Zero exploitable entry bugs from source audit alone -- but confirmed IsoHeap OFF and Gigacage disabled, which reopened CVE-2026-43720.

Subsystems audited: MetadataTable, MSE/SourceBuffer, ReadableStream/tee(), Canvas2D, CSSFontFace, structuredClone, RAB, Yarr regex, NodeIterator, XMLParser/CustomElements, sort()/TypedArray, DirectArguments, ClonedArguments, font parsing, SVG filters.

See [WK1400_SOURCE_AUDIT.md](WK1400_SOURCE_AUDIT.md) for details.

### Phase 3: Targeted probes -- DONE

CVE-2026-43720 confirmed on device through a series of probes:
- V573: Same-type reclaim -- CONFIRMED (alias at idx=9)
- V562: All 12 Canvas2D APIs through alias -- clean complete run
- V630: Full 12-API alias diagnostic -- ALL PASS (alias at idx=11)
- V589: BMR trigger validation -- `uaf-ok: inner=OK`
- V650: UAF trigger confirmed LIVE on PS5 14.20 (bmr=OK, getter=true, inner=OK)
- V592: Butterfly harvest v2 -- saves=32, cap=37, buf=14800, lwOff=12848 (4x consistent)

49 total attack vectors investigated, 44 confirmed dead. 5 bugs found (1 exploitable, 4 contained/blocked). See [DEAD_ENDS.md](DEAD_ENDS.md) and [CONFIRMED_VULNS.md](CONFIRMED_VULNS.md).

### Phase 4: Exploitation -- IN PROGRESS

**Done:**
- UAF trigger (bitmaprenderer outer + defineProperty getter + 2d inner)
- Same-type reclaim (500x Canvas2D spray reclaims freed 768B slot)
- Bidirectional R/W via alias (lineWidth, miterLimit, globalAlpha, fillStyle, getLineDash, etc.)
- Crash oracle (forge m_stateStack to target address, lineWidth reads 8 bytes)
- Heap topology mapping (V650-V655 binary subdivision scanner)
- DAZ confirmed ON (all float64 channels flush denormals to 0)

**APNG overread (V674) â€” DEAD (Nov 5):** The `op=apng` probe in
`canvas-uaf/v592-ctl.html` fails to decode on PS5 14.20 (`APNGERR load-fail`).
No pixel data is returned and no heap pointers are leaked. The claim that
"APNG overread leaks 1651 heap pointers" is not reproducible on retail hardware.

**Current blocker: Info leak (ASLR defeat)**

All Canvas2D APIs return typed JS values -- no raw heap pointer exposed. 10+ dedicated info leak approaches exhausted. On-device status (Nov 3):
- Same-type reclaim is stable (`lw=4.5678` reproduced).
- Reading a freed, not-yet-reclaimed context crashes; the pre-read is the fault.
- Direct AB(768) reclaim crashes: the AB backing store zeroes `m_stateStack` at +112,
  so the first field read dereferences null/garbage. Fixing it needs pointer forging.

Current candidates:
1. OOB state stack read via save-count mismatch (needs a read that survives the pre-read)
2. A reclaim type that preserves `m_stateStack` (not a zeroed ArrayBuffer)
3. Any byte WebKit writes into an attacker-owned buffer with no JS->C++ call (V689 `scan`)

**Do not repeat (answered on device, Nov 3):**
- Cross-type object/vector/butterfly reclaim of the 768B slot: all miss (V680, V681, V682).
- Reading the inline state stack after free: crashes (V683).
- Reading non-Vector members (`canvas`, `getContextAttributes`) before reclaim: crashes (V684, V685).
- Any JS->C++ call on an AB-owned zeroed slot: crashes; only `idle` and `gc` survive (V686, V688).
- `op=apng`: DEAD, image fails to decode on PS5 14.20.

**Still open, in priority order:**
1. V689 `scan` - a pointer written by GC/WebKit into our buffer would be a call-free leak.
2. V689 `js` / `lw0` / `restore` - decides whether the call machinery or the object contents
   is the wall on an AB-owned slot.
3. v592 `stage=5` - butterfly reclaim of the state buffer BEFORE the first read.
4. v592-ctl `reclaimread` - confirms whether the same-type alias is complete (5 fields).
5. V682 `text a=704` isolated re-run - one unexplained crash in the reclaim walk.

**Designed but not yet reached:**
- Forge lineDash Vector in AB for arbitrary R/W
- vtable hijack or startOfStructureHeap overwrite (Config unfrozen)
- ROP chain to mprotect(74) for RWX

### Phase 5: Kernel pivot -- BLOCKED

Requires browser code execution from Phase 4. Top kernel candidates:
- CVE-2026-7270 (execve memmove OOB) -- full exploit published
- CVE-2026-45251 (poll/select UAF) -- full exploit published
- thr_create(430) confirmed working (up to 8 threads)

## Known Constraints

| Constraint | Impact |
|------------|--------|
| No JIT | No RWX pages, need ROP/JOP chains |
| No WASM | Cannot use WASM memory for layout control |
| No SharedArrayBuffer | Cannot race between threads for heap bugs |
| No WebGL | Cannot use GPU buffer tricks, readPixels leak unreachable |
| Gigacage disabled | AB shares heap with JSC internals (HELPS exploitation) |
| IsoHeap OFF | All WebCore objects in same FastMalloc (HELPS exploitation) |
| Config unfrozen | startOfStructureHeap writable post-exploitation (HELPS) |
| FreeBSD kernel | Different syscall table, different exploit surface |
| 16KB pages | Page alignment differs from x86 4KB |
| LLInt only | All bytecode through interpreter loop |
| ~1200MB ceiling | WebContent process OOM-killed beyond this |
| DAZ ON | Float64 channels flush denormals; must use BigUint64Array for raw pointers |
