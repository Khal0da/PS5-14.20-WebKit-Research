# PS5 14.20 WebKit Research - Field Notes

Public research journal for a WebKit attack-surface study on PlayStation 5 firmware 14.20. This repository contains diagnostics, probes and documentation only. It does not contain a working exploit chain, shellcode, kernel payloads, or anything that grants code execution.

What this is
A structured, reproducible record of what does and does not work in the PS5 14.20 browser engine, so that other researchers do not repeat the same dead ends.

Every claim below was checked on retail hardware with a beacon-based probe. Beacons are sent before and after each step, so if the renderer dies, the last unmatched START identifies the exact crashing case.

Confirmed on 14.20
Item	Status	Notes
Canvas 2D / bitmaprenderer re-entrancy	Confirmed	Inner 2d context is created from a property getter during the outer bitmaprenderer call
Same-type reclaim	Confirmed	Fresh 2d contexts land in the freed slot
Alias read through the stale wrapper	Confirmed (partial)	4 of 5 state fields match the reclaim tag
SVG SMIL element lifecycle	Stable	240-iteration lifecycle fuzz, no crash
SVG filter primitives	Stable	200-iteration fuzz, no crash
ImageBitmap lifecycle	Stable	create / close / transfer ordering fuzz
MediaSource / SourceBuffer basics	Stable	Invalid input rejected cleanly
ReadableStream / WritableStream / tee	Stable	Basic flows work
Bottom line: there is a real UAF trigger, but no info leak, no arbitrary read/write, and no code execution.

Not available on 14.20
AudioContext, OfflineAudioContext, WebGL / WebGL2, RTCPeerConnection, ServiceWorker, IndexedDB, Gamepad, Notification / Permissions, SharedArrayBuffer, Resizable ArrayBuffer, WebAssembly.

Documented dead ends
See docs/DEAD_ENDS.md. Highlights:

APNG overread info leak - claimed elsewhere to leak 1,651 pointers. On 14.20 the malformed image fails to decode (load-fail). No pixel data, no pointers. Not reproducible.
WebAudio - API not exposed.
TransformStream - writer.write() hangs the renderer.
Font loca OOB - FreeType validates offsets.
Custom element double-parent - parser validation holds.
CSSFontFaceSet reference wrapper - classic thenable trigger does not fire.
V650 forged m_stateStack read - page hangs on the read.
Repository layout
README.md                     this file
CHANGELOG.md                  chronological log
FINAL_REPORT.md               consolidated report
docs/
  FINDINGS.md                 on-device results
  DEAD_ENDS.md                every dead end, with evidence
  STRATEGY.md                 research strategy
  RESEARCH_MAP.md             surface map
  PROGRESS_AUDIT.md           session audit
  PS5_1420_BROWSER_CAPABILITIES.md
  PUBLICATION.md              what is included / excluded and why
  bugs/canvas-getcontext-uaf.md
probes/
  index.html                  probe menu
  v2000-all-in-one.html       runs every safe test in one page
  v1000-smil-fuzz.html        SVG SMIL lifecycle fuzzer
  v1001-imagebitmap-fuzz.html ImageBitmap lifecycle fuzzer
  feature-detect.html         capability snapshot
Running the probes
The probes are static HTML/JS. Serve the probes/ directory over HTTP and open probes/index.html on the target browser.

They post progress to /beacon/<TAG>?... on the same origin. If you serve them without a beacon endpoint, the requests 404 and the probes still run; read the on-page table for results.

v2000-all-in-one.html runs 23 tests sequentially and prints a result row for each. If the page crashes, the last START without an OK/ERR is the culprit.

Excluded from the battery on purpose: TransformStream.writer.write() and the forged m_stateStack read. Both hang the renderer, and a JavaScript timeout cannot recover from that.

Method notes
No forged pointers, no ROP, no arbitrary read/write in this repository.
Probes are read-only with respect to system state; they exercise DOM and graphics APIs and observe behaviour.
Deterministic PRNG seeds are recorded so any crashing iteration can be reproduced.
Results are captured from beacons, not from memory of a session.
Status
Exploit chain status: blocked at info leak / ASLR defeat.

The trigger is real. The missing piece is a memory disclosure primitive. Until one is found, nothing here is a jailbreak.

License
MIT. See LICENSE.