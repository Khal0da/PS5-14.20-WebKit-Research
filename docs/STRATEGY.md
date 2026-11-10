# Strategy

## Current Phase: Exploitation (Phase 4)

CVE-2026-43720 (Canvas getContext() reentrant UAF) is confirmed exploitable. Same-type reclaim gives full R/W of Canvas2D state fields. The next unlock is an info leak primitive to defeat ASLR -- active routes: V914 allocator-math selection and V923 roundRect pointer-write.

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

49 total attack vectors investigated: 5 bugs found (1 exploitable, 4 contained); the remaining 44 answered with on-device evidence and logged in [DEAD_ENDS.md](DEAD_ENDS.md) and [CONFIRMED_VULNS.md](CONFIRMED_VULNS.md). Every answered vector narrows the field for the ones still running.

### Phase 4: Exploitation -- IN PROGRESS

**Done:**
- UAF trigger (bitmaprenderer outer + defineProperty getter + 2d inner)
- Same-type reclaim (500x Canvas2D spray reclaims freed 768B slot)
- Bidirectional R/W via alias (lineWidth, miterLimit, globalAlpha, fillStyle, getLineDash, etc.)
- Crash oracle **mechanism** (V906: offset-agnostic `[ptr,1,1]` pattern proves slot bytes are dereferenced as a pointer; 14/15 at `S4-tagged`, `dbl` crashes; 0 HIT because no mapped address found)
- DAZ confirmed ON (all float64 channels flush denormals to 0)

**APNG overread (V674) — answered (Nov 5):** The `op=apng` probe in
`canvas-uaf/v592-ctl.html` does not decode on PS5 14.20 (`APNGERR load-fail`).
No pixel data is returned and no heap pointers are leaked. The claim that
"APNG overread leaks 1651 heap pointers" is not reproducible on retail hardware.
The leak effort continues on the roundRect pointer-write path (V923).

**Current focus: Info leak (ASLR defeat)**

All Canvas2D APIs return typed JS values -- no raw heap pointer exposed yet. 10+ dedicated approaches answered on device; each answer constrains the design space and feeds the next attempt. On-device status (Nov 3):
- Same-type reclaim is stable (`lw=4.5678` reproduced).
- Reading a freed, not-yet-reclaimed context crashes; the pre-read is the fault.
- Direct AB(768) reclaim crashes: the AB backing store zeroes `m_stateStack` at +112,
  so the first field read dereferences null/garbage. Fixing it needs pointer forging.

Answered candidates (each result feeds the next design):
1. OOB state stack read via save-count mismatch — **answered by V908**: `oob-v0`/`oob-v32` both MISS (beacons 10068-10182); save count does not survive same-type reclaim. Same-object model holds — the model V906 and V914 build on.
2. A reclaim type that preserves `m_stateStack` (not a zeroed ArrayBuffer) — **answered by V907+V908**: cross-type reclaim to 768B is real but never yields a readable value (0 SUSPECT in 12+57 isolated cases, beacons 10038-10062 and 10068-10182). Leave-header also unreadable. New flaky 768 hits (`urlsp96`, `imagedata-16x12`) still 0 SUSPECT — the operative path stays same-type reclaim (Canvas2D / AB).
3. Any byte WebKit writes into an attacker-owned buffer with no JS->C++ call (V689 `scan`): scan itself OBLOCKs on the AB-owned slot; only pure-JSC `js` intermittently survives there (DEAD_ENDS "Nov 4 additions"). The idea graduates into **V923**: `roundRect` radii overload reaches `ensureCairoPath()` and writes a fresh `cairo_t*` at context+48 — a WebKit-side pointer write that bypasses the zeroed vptr entirely.

**Answered on device (Nov 3) — working paths derived from each result:**
- Cross-type object/vector/butterfly reclaim of the 768B slot: reclaim is real (4/7 V680 hits confirmed at read in V907 isolation: style/48, strfake8, abfake, abzero); readable fake 0 SUSPECT (beacons 10038-10062). text/704 + strfake16 crash during spray, not at read. matchmedia MISS on isolated re-run (sweep artifact). No cross-type +112 is a valid Vector — same-type Canvas2D reclaim is the working alias.
- Reading the inline state stack after free crashes (V683) — read through the live alias instead.
- Reading non-Vector members (`canvas`, `getContextAttributes`) before reclaim crashes (V684, V685) — Vector members (+112 region) are the readable surface.
- JS->C++ calls on an AB-owned zeroed slot dispatch through the zeroed vptr and crash; only `idle` and `gc` survive (V686, V688) — V923 `roundRect` targets the one analyzed gate-free write path.
- `op=apng` does not decode on PS5 14.20 — superseded by the roundRect pointer-write leak.

**Still open, in priority order:**
0. **V923 roundRect pointer-write leak — pending run.** Gate-free `roundRect(10,10,100,100,5)` reaches
   `ensureCairoPath()`, which writes a fresh `cairo_t*` at context+48 of the AB-owned slot — a WebKit-side
   pointer write that never touches the zeroed vptr. Scan -> extract P -> 12-qword dump through the
   `lineWidth` forge (`m_buffer = T-48, m_size = 1`). A live run answers the vptr-gate analysis and, on
   success, delivers the mapped anchor by construction.
1. **V914 allocator-math selection — running.** The 768B class serves ~705-768B allocations, so a RefPtr
   vector at capacity 89-96 places a live pointer exactly at +112 (rules ~92, toklist ~94) — first
   candidates with a mapped-pointer-by-construction at the read offset. Network bridge established (see
   NETWORK_ACCESS.md): console real IP 192.168.0.102 reachable via Tailscale; port 9295 (Remote Play RTSP)
   open; loader ports come online the moment ARW exists.
2. Mapped-address derivation: **in-browser surface fully surveyed (Nov 6).** V906 oracle works; every
   address tried so far is unmapped (V650 30 + V906 12). The survey that drove the pivot: cross-type
   reclaim readable fake (V907+V908, 0 SUSPECT), OOB save-count (V908), JSC pointer harvest (V910),
   WebCore size fine-tune (V911, 4 new read hits still 0 SUSPECT), JS-exposed number recon (V912, no
   anchor), tee() with fresh nonces (V913, self-data only) — together they selected allocator math (V914)
   and the roundRect write (V923).
3. Geometry tuning of the two NEW 768 hits — **DONE by V909 (beacons 10183-10217, 7 MISS + 10 CRASH + 0 SUSPECT)**: `urlsp` peak only at 96; `imagedata` 768 family 5x `S3-tagged` read + 1x `S2` spray (`96x2`), controls MISS. Readable fake answered — the same-type path continues.
4. `matchmedia` flaky race — **DONE by V909 (6/7 total)**: V907 1 MISS, V908 3/3 CRASH, V909 r4-r6 3/3 CRASH. Highly reliable, not a sweep artifact.
5. V689 `scan` / `js` / `lw0` / `restore` / v592 `stage=5` / V682 `text a=704` — **answered (Nov 4/5)**: scan + all canaries OBLOCK on AB-owned slot; stage=5 OOM before POST; text never reclaims the slot. Data in DEAD_ENDS "Nov 4/5 additions"; the write-class idea continues in V923.
6. 13.60 chain on 14.20 (V917) — **answered (Nov 6, beacons 10585-10987).** The official PS5 WebKit chain
   (history.replaceState structured-clone + Symbol OOB, 13.60/src) does not pass its FIRST stage on 14.20:
   `PRIM-START apis=ok` then **200+ consecutive attempts all `setup failed: Error: Scope not leaked`**
   (E-Attempt 0..200). The relapse scope-leak precondition does not reproduce on 14.20 → no ARW from
   this chain as-is. Companion V919 forge sweep: **every case CRASH, `base-unmapped`** (sweep-001..020 + forge-ctl,
   imagedata/abzero S3-tagged) — consistent with no mapped anchor. Re-entry condition: the anchor that
   items 0-1 are hunting.

**Phase 4 status (Nov 8, post-V917/V919 + B-session V938B-V956B/v597):** the canvas UAF chain currently
delivers, browser-side, reliable DoS + state-field R/W via alias (V573/V630) + mapped/unmapped oracle (V906).
The single missing piece is one mapped anchor; no heap pointer has been read yet. Answered this window:
13.60 chain (V917 Scope-not-leaked on 14.20), APNG 321753-class disclosure (live but uncontrolled, no
pointer: V953B), WebCodecs/325886 (unavailable: V955B), BMP RLE
321680/321754 (V952B/V954B negative), filter uninit (V956B/v597 negative). Active unblock routes, in parallel:
(a) loader/klog on the real PS5 IP for native crash reports — resolves "what is mapped" empirically, and
(b) leak-class WebKit triggers (JS-readable, no WebGPU/WebGL/WASM/SAB/WebCodecs) — V923 roundRect write and
V914 allocator-math selection are the current designs. One landed anchor makes the rest of the chain
reachable: lineDash forge -> arbitrary R/W -> Phase 5.

**Designed and queued:**
- Forge lineDash Vector in AB for arbitrary R/W
- vtable hijack or startOfStructureHeap overwrite (Config unfrozen)
- ROP chain to mprotect(74) for RWX

### Phase 5: Kernel pivot — QUEUED (fires on Phase 4 code execution)

Unlocks the moment Phase 4 delivers browser code execution. Kernel candidates already selected:
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
