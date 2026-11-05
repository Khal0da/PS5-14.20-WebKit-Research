# Changelog

## Nov 5 -- Final Recon Wave + APNG Claim Debunked
- V682 text a=704 confirmed DEAD across all ctx variants (ctxhit=1, sus=0); real
  CanvasRenderingContext2D objects always reclaim the 768B slot.
- V700 HTMLParser Custom Element double-parent / microtask bypass DEAD: all 5
  mutation patterns inside CE constructors executed but parser validation
  handled them correctly.
- V182 font parser loca OOB read DEAD: padding OOB, heap OOB (4-4096),
  heap spray (1000x 4KB), and .notdef OOB all returned px=0/diff=0.
- V800 WebAudio recon: `AudioContext`, `webkitAudioContext`, and
  `OfflineAudioContext` are undefined on PS5 14.20; WebAudio is unavailable.
- V900 browser capability snapshot: 21 APIs available, 14 unavailable
  (documented in docs/PS5_1420_BROWSER_CAPABILITIES.md).
- V910 MSE recon: basic `appendBuffer`, `remove`, `abort`, `changeType`, and
  add/remove cycles all handled safely; no crash.
- V920 CSSFontFaceSet reference_wrapper diagnostic: classic
  `FontFace.prototype.then` trigger did not fire during mutation tests; no
  crash. Reference_wrapper UAF remains unconfirmed as reachable.
- **V674 APNG overread claim DEBUNKED:** `v592-ctl.html?op=apng` fails with
  `APNGERR load-fail` on PS5 14.20. No pixel data and no heap pointers are
  leaked. README claim of 1651 pointers is not reproducible.
- README.md, FINDINGS.md, DEAD_ENDS.md updated to reflect APNG dead end.
- docs/PROGRESS_AUDIT.md updated: info leak / ASLR defeat moved to BLOCKED.

## Nov 4 -- Results Consolidation (Both Sessions)
- V680-V688 on-device results recorded in docs/FINDINGS.md as a results matrix.
- 4 new dead ends in docs/DEAD_ENDS.md: cross-type object reclaim (all miss), inline state
  stack read, non-Vector member read, AB-owned slot JS->C++ calls.
- docs/STRATEGY.md gained a "do not repeat" list plus a prioritized open-items list.
- Rule confirmed twice independently: reclaim before you touch the dangling wrapper.
- probes/index.html now links every probe from both sessions (46 links), including
  V680-V689 and the V592 stage bisection; previous menu backed up as index.html.pre-v680-links.
- Open items explicitly marked unresolved instead of dead: V682 text a=704 crash,
  V689 canaries, v592 stage=5, v592-ctl reclaimread.

## Nov 3 -- V592 Control Harness: Crash Localized + Guard Fixed
- Stage bisection: stage 1 (trigger only) survives; stages 2-4 crash right after CONFIG.
  The pre-read of freed-unreclaimed memory is the fault, not the trigger.
- Same-type reclaim stable: `reclaimctx n=16` -> `lw=0x4012456d5cfaacda` (4.5678), reproduced twice.
- `direct` AB(768) reclaim emits ABSPRAY then crashes, with `fill=marker` and `fill=zero`.
  Cause: AB backing store zeroes `m_stateStack` at +112 -> first field read null-derefs.
- `apng` is not implemented: `V592C-ERR unknown-op:apng`. No v674/APNG probe exists.
  README/docs claims for V674 downgraded to UNVERIFIED.
- Once-guard bug fixed: guard now reads/writes/clears BOTH sessionStorage and localStorage,
  `reset=1` clears the key, `guard=0` bypasses, and `DONE` releases the key on a clean finish.
- New read-only `reclaimread` op: reclaims N tagged contexts and reads all five state fields
  (`lw, ml, ga, ldo, sb`) through the stale wrapper.

## Nov 2 -- On-Device Beacons: V650 UAF Trigger + V592 Butterfly Harvest
- V650: Canvas getContext() UAF trigger confirmed LIVE on PS5 14.20 (bmr=OK, getter=true, inner=OK)
- V592: Butterfly harvest v2 â€” saves=32, cap=37, buf=14800, lwOff=12848 (4x consistent, crash/reload pattern)
- Host server operational, beacons received from the-console
- Tooling made Windows-compatible (selftest, build_host, host.py, index.html)

## Oct 22-23 -- ASLR Defeat Work
- APNG overread leaks 1651 heap pointers on device (V674)
- Heap topology mapping via binary subdivision scanner (V650-V655)
- DAZ confirmed ON -- all float64 channels flush denormals to zero
- BigUint64Array confirmed as bypass for raw pointer handling

## Oct 21-22 -- Full R/W Confirmed
- All 12 Canvas2D APIs confirmed working through alias (V630)
- Crash oracle working -- forge m_stateStack, lineWidth reads 8B at target
- 10+ info leak approaches exhausted (AB zero-init, freed memory, butterfly, etc.)
- OOB state stack read designed as info leak candidate

## Oct 20-21 -- Canvas UAF Breakthrough
- CVE-2026-43720 Canvas getContext() UAF confirmed LIVE on PS5
- IsoHeap is OFF on PlayStation (WTF_MAKE_ISO_ALLOCATED = FastMalloc)
- Same-type reclaim CONFIRMED on device (V573) -- bidirectional R/W
- Full alias diagnostic V562 -- all 12 APIs pass

## Oct 18-19 -- Surface Audit + New Bugs
- CSSFontFace UAF (CVE-2026-43715) confirmed DoS-only (Timer RELEASE_ASSERT)
- tee() type confusion and private-name inversion confirmed but contained (JS builtin wall)
- WK-1400 source audit complete -- 15+ subsystems, 0 exploitable entry bugs
- PLATFORM(PLAYSTATION) audit -- 22 guards, all logging-only or stricter

## Oct 17-18 -- MetadataTable Declared DEAD
- 38M entries x 104B/node = 3.7GB AST exceeds 1200MB process limit
- .length=81400 confirmed as false positive (correct literal length)
- All Relapse CVEs confirmed patched on 14.10
- Pivot to broad surface audit

## Oct 15-16 -- MetadataTable Discovery
- Bug 317632 integer overflow discovered and confirmed on device
- Correct stride 112 bytes (p142)
- Forward-only sweep directionality proven (p143/p144)
- Bait-and-switch heap groom demonstrated
- JSString header corruption confirmed (14/14 targets, p146)
