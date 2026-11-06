# CVE-2026-43720 -- Canvas getContext() Reentrant UAF

**Status:** CONFIRMED on PS5 14.10. Same-type reclaim + bidirectional R/W WORKING.

**Fix:** Commit 2693828e8d73 (2026-06-29). Not present in WK-1400.

## The Bug

`HTMLCanvasElement::getContext()` reads dictionary options via JS property getters BEFORE
setting the new context. A re-entrant getter creates a 2d context; the outer call then
replaces it with bitmaprenderer, freeing the 2d context while its JS wrapper survives.

Source: `HTMLCanvasElement.cpp`, lines 226 (m_context check) and 268 (IDL dictionary
conversion with JS getter callbacks).

### Trigger (bitmaprenderer outer + 2d inner)

```javascript
var innerCtx;
var canvas = document.createElement('canvas');
canvas.width = 1; canvas.height = 1;
var opts = {};
Object.defineProperty(opts, 'alpha', {
  get: function() {
    innerCtx = canvas.getContext('2d');
    return true;
  }
});
canvas.getContext('bitmaprenderer', opts);
// innerCtx is now a dangling reference to freed 768-byte memory
```

**Critical rules:**
- Outer MUST be `bitmaprenderer` (80B, different size class from 2d's 768B)
- Inner MUST be `2d`
- MUST use `Object.defineProperty`, NOT Proxy
- NEVER trigger UAF more than once per page load (double-deref = heap corruption)

### Why bitmaprenderer?

The bitmaprenderer context object is ~80 bytes vs Canvas2D's ~768 bytes. Different size
classes prevent the outer context from accidentally reclaiming the inner context's freed
slot during the same `getContext()` call.

## IsoHeap is OFF on PS5

`WTF_MAKE_ISO_ALLOCATED` compiles to standard FastMalloc on FreeBSD/PlayStation.
`BPLATFORM(PLAYSTATION)` at BPlatform.h:341 disables IsoHeap. Gigacage also disabled.
All WebCore objects live in the same heap.

Confirmed by:
- BPlatform.h:341 source analysis
- Synacktiv PS5 exploitation writeup
- CSSFontFace exploitation research (AB shares heap)

## Same-Type Reclaim (V573)

After triggering the UAF, spray 500 new Canvas2D contexts. One reclaims the freed
768-byte slot. `innerCtx` and `sprayCtxs[N].ctx` now alias the same live C++ object.

Device evidence:
- V573: Alias at index 9/11, bidirectional R/W confirmed
- V562: ALL 12 Canvas2D APIs work through alias (clean complete run)
- V630: Comprehensive re-confirmation, alias at index 11

## Confirmed Primitives

| API | Primitive | Type |
|-----|-----------|------|
| lineWidth | Float64 R/W at State+48 | number |
| miterLimit | Float64 R/W at State+64 | number |
| globalAlpha | Float64 R/W at State+0 | number |
| fillStyle | Color R/W at State+16 | string |
| strokeStyle | Color R/W at State+32 | string |
| font | Font string R/W at State+224 | string |
| setLineDash / getLineDash | 500-double array round-trip | Float64Array |
| getTransform | DOMMatrix read at State+112 | object |
| save / restore | 3-level state stack cycle | - |
| createPattern | Pattern from HTMLCanvasElement | object |
| measureText | TextMetrics object read | object |

## Crash Oracle — Mechanism CONFIRMED by V906 (2026-11-06), no mapped address yet

Forging `m_stateStack` (Vector at context offset +112) in an aliased ArrayBuffer:

1. Set `m_buffer` (ptr at AB+112) to target address
2. Set `m_size` (u32 at AB+120) to 2
3. Read `lineWidth` through dangling `innerCtx` -> reads float64 at `target + 48`
4. If target page is mapped: returns 8 bytes of data
5. If target page is unmapped: SIGSEGV, PS5 browser reloads

**V906 full run (beacons 9997-10034, FINAL 2026-11-06 12:08) settles this:**
- `same` (no AB, 8 tagged contexts) = MISS `lw=201` — stale wrapper was aliased by a real context, i.e. the wrapper *does* track the slot.
- All 15 AB cases crashed, 0 HIT, 0 MISS for AB. 14 crashed at `S4-tagged` (during `lineWidth` read, after taggers). `pe_512m` crashed at `S3-spray200` (during spray, before read). `dbl` (all lanes 4.5678) crashed instead of returning 4.5678, proving the slot bytes are dereferenced as a pointer, not read as a direct double.
- The pattern is offset-agnostic: `[ptr,1,1]` repeats every 16 bytes in both phases (`pe`/`po`), so every 8-byte-aligned Vector offset sees the same `[ptr,1,1]`. Because 6 different pointer guesses (`stack1/stack2/4m/64k/512m/4g` ×2 phases) all crashed, the failure is unmapped addresses, not a wrong +112 offset. V650's 30 failures are explained the same way.

**What remains:** no mapped address has ever been found. Blind user-space guesses on a PIE/ASLR process are hopeless without a leak. The oracle is a binary mapped/unmapped test *if* a plausible mapped address is known; it is not a leak by itself.

Also note (V680 re-parse + V907 isolated + V908 full-52, 2026-11-06): cross-type reclaim *does* happen
but never yields a readable value. V680's 7 crashes collapse under isolation (V907,
beacons 10038-10062, 0 SUSPECT): `style/48`, `strfake8`, `abfake`, `abzero` crash at the
read (`S3-tagged`); `text/704` and `strfake16` crash during spray, not at the read
(`S2-candidate`); `matchmedia` is MISS on isolated re-run. Leave-header `strraw8`
also unreadable — +112 in real StringImpl/style/AB bytes is not a valid Vector.
Do not build on cross-type readable fakes.

V908 full-52 (57 cases, beacons 10068-10182, 0 SUSPECT) makes this exhaustive:
45 MISS, 12 CRASH. Sweep missed two flaky 768 hits now isolated at read — `urlsp96`
and `imagedata-16x12` (`imagedata-16x11`/`urlsp32` stay MISS). `matchmedia` is flaky,
not artifact (3/3 CRASH here vs MISS in V907). Save-count OOB (`oob-v0`/`oob-v32`) is
MISS — same-object model holds; the stale wrapper reads the reclaimer's current state.

V909 geometry (17 cases, beacons 10183-10217, 0 SUSPECT): `urlsp` peak only at 96
(2/2); `imagedata` 768 family 5x `S3` read + 1x `S2` spray (`96x2`), controls MISS;
`matchmedia` 3/3 new (6/7 total). 7 MISS + 10 CRASH. Readable fake still dead; backing
size (768) is the determinant, not shape (except extreme).

V910 harvest (14 cases, beacons 10256-10284, 0 SUSPECT): 10 JSC pointer candidates
all MISS (did not reclaim); controls CRASH. JSC butterflies do not share the WebCore 768 slot.

V911 fine-tune (29 cases, beacons 10297-10355, 0 SUSPECT): new read hits `blob-8x768`,
`blob-16x768`, `text-736`, `urlsp-92` (plus controls) — 23 MISS + 6 CRASH. Size hits the 768 class,
but +112 never becomes a valid Vector.

V912 recon (no crash, beacons 10379-10395): no pointer-derived anchor in any JS-exposed number
(memory/eventCounts absent, toString clean, stack URL:line:col, typed offsets exact). V913 tests
tee() self-data equality with fresh nonces (read both branches, exact match = no leak).

## ASLR Defeat (V674) — DEAD

The `v592-ctl.html?op=apng` probe builds a malformed animated PNG (3 frames
claimed, 2 provided) and attempts to read leaked heap pointers via canvas
`getImageData`. On PS5 14.20 the image fails to decode (`APNGERR load-fail`);
no pixel data is returned and no heap pointers are leaked.

The claim that "APNG overread leaks 1651 heap pointers" is not reproducible
on retail PS5 14.20 hardware. ASLR defeat for this chain remains blocked.

## Exploitation Chain

1. **UAF trigger** -> `innerCtx` points to freed 768B slot
2. **Same-type reclaim** -> spray ctx aliases `innerCtx`
3. **Info leak** -> BLOCKED. APNG overread fails to decode on PS5 14.20.
4. **State buffer grow** -> 8x save() = 6400B out-of-line buffer
5. **State buffer free** -> BMR trigger frees inner ctx + state buffer
6. **AB reclaim state buffer** -> 200x ArrayBuffer(6400) sprayed
7. **Forge lineDash Vector** -> set m_buffer=target, m_size=N in AB
8. **Arbitrary read** -> getLineDash through alias reads from m_buffer
9. **Arbitrary write** -> setLineDash writes in-place when capacity >= N
10. **Code exec** -> vtable hijack or startOfStructureHeap overwrite (config unfrozen)
11. **Kernel** -> FreeBSD 11 kernel CVEs (needs browser code exec first)

## Key Offsets (CanvasRenderingContext2D, sizeof ~768B)

| Offset | Field | Notes |
|--------|-------|-------|
| +0 | vtable | NO vtable dispatch in lineWidth path |
| +32 | m_canvas | Ref<HTMLCanvasElement> -- GC reads this |
| +40 | CanvasPath vptr | |
| +48 | m_path | |
| +112 | m_stateStack | Vector<State>: m_buffer(ptr) + m_size(u32) + m_capacity(u32) |
| +128 | inline buffer | First State struct starts here |
| +592 | m_unrealizedSaveCount | |

## State Struct Layout (sizeof = 400B)

| Offset | Field | Type | Read via |
|--------|-------|------|----------|
| +0 | globalAlpha | double | `globalAlpha` |
| +16 | fillStyle | CanvasStyle (16B) | `fillStyle` |
| +32 | strokeStyle | CanvasStyle (16B) | `strokeStyle` |
| +48 | lineWidth | double | `lineWidth` |
| +64 | miterLimit | double | `miterLimit` |
| +88 | shadowBlur | double | `shadowBlur` |
| +112 | transform | AffineTransform (48B) | `getTransform` |
| +168 | lineDash | Vector<double> | `getLineDash` / `setLineDash` |
| +224 | FontProxy vptr | pointer | `font` (string only) |

## DAZ Constraint

PS5 has DAZ (Denormals Are Zero) enabled. All Canvas2D float64 channels flush
denormals to 0.0. Pointer values read as float64 may lose low bits. Must use
BigUint64Array for full 64-bit pointer reads once data is in an ArrayBuffer.

## Device Evidence Summary

| Probe | Purpose | Result |
|-------|---------|--------|
| V460/V461 | Re-entry confirmed | UAF trigger works |
| V527/V527b | AB reclaim discriminator | lineWidth=9999.99 readback |
| V548-V550 | Alias confirmation | Full state R/W via aliased pair |
| V562 | All 12 APIs through alias | Clean complete run |
| V573 | Same-type reclaim diagnostic | CONFIRMED: bidirectional R/W |
| V589 | BMR trigger validation | uaf-ok: inner=OK |
| V630 | Full 12-API alias diagnostic | ALL APIs pass, alias at idx=11 |
| V674 | ASLR bypass via APNG overread | DEAD: image fails to decode (`APNGERR load-fail`) |
| V905 | Canvas dimension / dirty-rect OOB | DEAD: all clamped, no OOB (only 1 GiB DoS) |
| V906 | Slot-steer oracle (offset-agnostic) | Mechanism CONFIRMED, 0 HIT (all guesses unmapped) |
| V907 | V680 hit isolation (12 cases) | Readable fake DEAD: 5 MISS, 7 CRASH, 0 SUSPECT |
| V908 | Full-52 + matchmedia x3 + OOB (57 cases) | Readable fake DEAD exhaustive: 45 MISS, 12 CRASH, 0 SUSPECT; OOB dead |
