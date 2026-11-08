# PS5 14.20 WebKit Research - Field Notes

Public research journal for a WebKit attack-surface study on PlayStation 5 firmware 14.20 (`PlayStation 5/14.20`, `AppleWebKit/605.1.15`). This repository contains diagnostics, probes and documentation only. It does **not** contain a working exploit chain, shellcode, kernel payloads, or anything that grants code execution.

**Status (checkpoint):** exploit chain **blocked at Stage 2 — ASLR / pointer-anchor info leak**. UAF/alias and crash signals exist; **no reliable pointer/ASLR anchor, no arbitrary R/W by address, no code execution, no kernel**.

## What this is
A structured, reproducible record of what does and does not work in the PS5 14.20 browser engine, so other researchers do not repeat dead ends and can help unblock Stage 2.

Claims are checked on retail hardware with **step-beaconed probes** (`/beacon/<TAG>`). Beacons are sent before/after steps, so if the renderer dies the last unmatched step identifies the crashing case.

## Confirmed / observed on 14.20
| Item | Status | Notes |
|---|---|---|
| Canvas 2D / bitmaprenderer re-entrancy UAF | Confirmed | Inner 2d context via property getter during outer bitmaprenderer call; same-type reclaim + alias (typed state R/W). **Pointer not readable via Canvas APIs** (no raw leak). |
| APNG Bug 321753-class OOB disclosure | **JS-readable disclosure (live/variable), not controllable** | OOB memory fragments readable (e.g. `aeae…` poison + variable slots such as `7f3bbd80`/`87870020`/`…ee3f`). Controllability rechecks (groom/spray incl. typed `Uint32Array/Float64Array` markers, **V971B `markerHits=0`, no `mark=1`**) **negative** ⇒ **no proven pointer/ASLR anchor**. Not equivalent to the “1651 pointers” claim. |
| RAB (Resizable ArrayBuffer) | **Available** | `ArrayBuffer(maxByteLength)`/`resize` works (V970B). CVE-2025-43541/301257-inspired bounded/heavier RAB+DataView+resize canaries (V970B/V970B2) reached `DONE` with **no crash/signal** on tested patterns (not proof of absence; 2.42.x backport unknown). |
| Streams tee under-yield (V702/V703, older runs) | Crash/DoS signal | Under-yield ⇒ WebProcess crash at/inside tee; over-yield survives (discriminator suggests not an ASSERT abort). **No demonstrated leak/alias verdict, no primitive.** V704 v2 groom-repeat stable/clean. |
| Alias-state/save-restore oracles (V957B–V966B) | Stable/negative | No corruption/inconsistency/leak via tested save/restore/state paths. |
| Surface/edge probes (V967B–V969B) | Negative | `performance.now` ~1ms coarse, `Error.stack` no `0x`; `createImageBitmap`/`structuredClone`/Intl edges guarded/no crash; BYOB path unusable as tested. |

## Not available / limited on 14.20 (as tested)
`WebAssembly`, `SharedArrayBuffer` (`crossOriginIsolated=false`), `WebGL`/`WebGL2`, `OffscreenCanvas`, WebCodecs, `AudioContext`/`OfflineAudioContext`/`AudioWorklet`, WebGPU. **Available:** `Atomics`, `ImageBitmap`/`createImageBitmap`, `ReadableStream` (BYOB unusable as tested), `structuredClone`, `Intl.*` (Segmenter/Collator/DisplayNames), **Resizable ArrayBuffer**.

## Open problem — Stage 2: ASLR / pointer anchor (help wanted)
**Goal:** a reliable, verifiable pointer/info leak (ASLR anchor) on 14.20 WebKit, convertible toward arb R/W.  
**What we have:** typed-state alias R/W (pointer unreadable) + live but **uncontrollable** APNG OOB disclosure + DoS/crash signals. **What we lack:** a controllable/readable pointer or address anchor.

**Highest-value help:**
1. **14.20 dump + JSC/WebCore diff/backport analysis** (what’s patched vs 2.42.x/2.50.x, offsets/IsoHeap/structures) to target a real primitive.
2. A **verified 14.20-compatible trigger/PoC/CVE/commit details** for an **available** surface (Canvas/RAB/TypedArray, `ImageBitmap`/`createImageBitmap`, `structuredClone`, Intl, JSC/DFG) — **no** WASM/SAB/WebGL/WebCodecs/OffscreenCanvas. Share code/details → we run **(a) repro/signal (step-beaconed)** then **(b) attempt primitive conversion** if a signal appears.
3. Independent verification/re-analysis of the APNG 321753 disclosure (can any variable slot be made to carry a stable/controllable value or pointer on 14.20?) — our spray tests (incl. V971B) were negative.

**Key artifacts:** `docs/reports/v925-v928B-session-findings.md` (B-session V925–V971B log summary), `docs/STRATEGY.md`, `docs/RESEARCH_MAP.md`, `docs/DEAD_ENDS.md`, `docs/NETWORK_ACCESS.md`, probes under `probes/canvas-uaf/` and `probes/streams/`.

## Documented dead ends
See `docs/DEAD_ENDS.md` (treat as evolving; cross-check with latest reports). Highlights relevant to 14.20: APNG 321753-class = disclosure seen but **uncontrollable/no pointer** (V971B etc.); RAB present but 43541 canary patterns **no signal** (tested set) — **not proof of absence**; many surfaces unavailable (WASM/SAB/WebGL/WebCodecs/Audio). Prior “V674 APNG load-fail / 1651 pointers” claims are not reproduced as stated here — distinguish probe/firmware/path specifics.
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