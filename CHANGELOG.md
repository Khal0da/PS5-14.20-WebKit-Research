# Changelog

## Nov 10 (night) -- V981 results: fake-loaded face only lies to CSSOM, FontFace closed
- **V981 on-device (693 beacons, 19:47–19:51 UTC):** `ctx` 5/5 HIT, `all` 7/7 HIT, `arm=0`
  **8/8 NOHIT**; 2 crashes, both in the `setStatus` tail *after* `FACEWAVE` (V980 death), none
  inside a consumer.
- **No consumer crashed:** `PHASE` count 144 = exactly 8 phases × 10 armed + 8 × 8 baseline
  batteries. DOM, SVG `getBBox`/`getComputedTextLength`, Canvas 2D `measureText`/`fillText`/
  `getImageData`, bold+italic match and the SVG data-URL image all ran to completion.
- **Rendering is identical to baseline** on every consumer (DOM `325x63`, SVG `143.00x63.00`,
  Canvas `143.00`/`1364px`, MATCH `156x52`, SVGIMG `320x120`) → layout/paint never touches the
  missing `m_font`; the fake-loaded face is skipped like an `unloaded` one.
- **Only CSSOM lies:** `status=loaded`, `document.fonts.check()` **`true`** (baseline `false`),
  `document.fonts.load()` **resolves `arr1`** (baseline `NetworkError`), `face.loaded` stays
  `pending`. Good oracle, but only booleans — no leak, no pointer read, no corruption.
- **FontFace closed.** Cascades still never amplify (`stageHits` one face in 7/7).

## Nov 10 (night) -- V981 fake-loaded consumer probe (last FontFace experiment)
- `probes/canvas-uaf/v981-fontface-fakeloaded-consume.html`: after the V980 status flip, feeds the
  fake-loaded family (`m_status=Loaded`, `m_font=null`) to DOM text, SVG `<text>`
  (`getBBox`/`getComputedTextLength`), Canvas 2D (`measureText`/`fillText`/pixel readback),
  bold+italic trait mismatch, and an SVG data-URL image. Each consumer is preceded by a `PHASE`
  beacon for crash attribution; `arm=0` runs the same battery on a never-loaded face as baseline.
  Index bumped to `cb=981`; V980 demoted to reference-only.

## Nov 10 (night) -- V980 results: clean timer oracle + type path proven dead
- **V980 on-device (805 beacons, 19:25–19:35 UTC):** `all` armed **10/10 HIT**, `arm=0`
  **10/10 NOHIT**, `timer` **7/7 clean HIT**, `promise` **6/6 HIT**, `types` **20/20 TYPE-DEATH**.
- **Timer oracle fixed and positive:** every completed timer run is
  `hit=1, hitStat=s1_N:loaded, sprayStatuses=uuuuluuu..., ctrl=uuuu` — exactly one of 64 sprayed
  faces flips to `loaded`, controls stay `unloaded`, process survives. Cleanest writeback proof.
- **All 15 type families die after `TYPEWAVE`, before `DONE`/`FACESCAN`/`TYPECHECK`** (spray
  completes, `errs=0`). Death is in the `setStatus` tail (`m_timeoutTimer.stop()`), which is only
  valid on a real `CSSFontFace` — matching V975 `mode=ab`. The type-reclaim leak path is
  structurally dead; FontFace is a status-flip oracle, not a corruption primitive.
- `MAXLOADS=10` yields only ~5 `types` attempts/session (each crash burns 2 loads).

## Nov 10 (late) -- V979 results + V980 survivor-mode type reclaim (deployed + indexed)
- **V979 on-device (706 beacons, 18:47–19:01 UTC):** 39 armed + 8 `arm=0`. `all` 6/7 HIT,
  `cascade` 8/8, `promise` 10/13, `types` 0/4 with **4/4 CRASH**, `timer` 5/7 but a **false
  positive**, `arm=0` 8/8 `NOHIT`. Real HIT **24/28 valid armed (~86%)**; trigger confirmed.
- **Cascade does not amplify:** `CASCADE-NEST` proves re-entry 1→2→3 with fresh `unloaded`
  victims, but `stageHits` is always one face (`{"1":1}` 7/8, `{"2":1}` 1/8).
- **`types`:** all four families crashed right after `TYPEWAVE made=256` with no `TYPECHECK` —
  the reclaim lands on a live JS object but the renderer dies before it can be read.
- **`promise`:** 32/32 `first=pending` vs baseline `NetworkError` at ~180–220 ms; stuck, no leak.
- **`timer` invalid:** `hit=68` came from the dead 192.0.2.1 URL making every face `error`
  naturally; the oracle counted `error` as a hit.
- **V980** (`probes/canvas-uaf/v980-fontface-typereclaim.html`): tiered small type spray
  (`&tn`, default 24), `TYPEPRE` before allocation, delayed `TYPECHECK`/`TYPECHECK2` with
  `alive`/`diffs`, `typeidx` survives `reset=1`, `&typeidx=N` jump, fixed timer oracle
  (local faces never preloaded, `error` excluded), `&maxloads=N`. Index bumped to `cb=980`;
  V979 demoted to reference-only.

## Nov 10 (late) -- V978 trigger regression (0/31) + V979 trigger-fix (deployed + indexed)
- **V978 on-device (516 beacons, 18:37–18:41 UTC):** 8 × `all`, 8 × `cascade`, 8 × `types`,
  8 × `promise`; **31/31 scans `NOHIT`, 0 HIT, 0 CRASH**. Getter re-entry worked (`CASCADE-STAGE`
  1→2→3), but the trigger removed the victim `<style>` instead of mutating the `@font-face` rule,
  which tears down the client set and removes the UAF. Setup-created cascade victims were also already
  `loaded` before the trigger.
- **V979** (`probes/canvas-uaf/v979-fontface-triggerfix.html`): restores the V977-verified
  `rule.style.setProperty('font-weight', ...)` + forced-layout trigger; cascade stages now build a
  fresh victim inside the getter right before `load()`. Keeps type rotation + `TYPECHECK`, IIFE
  promise races, and the 6.5 s internal-timer test. Index bumped to `cb=979`; V978 demoted to
  reference-only.

## Nov 10 (late) -- V978 corrected amplification sweep (deployed + indexed)
- `probes/canvas-uaf/v978-fontface-corrected.html` fixes V977's three probe bugs:
  real in-getter cascade (3 victims, `stageHits`), real `localStorage`-rotated 192B-class type
  reclaim with post-tail `TYPECHECK` signatures, and IIFE promise races. Adds a real internal-timer
  test (`case=timer`): hanging `url(http://192.0.2.1/...)` faces with `load()` armed, scan at 6.5 s
  distinguishes `loaded` (timer stopped) vs `error` (timer fired) vs `loading` (no writeback), with
  pre-free control faces to validate that the URL actually hangs. `arm=0` short-circuits before any
  free/spray. Index bumped to `cb=978`.

## Nov 10 (late) -- V977 on-device results (679 beacons)
- **Armed V977 (18:15–18:24 UTC):** HIT ~100% when the process survived (32/32 scans across
  `all`/`timer`/`status`/`types`), CRASH 3/41 (~7%), hit slot varies as in V976.
- **Only real signal = H2 stuck promise:** HIT face `face.load()` never settles in the 5 s window
  (0 × HIT-THEN/HIT-CATCH) while baseline `unloaded` face rejects with NetworkError at ~0.4–0.9 s.
  Consequence of `m_status=Loaded` + never-resolved `m_loadedPromise`, not a leak.
- **H1 timer negative and weakly tested** (`setTimeout` unrelated to `CSSFontFace::m_timeoutTimer`).
- **H3/H4/H5 never actually ran** due to probe bugs: `typeidx` rotation read from URL instead of
  localStorage (always `string8`), `var h` closure in `testPromiseLeak` (0 × PROMISE-RACE), and
  cascade's nested `face.load()` executed after the trigger instead of inside the getter.
  FontFace remains a status-flip oracle; corrected probe needed before declaring leak-dead.

## Nov 10 (late) -- V977 FontFace primitive amplification / leak-channel sweep
- Designed `probes/canvas-uaf/v977-fontface-primitive.html` to test whether the V975 status-flip
  primitive can be deepened into an info leak or broader corruption. Tests five hypotheses in one
  load: Timer side-channel, status-driven behavior oracle, multi-trigger cascade, other 192B-class
  occupants, and promise-state leak. Rotates through allocation families for cross-type reclaim
  detection. Updated `docs/bugs/cssfontface-uaf.md` with the V977 design and expected outcomes.

## Nov 10 (late) -- V975 face HIT×4 + V976 characterization probe
- **V975 on-device 14.20 (17:24–17:27 UTC):** face armed (via=js) = **STATUS-HIT ×4/5 with 4 survivals**
  (each try: TRIG loading,arm=1 → FACEWAVE k=64 → FACESCAN total=64,hits=1 → `HIT STATUS-WRITEBACK-IN-LIVE-FACE:<idx>:loaded`
  → DONE → RELEASED after 5s grace); 5th try CRASH in-window (reclaim/tail race). A sprayed never-pumped
  CSSFontFace reclaimed the freed 192B block, received the stray `m_status=Success(3)` writeback from the
  `setStatus` tail, and became JS-observable as `loaded` while the process survived (tail ran on a live face,
  valid `m_thread` ⇒ `m_timeoutTimer.stop()` passed). **First observable UAF writeback primitive on 14.20
  with process survival.** AB armed (no reclaim during tail) = **CRASH 3/3 before any SCAN** (freed-but-intact
  tail fatal — scribbling). FACE control arm=0 = **6/6 survived**. Unescaped `<style>` in V975 description
  broke parsing (fixed & redeployed).
- **V976 characterization probe** (`probes/canvas-uaf/v976-fontface-hit-char.html`, deployed + indexed):
  follows V975 face-mode HIT to measure (1) repeatability/which K-slot is hit, (2) all JS-exposed FontFace
  properties of each hit face vs an unloaded baseline (family/style/weight/stretch/unicodeRange/variant/
  featureSettings/display/status) + async loaded-promise probe, (3) via=style vs via=js comparison. No address
  math, no raw reads; stop after 2 crashes.

## Nov 10 (late) -- V975 designed + deployed: tail-survival FontFace reclaim oracle (face/ab)
- Source verification (WebKit-1400): `setStatus` is the ONLY unprotected host of the thenable re-entry
  (`fontLoaded`:632 / `timeoutFired`:443 / `font()`:726 hold `Ref protectedThis`); tail = `m_status` write (:595) +
  `m_timeoutTimer.stop()` only in Success/Failure (:625); `fontLoadEventOccurred` runs AFTER setStatus (no tail) -
  useless; no remove()+iterateClients path without a setStatus tail.
- `new FontFace(family, src)` (FontFace.idl:49 -> FontFace.cpp:58-62,157-162) synchronously creates a backing
  CSSFontFace (same 192B class) - same-class spray from JS INSIDE the getter is possible (p458 B-CHECK precedent:
  sprayed face #55 read m_status=Success(3) on 14.10).
- sizeof(CSSFontFace): static member sum (CSSFontFace.h:184-206, Timer.h absent from OSS zip) ~188-200 =>
  consistent with the device-calibrated 192B class; mode=face is size-proof, mode=ab tests the assumption.
- V975 probe (`probes/canvas-uaf/v975-fontface-tail.html`, deployed + both index menus): mode=face
  (&via=js|style) = reclaim the freed 192B block with K live CSSFontFaces so the setStatus tail runs on a live
  face (m_thread valid => assert passes => survive) and the stray m_status=Success lands in a never-pumped face
  => `face.status==='loaded'` = STATUS-HIT; mode=ab = free with no reclaim (tail on freed-intact memory), spray
  ArrayBuffer(192) wave as the FIRST action after the tail => WB (byte130) / LEAK-HIT (+0x58/+0x68) / NOHIT
  (heap isolation). 5s pending grace for stale 3s timer fire; arm=0 control; stop after 2 crashes.

## Nov 10 (late) -- V974B v2: FontFace UAF Trigger Reproduced + Crash Root-Caused on 14.20
- v1/v2 lesson encoded: `.then` getter fires ONLY on resolve(FontFace) = Success path of
  `face.load()` (reject + fonts.load() array never read .then) + EAGER `face.loaded` access is
  mandatory (V457 finding). v1 (fonts.load + local-fail): NOTRIG 6/6. V974C (other session): trig=0.
- v2 (p458-exact) on-device 14.20 (~00:01 UTC): TRIG-in-iterateClients status=loading **9/9**
  (3 armed + 6 control); getter frees the CSS-connected face (adopt) + zeroed AB(192)x48 wave;
  **armed CRASH 3/3 in-window** (post-free m_status=Success write + m_timeoutTimer.stop() on
  AB-zeroed reclaim => m_thread=null => Timer RELEASE_ASSERT per CONFIRMED_VULNS S2 chain);
  **arm=0 control survived 6/6**. Root-cause-classified from beacons + source chain (Timer
  thread-check on zeroed reclaim). Readback blocked by the same wall - unblock conditions
  unchanged (valid Thread* at +176 or a free path without Timer access). Documented in
  CONFIRMED_VULNS.md S2 (14.20 live re-confirmation).

## Nov 10 -- V973 DC Run Encoded (6/6+6/6) + V974B FontFace Leak Probe
- **V973 DC on-device run (14.20, operator):** `mode=save` **6/6 PRE→CRASH**
  (two rounds ×3, tight devMs brackets around the single `save()` call),
  `mode=bp` **6/6 PRE→CRASH** (+1 interrupted PRE, not a survival), and
  **CONTROL `arm=0` survived 6/6 loads** (no fatal call ⇒ no crash). Crash is
  causally tied to the fatal call on the stale context, not trigger/spray/setup.
  Encoded: `results/vc04/v973-2026-11-09-windows.{json,md}` (server + local).
- Fixed en-route: DC reset link now auto-restarts into the run (1.5 s);
  GIVEUP no longer reload-loops (phase=done); `vc04_encode.py` now parses
  JSONL beacon events with query strings (`PRE?d=...`) and bare-PRE steps
  (step derived from `call=`).
- **V974B FontFace leak probe** (`probes/canvas-uaf/v974B-fontface-leak.html`):
  VC-06 leak test on 14.20 — CSSFontFace UAF (CVE-2026-43715 class, repo-proven
  p458 mechanism): `FontFace.prototype.then` getter frees the CSS-connected face
  and sprays a zeroed `ArrayBuffer(192)` wave (192B = sole CSSFontFace class);
  acceptance: HIT at +0x58/+0x68 (pointer qwords, the 14.10 leak offsets) = leak
  PASS; status writeback (~byte 130, Failure=4) readable = reclaim confirmed;
  all-zero = MISS; in-window death = Timer RELEASE_ASSERT class. No address math.
  Deployed to server + both index menus (NOW section). CONTROL arm=0 baseline.
- Server ops: klog capture still blocked (PS5 9027 closed); VC-04 remains
  open pending native diagnostics.

## Nov 9-10 -- VC-04 (B) Capture Path Prepared; Work Resumed
- VC-04 klog/minidump work RESUMED by explicit operator decision (was stopped
  earlier). Capture path prepared end-to-end, tooling smoke-tested:
  - `probes/canvas-uaf/v973-vc04-dc.html`: frozen diagnostic replay of the two
    inferred-crash configs, one deterministic call per load with sub-second
    bracketing (`PRE → call → POST → CLEAR → ALIVE1/ALIVE3`); modes
    `?mode=save` (V923H save200) and `?mode=bp` (V923C nospray); `&arm=0`
    control, `&scan=1` exact-V923H replication; paced reloads, no AB scan by
    default (excludes the scan as crash site).
  - `tools/vc04_encode.py`: `windows` (beacon log -> crash windows, JSONL or
    pipe-extract), `capture` (klog snapshot via send.py + payloads/klog.js raw),
    `correlate` (encoded record schema vc04-encoded-crash-record/1),
    `attribute` (WebKit-1400 candidate table with source refs).
  - Precomputed correlation anchors: `results/vc04/v923h-windows-2026-11-08.*`
    (10/10 SAVE-PRE -> crash) and `results/vc04/v923c-windows-2026-11-08.*`
    (12/12 BP + 20/20 SAVE -> crash).
  - `tools/host.py`: beacon probe-ID parsing now accepts suffixed tags
    (V923H/V928B style) that were previously falling into probe=None.
- Deployed to research server 192.168.1.54 (repo `~/PS5-14.10-Jailbreak-Research`):
  v973 probe + vc04_encode.py + windows anchors + VC-04 docs; index menu
  (root + probes/) patched with a top "NOW: VC-04" section; full host.py stack
  running (DNS 53 / HTTPS 443 / HTTP 8080); `host-beacons.log` chowned back to
  ps5:ps5 (was root:root from an earlier sudo run — JSONL writes were silently
  failing since Nov 8 23:21); verified: LAN 8080/443 + tunnel ps5.mutaqan.com
  all 200, beacon self-check recorded with probe=V973.
- Runbook v2 added to docs/VC04_CRASH_DIAGNOSTICS_CAPTURE_CHECKLIST.md;
  VC-04 row + next-steps updated in CANVAS_GETCONTEXT_UAF_EVIDENCE_ASSESSMENT.md
  and P2_CONFIRMATION_PLAN.md (P2-T2 acceptance unchanged).
- Direction note recorded in P2 plan: "V925 alias -> arbitrary WebContent R/W"
  evaluated and rejected for now per documented walls (V925 post-free matrix:
  any call on stale wrapper crashes; DEAD_ENDS crash-oracle computational wall;
  CONFIRMED_VULNS info-leak blocker). Primitive discussion gated on VC-04
  revealing a non-fatal fault mechanism + surviving call path.

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
- V592: Butterfly harvest v2 — saves=32, cap=37, buf=14800, lwOff=12848 (4x consistent, crash/reload pattern)
- Host server operational, beacons received from 192.168.1.176
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
