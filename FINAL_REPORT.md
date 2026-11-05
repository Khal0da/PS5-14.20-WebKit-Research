# PS5 14.20 WebKit Exploitation Research - Final Report

## Executive Summary

This report documents the complete state of the PS5 14.20 WebKit exploitation research. All identified attack pathways have been investigated. **No viable info-leak or ASLR defeat primitive has been discovered.**

## Key Findings

### Confirmed Working Primitives

| Primitive | Status | Notes |
|-----------|--------|-------|
| Canvas 2D UAF Trigger | âœ… CONFIRMED | bitmaprenderer outer + 2d inner via property getter |
| Same-Type Reclaim | âœ… CONFIRMED | 500x Canvas2D spray reclaims 768B slot |
| Alias Read/Write | âœ… CONFIRMED | All 12 Canvas2D APIs work through stale wrapper |
| Crash Oracle | âœ… CONFIRMED | Forged m_stateStack + lineWidth read |

### Blocked Attack Paths

| Path | Status | Blocking Factor |
|------|--------|-----------------|
| STG5 Butterfly OOB Read | âŒ BLOCKED | OOM/GC crash at spray=100-200 |
| V689 Canaries | âŒ BLOCKED | vtable gate on AB-owned slot |
| V682 text a=704 reclaim | âŒ BLOCKED | Real contexts always win slot |
| V700 HTMLParser CE bypass | âŒ BLOCKED | Parser validation handles mutations |
| V182 font loca OOB | âŒ BLOCKED | FreeType validates offsets / returns notdef |
| V674 APNG overread | âŒ BLOCKED | Image fails to decode (`APNGERR load-fail`) |
| WebAudio API | âŒ UNAVAILABLE | AudioContext/OfflineAudioContext undefined |
| CSSFontFace UAF | âŒ BLOCKED | Classic thenable trigger does not fire |
| MSE basic edge cases | âŒ BLOCKED | All handled safely |
| Streams API TransformStream | âŒ BLOCKED | Hangs on writer.write() |
| V650a Crash Oracle | âŒ BLOCKED | Page hangs on forged read |

### Browser Capability Snapshot (V900)

**Available (21):** MediaSource, BroadcastChannel, CacheStorage, localStorage,
Web Animations, SVG, Shadow DOM, WebSocket, Workers, ImageBitmap, Streams API.

**Unavailable (14):** WebAudio, WebGL, WebRTC, ServiceWorker, IndexedDB,
Gamepad, Notification, RAB, SAB, WebAssembly.

## Attack Chain Status

| Stage | Status |
|-------|--------|
| Bug identification | âœ… DONE |
| UAF trigger | âœ… DONE |
| Same-type reclaim | âœ… DONE |
| Alias R/W | âœ… DONE |
| Info leak / ASLR defeat | âŒ BLOCKED |
| Arbitrary R/W | âŒ BLOCKED |
| Code execution | âŒ BLOCKED |

## Technical Details

### Why APNG Claim is False

The probe `v592-ctl.html?op=apng` attempts to decode a malformed APNG:
- Claims 3 frames
- Provides only 2 frames
- Intended to read beyond fdAT boundary

**On PS5 14.20:** The image fails to decode with `APNGERR load-fail`. No pixel
data is returned. No heap pointers are leaked.

### Why TransformStream Hangs

`new TransformStream()` succeeds. `getWriter()` and `getReader()` succeed.
The first `writer.write()` call hangs indefinitely. This suggests WebKit's
TransformStream implementation has a deadlock or blocking issue on this platform.

### V650a Read Failure

The crash oracle probe:
1. Successfully triggers UAF
2. Sprays marker-filled ArrayBuffers
3. **Attempts to read `lineWidth` â€” the page hangs**

The stale context wrapper cannot perform a read operation without crashing
or hanging the renderer.

## Recommendations

1. **Do not pursue further exploitation of PS5 14.20 WebKit** without:
   - Additional info-leak surface discovery
   - New WebKit CVE exploitation (JIT-disabled platform)
   - Firmware-specific vulnerabilities

2. **Focus research efforts on**:
   - Other attack surfaces (e.g., GPU drivers, kernel bugs)
   - Newer firmware versions with potential bug fixes/changes
   - Cross-model vulnerability research

## Conclusion

The PS5 14.20 browser lacks a viable path from the confirmed Canvas UAF to a
fully weaponized exploit chain. Every attempt to extract heap addresses has
failed. The documented claim that "APNG overread leaks 1651 heap pointers"
is not reproducible on retail hardware.

---

*This report documents the complete exploration of all known and suspected
attack vectors. The research is concluded.*