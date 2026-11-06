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
- Crash oracle **mechanism** (V906: offset-agnostic `[ptr,1,1]` pattern proves slot bytes are dereferenced as a pointer; 14/15 at `S4-tagged`, `dbl` crashes; 0 HIT because no mapped address found)
- DAZ confirmed ON (all float64 channels flush denormals to 0)

**APNG overread (V674) — DEAD (Nov 5):** The `op=apng` probe in
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
1. OOB state stack read via save-count mismatch — **DEAD by V908**: `oob-v0`/`oob-v32` both MISS (beacons 10068-10182); save count does not survive same-type reclaim. Same-object model holds.
2. A reclaim type that preserves `m_stateStack` (not a zeroed ArrayBuffer) -- **DEAD by V907+V908**: cross-type reclaim to 768B is real but never yields a readable value (0 SUSPECT in 12+57 isolated cases, beacons 10038-10062 and 10068-10182). Leave-header also unreadable. New flaky 768 hits (`urlsp96`, `imagedata-16x12`) still 0 SUSPECT.
3. Any byte WebKit writes into an attacker-owned buffer with no JS->C++ call (V689 `scan`) -- **DEAD**: V689 `scan` killed the renderer (OBLOCK); only pure-JSC `js` intermittently survives on an AB-owned slot (DEAD_ENDS "Nov 4 additions").

**Do not repeat (answered on device, Nov 3):**
- Cross-type object/vector/butterfly reclaim of the 768B slot: **reclaim is real (4/7 V680 hits confirmed at read in V907 isolation: style/48, strfake8, abfake, abzero), readable fake is DEAD (0 SUSPECT, beacons 10038-10062)**. text/704 + strfake16 crash during spray, not at read. matchmedia MISS on isolated re-run (sweep artifact). No cross-type +112 is a valid Vector.
- Reading the inline state stack after free: crashes (V683).
- Reading non-Vector members (`canvas`, `getContextAttributes`) before reclaim: crashes (V684, V685).
- Any JS->C++ call on an AB-owned zeroed slot: crashes; only `idle` and `gc` survive (V686, V688).
- `op=apng`: DEAD, image fails to decode on PS5 14.20.

**Still open, in priority order:**
1. Mapped-address derivation: **IN-BROWSER SURFACE EXHAUSTED (Nov 6).** V906 oracle works but every address tried is unmapped (V650 30 + V906 12). Closed since: cross-type reclaim readable fake (V907+V908, 0 SUSPECT), OOB save-count (V908), JSC pointer harvest (V910), WebCore size fine-tune (V911, 4 new read hits still 0 SUSPECT), JS-exposed number recon (V912, no anchor), tee() with fresh nonces (V913, self-data only). Remaining paths are outside the tunnel-only setup: native crash reports / klog via loader on the PS5's real IP (port 9027), or a second bug that is itself a leak.
2. Geometry tuning of the two NEW 768 hits — **DONE by V909 (beacons 10183-10217, 7 MISS + 10 CRASH + 0 SUSPECT)**: `urlsp` peak only at 96; `imagedata` 768 family 5x `S3-tagged` read + 1x `S2` spray (`96x2`), controls MISS. Readable fake still dead.
3. `matchmedia` flaky race — **DONE by V909 (6/7 total)**: V907 1 MISS, V908 3/3 CRASH, V909 r4-r6 3/3 CRASH. Highly reliable, not a sweep artifact.
4. V689 `scan` / `js` / `lw0` / `restore` / v592 `stage=5` / V682 `text a=704` — **CLOSED**: scan + all canaries OBLOCK on AB-owned slot; stage=5 OOM before POST; text never reclaims the slot. See DEAD_ENDS "Nov 4/5 additions".

**Phase 4 honest status (Nov 6, post-V913):** the canvas UAF chain is capped, browser-side, at
reliable DoS (urlsp96 / imagedata-768 / matchmedia crash-at-read) + state-field R/W via alias
(V573/V630) + a mapped/unmapped oracle (V906). No heap pointer has ever been read. The next
realistic unblocks are (a) loader/klog on the real PS5 IP for native crash reports — resolves
"what is mapped" empirically, or (b) hunting a second, leak-class WebKit bug. Everything else
in the current chain is blocked on the same missing anchor.

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
