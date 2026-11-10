# PS5 14.20 WebKit Research (WebKit-605.1.15 / 1400)

Research workspace for PlayStation 5 firmware **14.20** (Prospero/FreeBSD r230171, AMD Zen 2, 16KB pages) targeting the in-box browser engine **WebKit 605.1.15 (WebKit-1400)**. Focus: memory-safety bugs reachable from WebContent on 14.20, with device-confirmed probes and beacon-based diagnostics.

> **Disclaimer:** Authorized security research on personally owned hardware. No ready-to-run exploit chain is published here.

## Environment (confirmed)

| Property | Value |
|---|---|
| Firmware / UA | 14.20 — `Mozilla/5.0 (PlayStation; PlayStation 5/14.20) AppleWebKit/605.1.15 ...` |
| Source tree | WebKit-1400 (primary) |
| JIT | Disabled (LLInt only) |
| IsoHeap (WebCore) | OFF on PlayStation build (`BPLATFORM(PLAYSTATION)`) |
| Gigacage | Disabled (AB backing stores share heap with objects) |
| Available (relevant) | Canvas 2D, FontFace, Workers, WebSocket, fetch, RAB, WeakRef/FR, BigInt, Atomics, MessageChannel |
| Not available | WebAssembly, SharedArrayBuffer, WebGL, WebAudio, IndexedDB, ServiceWorker, WebGPU, OffscreenCanvas |

## Current status (2026-11-10)

### 1) CSSFontFace `iterateClients` UAF — CVE-2026-43715 (WK-1400 unpatched)
- **Trigger reproduced on 14.20 (V974B v2, p458 recipe):** eager `face.loaded` + `face.load()` on a CSS-connected `@font-face{src:local('Arial')}` → `.then` getter fires synchronously inside `iterateClients` (status=loading). Getter mutates the rule + forced layout (adopt frees the backing CSSFontFace) — TRIG 9/9.
- **Timer wall (confirmed):** armed free + zeroed `ArrayBuffer(192)` reclaim → **CRASH 3/3** in the post-`iterateClients` tail of `setStatus(Success)`: `m_status` write (:595) then `m_timeoutTimer.stop()` (:625) on `m_thread=null` (RELEASE_ASSERT). Control (no free/spray) **6/6 survived**. Readback via AB blocked.
- **Tail-survival pivot (V975, first observable UAF writeback with survival on 14.20):** reclaim the freed 192B block with **live** CSSFontFaces inside the getter so the tail runs on a valid object (`m_thread` intact ⇒ timer assert passes).
  - `mode=face, via=js` (armed): **STATUS-HIT ×4/5 with 4 survivals** (1/64 never-pumped sprayed face becomes `status="loaded"` each hit; 1 in-window crash = reclaim/tail race). AB-deferred (`mode=ab`, no reclaim during tail): **CRASH 3/3 pre-scan** (freed-intact tail fatal). Control `arm=0`: **6/6 survived**.
- **Characterization (V976):** `via=js` **10 HIT / 3 CRASH** across runs (~repeatable); hit slot varies (e.g. 3,13,45,55,62). JS-observable corruption = **`status` flip only**; all other exposed FontFace properties identical to baseline. `via=style` **0/4 CRASH** (rejected). **No JS-readable pointer leak** (+0x58/+0x68 not surfaced by FontFace API; AB readback path fatal).
- **Source audit (iterateClients+thenable-reentry pattern):** scanned all `copyToVectorOf<Ref<` sites and promise-resolve re-entry hosts in WebCore/WebKit-1400 — **CSSFontFace is the only releasable target** (others Ref-protected / no `adopt`/repoint / no dangerous JS tail). Classified as a **narrow, repeatable status-flip oracle with survival; leak/arb-RW from this path blocked**.

### 2) Canvas `getContext()` reentrant UAF — CVE-2026-43720 (VC chain)
- Reentrant `bitmaprenderer`↔`2d` trigger and alias/reclaim behavior exercised on 14.20 (V569–V973 series; v925 alias discriminator reproducible). VC-01/03 supported behaviorally; **VC-04 (crash root-cause / native attribution) remains OPEN** pending native diagnostics.
- **VC-04 (B) capture prepared:** deterministic DC replay probe `v973-vc04-dc.html` (save/bp/control, anchored `PRE→call→CRASH` windows: save 6/6, bp 6/6, control survived) + `tools/vc04_encode.py` (`windows/capture/correlate/attribute`) and runbook/checklist docs. **Blocked:** PS5 loader 9027 closed and no `/dev/klog` channel on 14.20 — cannot capture/symbolize; do not rerun without a capture mechanism.
- APNG-overread info-leak (v938B–v953B) and save-count OOB claims: **no working leak** established here (see `docs/DEAD_ENDS.md`).

### 3) Other notes
- RAB/TypedArray/Promise/Intl/streams/DOM reentrancy canaries (v961A–v974A series) and APNG stability (v982B) probed; no confirmed new primitive beyond the above. See `CHANGELOG.md` and `docs/DEAD_ENDS.md`.

## Repository layout

| Path | Purpose |
|---|---|
| `probes/canvas-uaf/` | Canvas (v569–v973, v982B) and FontFace (v972B, v974B/C, v975–v981) probes |
| `probes/` | Recon, candidates, press/sweep/streams/metadata probes and index menus |
| `docs/` | Evidence/plan/checklists (`P0`–`P2`, VC-04), bug notes (`docs/bugs/`), confirmed vulns, dead ends, reports |
| `tools/` | `host.py` (beacon + static host), `vc04_encode.py`, `analyze_v982b.py`, loaders/utilities |
| `results/vc04/` | Encoded VC-04/V973 correlation anchors (windows JSON/MD) |
| `assets/`, `payloads/`, `offsets/`, `src/` | Fonts/assets, payload scripts, offsets, framework sources |

## Running probes (beacon host)

```bash
# serve (HTTP; host.py also supports DNS/HTTPS flags used in lab setup)
python3 tools/host.py --http-port 8080
# open http://<host>:8080/ (probe index) on the PS5 browser and watch host-beacons.log
```

Probe discipline (P2): every probe states hypothesis + acceptance criteria; stop after 2 in-window crashes per capture run; no address scans / no blind spray fishing. VC-04 re-runs require a native capture channel (klog/9027) — see `docs/VC04_CRASH_DIAGNOSTICS_CAPTURE_CHECKLIST.md`.

## Key documents

- [`docs/CONFIRMED_VULNS.md`](docs/CONFIRMED_VULNS.md) — device-confirmed bugs and blockers
- [`docs/DEAD_ENDS.md`](docs/DEAD_ENDS.md) — exhausted vectors
- [`docs/bugs/cssfontface-uaf.md`](docs/bugs/cssfontface-uaf.md) — CVE-2026-43715: mechanism, V974B/V975/V976 results, source audit
- [`docs/P2_CONFIRMATION_PLAN.md`](docs/P2_CONFIRMATION_PLAN.md) — VC plan and gates
- [`docs/VC04_CRASH_DIAGNOSTICS_CAPTURE_CHECKLIST.md`](docs/VC04_CRASH_DIAGNOSTICS_CAPTURE_CHECKLIST.md) — (B) capture/correlate runbook
- [`CHANGELOG.md`](CHANGELOG.md) — chronological probe/session log

## License

Research materials provided for study and defensive analysis. Upstream WebKit source, where referenced, remains under its original licenses.
