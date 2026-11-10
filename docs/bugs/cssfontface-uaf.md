# CSSFontFace iterateClients UAF (CVE-2026-43715)

**Status:** Unpatched in WK-1400 (PS5 14.10). Device test deployed; crash not yet confirmed.
**CVE:** CVE-2026-43715
**Upstream:** Patched in commit `5aedb82710ba578f`.

## Bug

`iterateClients()` in CSSFontFace.cpp copies a WeakHashSet into a `Vector<Ref<Client>>` and then invokes a callback on each client in the vector. When `FontFace::fontStateChanged` runs as one of those callbacks, it resolves `m_loadedPromise`. The promise resolution path checks whether the result is a thenable -- if it has a `.then` property, the engine calls that getter synchronously.

An attacker places a getter on `FontFace.prototype.then` that removes a style element and forces a synchronous layout. This causes a client to be removed from the underlying WeakHashSet while the callback loop is still iterating over its snapshot. On the next iteration, the loop invokes a callback on the now-disconnected client -- a use-after-free.

## Trigger

```js
Object.defineProperty(FontFace.prototype, 'then', { get() {
    document.getElementById('victim-style').remove();
    document.body.offsetHeight; // force synchronous layout
}, configurable: true });

const face = new FontFace('test', 'url(font.ttf)');
document.fonts.add(face);
face.load();
```

Calling `face.load()` starts font loading. When the font finishes loading, the engine calls `setStatus`, which triggers `iterateClients`, which resolves the promise, which checks for a thenable, which invokes the attacker's `.then` getter.

## Call Chain

1. `face.load()` initiates font loading.
2. The font loads successfully. The engine calls `CSSFontFace::setStatus(Status::Success)` (CSSFontFace.cpp:571-628).
3. `setStatus` calls `iterateClients(callback)` (CSSFontFace.cpp:55-59).
4. The first client callback is `FontFace::fontStateChanged` (FontFace.cpp:332-356).
5. `fontStateChanged` resolves `m_loadedPromise` at line 344.
6. `DOMPromiseProxy::resolve()` calls `JSDOMPromiseDeferred::resolve()`, which enters JavaScript execution.
7. The JavaScript engine checks whether the resolved value is a thenable. It reads the `.then` getter, which runs the attacker's synchronous JavaScript.
8. The getter removes a style element and forces a layout update. This disconnects a client from the WeakHashSet.
9. The loop continues to the next client and invokes a callback on the now-disconnected object -- use-after-free.

## Fix (Upstream)

Commit `5aedb82710ba578f` adds a `clients.contains(client)` check before each callback invocation, skipping any client that was removed during iteration. The WK-1400 build on PS5 14.10 does not include this fix.

## UAF Targets

The disconnected client can be any of the following types. Each receives a different callback after disconnection:

1. **CSSFontSelector** -- receives `fontLoaded`, which calls `dispatchInvalidationCallbacks()`.
2. **CSSSegmentedFontFace** -- receives `fontStateChanged`, which clears `m_cache`.
3. **CSSFontFaceSet** -- receives `fontStateChanged`, which calls `decrementActiveCount()` and then `completedLoading()`.
4. **FontFace** -- resolves the JavaScript promise. This is the first client in iteration order and is the one that triggers the thenable getter.

## Exploitation Path

1. The UAF produces a controlled callback invocation on a disconnected CSSFontSelector or CSSSegmentedFontFace object.
2. Heap grooming replaces the freed object with attacker-controlled data in the same FastMalloc size class.
3. Gigacage is disabled on PS5, so all allocations (including ArrayBuffer backing stores) share the same heap.
4. If the attacker controls the replacement memory, a StructureID corruption leads to type confusion.
5. Type confusion yields `addrof` and `fakeobj` primitives, which provide arbitrary read/write.

## Source Locations (WK-1400)

- `CSSFontFace.cpp:55-59` — VULNERABLE `iterateClients` (no `contains()` check)
- `CSSFontFace.cpp:571-628` — `setStatus()` calls `iterateClients`
- `CSSFontFace.cpp:428-438` — `fontLoadEventOccurred` → `iterateClients`
- `FontFace.cpp:332-356` — `fontStateChanged` → resolves `m_loadedPromise`
- `DOMPromiseProxy.h:335-343` — `resolve()` iterates deferred promises
- `JSDOMPromiseDeferred.cpp:55-90` — `callFunction` → enters JSC

## PS5 Requirements

All required APIs have been confirmed available on PS5 14.10:

- **FontFace API:** Available (confirmed in V399).
- **Object.defineProperty on FontFace.prototype:** Available (standard JavaScript).
- **document.fonts:** Available (confirmed in prior FontFace tests).
- **Font loading from ArrayBuffer or data: URI:** Available.

## Device Test

Deployed as `fa-v445-fontface.html` (probe `p445-fontface-uaf.js`). The test tries local font names first and falls back to a data: URI TTF. Awaiting crash confirmation on device.

## V975 (14.20, designed 2026-11-10, B) — tail-survival reclaim oracle

Follows the V974B v2 result (TRIG 9/9, armed CRASH 3/3 in-window, control 6/6): the trigger works but the
`setStatus(Success)` tail kills the process before JS can scan. Source verification (WebKit-1400, `CSSFontFace.cpp/.h`,
`FontFace.cpp/.idl`):

1. **Tail structure** — `setStatus` (:571-628): `iterateClients(fontStateChanged)` :591 → `m_status=newStatus` :595 →
   `m_timeoutTimer.stop()` **only** in the Success/Failure branches :625 (Loading/TimedOut branches start the timer or
   recurse; recursion to Failure reaches :625 too). `fontLoadEventOccurred` (:428-439) runs **after** setStatus and has
   no tail — useless for avoidance. `timeoutFired`/`fontLoaded`/`font()` all hold `Ref protectedThis` (:443/:632/:726)
   ⇒ **setStatus is the only unprotected host** of the thenable re-entry (the getter rides `fontStateChanged` promise
   resolution, which exists only in `setStatus`).
2. **JS same-class creation inside the getter — VERIFIED** — `new FontFace(family, src)` (FontFace.idl:49) →
   `FontFace::create` (FontFace.cpp:58-62) → `new FontFace(*cssFontSelector)` with member-init
   `m_backing(CSSFontFace::create(fontSelector, nullptr, this))` (:157-162) + `addClient` ⇒ a fresh CSSFontFace is
   allocated **synchronously** inside the getter, after the victim free. p458 B-CHECK precedent (14.10): sprayed face
   #55 read `m_status=Success(3)`.
3. **sizeof** — static member sum (LP64, `CSSFontFace.h:184-206`: variant 16 + RefPtr 8 + 2×Vector 32 +
   FontFeatureSettings ~16 + behavior/sizeAdjust ~8 + WeakHashSet ~24-32 + WeakPtr 8-16 + FontSelectionCaps 12 +
   status/bools/enums ~8; `Timer m_timeoutTimer` last, WTF Timer.h absent from the OSS zip) ≈ **188-200** ⇒ consistent
   with the device-calibrated 192B class; exact sizeof only provable on device. Non-polymorphic (`RefCounted` only, no
   vtable). **mode=face is size-proof** (faces self-size to the class); **mode=ab tests the 192 assumption directly**.

**Design** (`probes/canvas-uaf/v975-fontface-tail.html`, deployed 2026-11-10 + both index menus):
- **mode=face** (`&via=js|style`, default js): getter frees the victim (rule mutation + layout), then reclaims with K
  live CSSFontFaces — js: K×`new FontFace()`+`document.fonts.add` right after the free; style: one `<style>` with K
  `@font-face` rules injected before a single forced layout (sheet order ⇒ victim rebuild+free first, then K faces
  back-to-back). Tail then runs on a LIVE face: valid `m_thread` ⇒ assert passes ⇒ survive; stray
  `m_status=Success(3)` lands in a never-pumped face ⇒ `face.status==='loaded'|'error'` = **STATUS-HIT** (acceptance:
  HIT = JS-observable UAF writeback into a live same-class object, process survives; NOHIT = reclaim missed; in-window
  CRASH = wall deeper — scrubbing/failed live reclaim).
- **mode=ab**: getter frees with NO reclaim; tail runs on freed-but-intact memory (original m_thread intact ⇒ assert
  passes ⇒ survive); ArrayBuffer(192) wave sprayed as the FIRST action in the promise callback, then scanned:
  byte130∈{3,4} = **WB** (first JS-readable freed-memory readback on 14.20); pointer-shaped qwords at +0x58/+0x68 =
  **LEAK-HIT**; all-zero = NOHIT (heap-identifier isolation / size mismatch ⇒ face mode is the only reclaim); CRASH
  before any SCAN = tail fatal even with zero reclaim ⇒ both reclaim-then-read strategies dead.
- 5s pending grace (stale 3s block-period timer firing on the reclaimed block is attributed via CRASH, not lost);
  `arm=0` control; MAXLOADS 6 → phase=done; stop after 2 crashes; no address math, fixed 48-word dump only.

**14.20 on-device results (V975, 2026-11-10 17:24–17:27 UTC):**
- **face armed (via=js): STATUS-HIT ×4/5, 4 survivals, 1 in-window CRASH** (try 5). Each HIT: 1/64 sprayed face
  became `loaded` (never pumped) with process survival through the 5s grace — **first observable UAF writeback with
  survival on 14.20** (confirms same-class 192B reclaim + tail-on-live-face non-fatal). Control arm=0: 6/6 survived.
- **ab armed: CRASH 3/3 before any SCAN** (tail fatal on freed-but-intact memory; no WB/HIT). AB-deferred readback
  path **dead** for this trigger.

**V976 characterization (via=js, 2026-11-10 17:35–17:36 UTC, `v976-fontface-hit-char.html`):** 6/7 HIT + 1 CRASH.
Hit slot varies (idx 3,55,62,45,13,55 over 64). Hit-face vs baseline: **all JS-exposed FontFace properties identical
except `status`** (`loaded` vs `unloaded`); `style/weight/stretch/variant/featureSettings/display/unicodeRange` and
`loaded` Promise unchanged. Observable corruption = `m_status` writeback only; internal fields (+0x58/+0x68 pointers)
not surfaced by FontFace JS API and AB readback path is fatal ⇒ **no JS-readable leak found**. Primitive classified
as a narrow, repeatable status-flip oracle with survival. via=style comparison pending.

## V977 (designed 2026-11-10) — primitive amplification / leak-channel sweep

Follow-up probe (`probes/canvas-uaf/v977-fontface-primitive.html`) tests whether the V975 status-flip
primitive can be deepened into a leak or broader corruption. It runs five parallel hypotheses in one
load:

1. **Timer side-channel** — the tail calls `m_timeoutTimer.stop()` on the reclaimed live face; the probe
   checks whether any timeout behavior differs after a HIT.
2. **Status-driven behavior oracle** — re-loading a HIT face, calling `document.fonts.check()`, and
   measuring timing/promise settlement vs. a baseline.
3. **Multi-trigger cascade** — attempts nested `face.load()` inside the getter to see if multiple
   `setStatus` tails can cascade.
4. **Other 192B occupants** — sprays a rotating list of allocation families (strings, ArrayBuffer(192),
   Map/Set, URLSearchParams, Headers, FormData, ImageData, style attributes, etc.) after the free to see
   if any cross-type reclaim survives the Timer assert and produces a JS-visible anomaly.
5. **Promise-state leak** — races `face.loaded` against a marker promise to detect whether the UAF
   causes synchronous settlement.

**Expected outcome:** If any hypothesis produces a non-status side effect, pointer-shaped value, or
reproducible timing signal, the FontFace writeback can be deepened. If all beacons match the V976
baseline (status-only), the primitive remains a narrow status-flip oracle and the Canvas UAF stays the
primary exploitation vector.

## V977 on-device results (2026-11-10 18:15–18:24 UTC, 679 beacons)

Armed runs only (`arm=1`), cases `all`/`timer`/`status`/`types`:

| Case | Scans | HIT | CRASH | Notes |
|------|-------|-----|-------|-------|
| all    | 6  | 6/6 | 1 (try 6) | H1+H2 exercised; H3/H4/H5 did not actually run |
| timer  | 8  | 8/8 | 0 | `TIMER fired=1` every run |
| status | 10 | 10/10 | 2 (try 2, try 5) | HIT `load()` never settles; BASE rejects ~0.4–0.9 s |
| types  | 8  | 8/8 | 0 | `TYPESWEEP` always `type=string8,idx=0` |

Hit rate stays ~100% when the process survives; crash rate ~7% (3/41), matching V975. Hit slot varies
(1, 2, 3, 5, 54, …), same as V976.

**What actually produced data:**

- **H2 (status oracle) — only real signal.** In every status run the HIT face's `face.load()` promise
  **never settled** within the 5 s window (0 × `HIT-THEN`, 0 × `HIT-CATCH`), while the baseline
  `unloaded` face rejected with `NetworkError` at ~0.4–0.9 s (`BASE-CATCH`). This is consistent with
  `FontFace::load()` returning the existing (never-resolved) `m_loadedPromise` because `m_status` was
  flipped to `Loaded` by the stray write — i.e. a *stuck-promise* consequence of the status flip, not a
  new memory disclosure. `document.fonts.check()` returned `true` for both HIT and baseline, so the
  check() part of the oracle does not discriminate.
- **H1 (timer) — negative, but the test was weak.** `TIMER fired=1` in all 14 runs; `elapsed` was
  200–1300 ms and is dominated by the probe's synchronous XHR beacons, not by font-timer behaviour.
  `setTimeout` is unrelated to `CSSFontFace`'s internal `m_timeoutTimer`, so this never tested the
  tail's `stop()`.

**What did NOT actually run (probe bugs):**

- **H4 (other 192B occupants) — never tested.** `testTypeSweep()` reads `typeidx` from the URL but
  writes the next index to `localStorage`, so every reload re-ran `type=string8,idx=0`. No cross-type
  reclaim family was ever sprayed.
- **H5 (promise-state leak) — never tested.** `testPromiseLeak()` uses `var h` and dereferences
  `hitFaces[h]` inside the async `.then`; with exactly one hit the index is out of range and the
  callback throws, swallowing the beacon. 0 × `PROMISE-RACE`.
- **H3 (cascade) — never tested.** `testCascade()` runs *after* the trigger returns; the nested
  `face.load()` is not executed inside the getter, so no second `setStatus` tail was ever cascaded.

**Verdict so far:** FontFace writeback is still a **status-flip oracle**. The only behavioural
difference is the stuck `loaded` promise, which follows directly from the status value. H3/H4/H5 remain
open and need a corrected probe before FontFace can be declared leak-dead.

## V978 (2026-11-10) — corrected sweep

`probes/canvas-uaf/v978-fontface-corrected.html` fixes the three V977 probe bugs and makes the timer
test meaningful:

- **Real cascade.** Up to three victims are created at setup. The `FontFace.prototype.then` getter
  removes the current victim's `<style>`, forces layout, sprays the reclaim population, then calls the
  *next* victim's `load()` **inside the getter** — so `iterateClients()` is still on the stack. Each
  stage logs `CASCADE-STAGE` / `CASCADE-NEST`; `FACESCAN` reports `stageHits` so a multi-stage hit is
  directly visible. `arm=0` still short-circuits before any free/spray.
- **Real type rotation.** `typeidx` is persisted in `localStorage` and bumped inside `doTypeSpray()`,
  so each reload tests a different family (string8/16, ArrayBuffer(176), Uint8Array, Map, Set,
  URLSearchParams, Headers, FormData, ImageData, object/double arrays, Blob, RegExp, style attribute).
  The spray happens **inside the getter** (the actual reclaim window). `TYPECHECK` re-reads a signature
  of every held object after the tail and reports `diffs` / `errs` — a stray write into object data
  shows as a diff, a write into a header shows as a thrown signature.
- **Working promise race.** IIFE per hit face; races both `face.loaded` and `face.load()` against a
  marker and reports `pending` / `settled` / `rejected`.
- **Real internal-timer test (`case=timer`).** Sprayed faces use
  `url(http://192.0.2.1/...)` (TEST-NET black hole) and `load()` is called so their 3 s
  `CSSFontFace` timeout is armed. Scan is delayed to 6.5 s. A hit face still `loaded` ⇒ the tail's
  `m_timeoutTimer.stop()` cancelled the timeout; `error` ⇒ timeout still fired; `loading` ⇒ no
  writeback. Four control faces with the same URL (allocated before the free) tell us whether the URL
  actually hangs; if controls are already `error`, the timer channel is inconclusive in this
  environment.

## V978 on-device result: trigger regression, 0/31 hits

V978 ran 8 × `all`, 8 × `cascade`, 8 × `types`, 8 × `promise` (516 beacons, 18:37–18:41 UTC).
**Every one of the 31 scans was `NOHIT`; 0 HIT, 0 CRASH.** The cascade getter did re-enter
(`CASCADE-STAGE` 1→2→3, `CASCADE-NEST` returned a Promise), so the reentrancy path was exercised —
but no `m_status` writeback ever landed.

Root cause: V978 replaced the V977-verified trigger with
`victim.style.parentNode.removeChild(victim.style)`. Removing the `<style>` tears down the face's
client set instead of leaving a stale client in the snapshot, so `iterateClients()` has nothing to
walk after the getter returns → no UAF. The second regression: victims 1 and 2 were created at setup,
and `local('Arial')` resolved them to `loaded` **before** the trigger, so the nested `load()` returned
an already-settled promise rather than starting a new `setStatus`.

## V979 (2026-11-10) — trigger restored

`probes/canvas-uaf/v979-fontface-triggerfix.html`:

- Trigger is the V977-verified one: mutate the `@font-face` rule
  (`rule.style.setProperty('font-weight', ...)`) then force `document.body.offsetHeight`. The
  `<style>` stays attached.
- Cascade stages build a **fresh** victim (`makeVictim('c1')`, `'c2'`) inside the getter, immediately
  before `load()`, so each nested stage really starts from `unloaded`/`loading`.
- Everything else (type rotation + `TYPECHECK`, IIFE promise races, 6.5 s timer test) is inherited
  from V978.

## V979 on-device results (2026-11-10 18:47-19:01 UTC, 706 beacons)

39 armed runs + 8 `arm=0` controls, 104 run ids total (a crash reloads and starts a new run id).

| case | armed | HIT | CRASH |
|---|---|---|---|
| `all` | 7 | 6 | 1 (try=7, before scan) |
| `cascade` | 8 | 8 | 0 |
| `promise` | 13 | 10 | 3 |
| `types` | 4 | 0 | 4 (100%) |
| `timer` | 7 | 5 (false positive) | 1 |
| `arm=0` | 8 | 0 (`NOHIT` 8/8) | 0 |

Real HIT: **24 / 28 valid armed runs (~86%)**. The trigger is confirmed and reproducible; `arm=0`
never hits, so the status flip is not a FontFace natural transition.

**Cascade does not amplify.** `CASCADE-NEST` proves real re-entry (stages 1->2->3, fresh victim
`unloaded`, `load()` returns a Promise), but `stageHits` is always a single face: `{"1":1}` in 7/8,
`{"2":1}` in 1/8. Never two corrupted faces in one chain. The cascade is not a write-amplification
channel.

**`types` = strongest signal, no leak yet.** All four families (`string8`, `string16`, `ab176`,
`u8-176`) emitted `TYPEWAVE made=256` and then crashed with **no `TYPECHECK`**. So the 256
allocations do land on the freed block and the first status writeback corrupts a live JS object, but
the renderer dies before it can be read. Families idx 4-14 were never tested (crashes exhausted
`MAXLOADS=8`).

**`promise` = no leak.** 32/32 `PROMISE-RACE` records are `first=pending` (16 `loaded`, 16 `load`),
while the baseline rejects `NetworkError` at ~180-220 ms. The hit face is stuck in `loading` forever
(no settle, no reject) - a consequence of `m_status=Loaded` + a never-resolved `m_loadedPromise`.

**`timer` = invalid oracle.** `hit=68` / `stageHits={"1":64}` was a false positive: timer spray
faces used `HANGURL=http://192.0.2.1/...` and called `load()`, while `scanFaces` counts
`status==='loaded'||'error'` as a hit. The dead URL makes every face `error` naturally, and the
controls were `error` too (`ctrl=eeee`). The test measured network failure, not writeback.

**Crash rate:** 9 / 39 armed runs (~23%); `types` 4/4.

## V980 (2026-11-10) — survivor-mode type reclaim + clean timer oracle

`probes/canvas-uaf/v980-fontface-typereclaim.html` keeps the V979 trigger and changes measurement:

- Type spray is tiered and small (`&tn=N`, default 24; stage 1 = `tn`, stage 2 = `tn/2`,
  stage 3 = `tn/4`) so the renderer can survive to the check.
- `TYPEPRE` logs `type,idx,want,stage` **before** allocating, so a crash maps to an exact family.
- `TYPECHECK` runs 300 ms after `FACESCAN`, `TYPECHECK2` 1.2 s later; both report `alive`, `diffs`
  and `errs` over the held objects. A changed signature is the first real leak signal.
- `reset=1` no longer clears `typeidx`; the family sweep continues. `&typeidx=N` jumps to a family.
- Timer oracle fixed: timer spray faces are plain `local()` faces that are never preloaded, so any
  status change can only come from the writeback. `error` is excluded from hits for `case=timer`.
- `&maxloads=N` (default 10) to survive the crash/reload cycle during a family sweep.

## V980 on-device results (2026-11-10 19:25-19:35 UTC, 805 beacons)

| case | attempts | HIT | NOHIT | TYPE-DEATH | other |
|---|---|---|---|---|---|
| `all` armed | 10 | 10 | 0 | 0 | 0 |
| `all` `arm=0` | 10 | 0 | 10 | 0 | 0 |
| `timer` | 9 | 7 | 0 | 0 | 2 (tail crash after `FACEWAVE`) |
| `promise` | 8 | 6 | 0 | 0 | 2 (tail crash after `FACEWAVE`) |
| `types` | 20 | 0 | 0 | **20** | 0 |

**Timer oracle is now clean and positive.** 7/7 completed timer runs:
`hit=1, hitStat=s1_N:loaded, sprayStatuses=uuuuluuu..., ctrl=uuuu`. Exactly one of the 64 sprayed
faces becomes `loaded` (never pumped), the other 63 stay `unloaded`, and all four pre-free control
faces stay `unloaded`. This is the cleanest confirmation so far: the dangling getter writes
`m_status=Loaded` into exactly one live same-class object and the process survives. (V979's
`hit=68` was the dead-URL false positive; it is gone.)

**All 15 type families die in the tail.** 20/20 `types` attempts (15 families, two passes)
emitted `TYPEPRE` then `TYPEWAVE made=24|8` and then **nothing**: no `DONE`, no `FACESCAN`, no
`TYPECHECK`, no `TYPECHECK2`. The spray itself completes (`errs=0`), so the death is *after*
allocation, in the `setStatus` tail. This matches V975 `mode=ab` (tail fatal on freed-but-intact
memory) and explains why every non-`CSSFontFace` reclaim crashes: the tail calls
`m_timeoutTimer.stop()` on the reclaimed block, which is only valid when the block is a fresh
`CSSFontFace`.

**Structural conclusion: the type-reclaim leak path is dead.** To survive the tail the reclaimed
object must be a real `CSSFontFace`; once it is, the only JS-observable effect of the writeback is
`m_status`. `TYPECHECK` can never run because the tail kills the process first. FontFace is a
reliable **single-face status-flip oracle with survival**, not a memory-corruption primitive.

**Cascade still does not amplify** (`stageHits` `{"1":1}` 6/10, `{"2":1}` 4/10 in `all`), and
`promise` is still 32/32 `first=pending` vs baseline `NetworkError` at ~170-220 ms.

**Attempt economics:** `MAXLOADS=10` gives only ~5 `types` attempts per session because every crash
consumes two loads (attempt + crash-detection reload).

## V981 (2026-11-10) — fake-loaded consumer probe (last FontFace experiment)

`probes/canvas-uaf/v981-fontface-fakeloaded-consume.html` accepts the V980 conclusion and asks the
only remaining question: does any consumer trust `status()`/`document.fonts.check()` on a
**fake-loaded** face (`m_status=Loaded`, `m_font=null`) and then use the missing font?

- Reuses the V980 trigger and reclaims with `K` live `FontFace`s so the `setStatus` tail survives;
  the writeback flips exactly one sprayed face to `loaded`.
- Finds the hit face, then feeds its family to: DOM text (`offsetWidth/Height`,
  `getBoundingClientRect`), SVG `<text>` (`getBBox`, `getComputedTextLength`), Canvas 2D
  (`measureText`, `fillText`, `getImageData` black-pixel count), bold+italic trait mismatch, and an
  SVG data-URL `<img>` load.
- Every consumer is preceded by a `PHASE` beacon, so a crash maps to the exact operation.
- Logs `HIT-CHECK` (`document.fonts.check` plain/text), `HIT-LOADED` (promise state) and
  `HIT-FLOAD` (`document.fonts.load`) before the consumers.
- `arm=0` runs the same battery on a never-loaded spray face as the baseline; `&print=1` optionally
  calls `window.print()`; `&maxloads=N` (default 8).
- Acceptance: if a consumer crashes or renders differently from the `arm=0` baseline, the
  fake-loaded state is reachable from a dangerous path; otherwise FontFace is closed as a pure
  status oracle.

## V981 on-device results (2026-11-10 19:47-19:51 UTC, 693 beacons) — FontFace closed

20 armed attempts (`ctx` 6, `all` 8, plus the 8 `arm=0` baseline runs), 12 complete armed
batteries (5 `ctx` + 7 `all`), 2 tail crashes (1 per case, both **after `FACEWAVE`, before
`DONE` — the V980 `m_timeoutTimer.stop()` death, not a consumer).

| run group | attempts | complete battery | HIT | crash |
|---|---|---|---|---|
| `ctx` armed | 6 | 5 | 5/5 | 1 (tail) |
| `all` armed | 8 | 7 | 7/7 | 1 (tail) |
| `ctx` `arm=0` | 8 | 8 | 0 (NOHIT 8/8) | 0 |

`stageHits` in `all`: `{"1":1}` 5x, `{"2":1}` 2x — still exactly one face, cascade still does
not amplify.

**No consumer crashed.** `PHASE` beacons total 144 = 8 phases x 10 armed batteries + 8 x 8
baseline batteries, i.e. every single `PHASE` was followed by its result tag. DOM, SVG
(`getBBox`/`getComputedTextLength`), Canvas 2D (`measureText`/`fillText`/`getImageData`),
bold+italic matching and the SVG data-URL image all completed normally on the fake-loaded face.

**Rendering is bit-identical to the baseline.** All 10 armed batteries and all 8 `arm=0`
batteries produced exactly the same numbers:

| consumer | HIT (fake-loaded) | BASE (`unloaded`) |
|---|---|---|
| DOM | `w=325,h=63,rect=325.0x63.0` | identical |
| SVG | `bbox=143.00x63.00,len=143.00` | identical |
| Canvas | `measure=143.00,blackPx=1364` | identical |
| MATCH (bold+italic) | `156x52` | identical |
| SVGIMG | `loaded,w=320,h=120` | identical |

So layout/paint never touches the missing `m_font`: the fake-loaded face is skipped and the
fallback font is used, exactly like a face that is genuinely `unloaded`. There is no
dereference, no crash and no state-dependent rendering difference.

**The only observable effects are CSSOM-level lies:**

| probe | HIT | BASE |
|---|---|---|
| `face.status` | `loaded` | `unloaded` |
| `document.fonts.check('48px "fam"')` | **`true`** (plain and with text) | `false` |
| `document.fonts.load('48px "fam"','HELLO')` | **resolves `arr1`** | rejects `NetworkError` |
| `face.loaded` | `pending` (never settles) | `pending` |

`document.fonts.check()` returning `true` for a face whose `m_font` is null is a clean,
JS-visible, crash-free confirmation of the writeback — a better oracle than scanning
`status` — but it is only a boolean. `document.fonts.load()` resolving with a 1-element array
instead of rejecting is the same lie one level up; the returned face still has no font data
and the renderer never uses it.

**Verdict: FontFace is closed.** The UAF is real and reliably reproducible, and it yields a
survivable single-face `m_status` flip with a clean `check()` oracle, but the writeback reaches
only `m_status`; every non-`CSSFontFace` reclaim dies in the `setStatus` tail, and every
survivable reclaim is invisible to layout, SVG, Canvas and printing. No leak, no pointer read,
no corruption. Further FontFace work has no upside.
