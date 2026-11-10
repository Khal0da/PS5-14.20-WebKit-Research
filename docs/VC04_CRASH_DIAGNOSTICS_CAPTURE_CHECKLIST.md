# VC-04 — Crash Diagnostics Capture Checklist (PS5 14.20) — Diagnostic Only

**Goal:** Obtain symbolized/native crash evidence to attribute inferred crashes (VC-04) and inform VC-05. **This is diagnostics capture guidance, not exploitation.**

## Target cases (priority)
1. **Primary:** `V923H` — `SAVE`-path crash, **2/2 inferred** (stages), no `SLOT`/canary observed in beacons.
   - Beacon ref: `results/beacon-logs/p0-2026-11-08/v923h-beacons.txt`
   - Approx window (from prior logs): **~2026-11-08 19:22:53–19:24:11** (14.20 base), look for `*-SAVE-PRE` immediately preceding crash/reload.
2. **Secondary:** `V923C` — `beginPath/save` crashes under AB-zeroed reclaim (2/2 inferred).
   - Beacon ref: `results/beacon-logs/p0-2026-11-08/v923c-beacons.txt`

## What to capture (provide any/all available)
- **Kernel/process log / panic / crash report** covering the exact crash moment (klog, minidump, crash dump, system log — whatever 14.20/your debug setup yields).
- **Symbolized stack trace** (module + offset/symbol) for the faulting thread/process (WebKit/WebCore/renderer context as applicable).
- **Fault info:** signal/exception type, fault address/registers if available, faulting instruction/PC.
- **Time correlation:** device timestamp aligned to beacon `*-SAVE-PRE` / crash window and the probe URL+`cb` used.
- **Build/UA confirmation:** PS5 firmware (14.20 base), UA (`AppleWebKit/605.1.15 ...`), probe version/cb.

## Probe references (to reproduce the same scenario)
- V923H probe: `probes/canvas-uaf/` (V923H variant used in prior run; use the same frozen probe/cb lineage as the beaconed run). Trigger = bitmaprenderer+alpha-getter → stale 2D; crash observed at `SAVE` path under AB-zeroed reclaim (2/2). **Run only as needed to capture diagnostics; avoid address scans/memory-dialog probes (V923E/I).**
- Control (sanity): V923G/V925 same-type 2D reclaim shows stable behavior (no comparable crash) — useful for contrast, not required for (B).

## Handling constraints
- Crashes in our beacons are **inferred** (reload/pending). (B) is required to confirm faulting component and root cause.
- #59 notes AB reclaim on 14.20 can zero slot/break dispatch (vtable@+0) — diagnostics should confirm whether V923H/C map to null-vtable/dispatch, `m_stateStack`/`realizeSaves()`, or another path (WebKit-1400: `save()` unrealized; many ops call `realizeSaves()` touching `Vector<State,1> m_stateStack`).
- **VC-04/VC-05/VC-06 remain open** (verified beacon-inferred counts: V923H 10/10 SAVE, V923C 12/12 BP + 20/20 SAVE). **Technical blocker:** no native crash diagnostics (klog/stack/minidump/symbolized PC) available on 14.20 in current setup.
- **Stop:** no further work on klog/minidump capture/analysis until device situation changes. Resume attribution when (B) is provided.
- **Out of scope:** exploit development, ASLR bypass, primitive construction. Provide diagnostics only.

## When you have (B)
Share the file/text/path here. I will: map PC/symbols to WebKit-1400 (14.00+, covers 14.20) vs 14.20 behavior, classify VC-04, and update VC-05 assessment (attribution only; no primitive claims without evidence).

---

## Runbook v2 (2026-11-09) — capture path prepared; work RESUMED by operator decision

Klog/minidump work was previously stopped ("until device situation changes").
On 2026-11-09 the operator explicitly chose to resume VC-04 (B). Everything below
is prepared and smoke-tested on the tooling side; only the device steps remain.

### Prepared tooling
| Item | Path | Notes |
|---|---|---|
| DC probe (frozen replay) | `probes/canvas-uaf/v973-vc04-dc.html` | `?mode=save` = exact V923H save200 replay (minimal trigger + 200×AB(768) + `save()`); `?mode=bp` = V923C bp-nospray replay (32-save trigger + `beginPath()`). Tight bracket: `PRE → call → POST → CLEAR → ALIVE1/ALIVE3`; **no AB scan by default** (excludes the V923H scan as crash site). `&arm=0` = control (no fatal call, klog baseline). `&scan=1` = replicate V923H scan exactly. `&stop=1` = no auto-reload. Paced reloads (4 s), give-up at load 6 — **stop after 2 crashes** (see DEAD_ENDS 21-reload system-dialog incident). |
| Encoder/correlator | `tools/vc04_encode.py` | Subcommands: `windows` (beacon log → crash windows JSON+MD; JSONL or pipe-extract), `capture` (klog snapshot via `tools/send.py` + `payloads/klog.js --arg raw`), `correlate` (windows + klog → encoded record `schema vc04-encoded-crash-record/1`), `attribute` (stack/PC → WebKit-1400 candidate table). |
| Reference windows (precomputed) | `results/vc04/v923h-windows-2026-11-08.{json,md}` | **10/10 SAVE-PRE → crash** (19:22:54–19:23:51). (B) must align to these. |
| Reference windows (precomputed) | `results/vc04/v923c-windows-2026-11-08.{json,md}` | **12/12 BP-PRE → crash + 20/20 SAVE-PRE → crash** (18:08:44+). Secondary anchor. |

### Deployment note (2026-11-10 — server live)
- Beacon host runs on the research server **192.168.1.54** (`~/PS5-14.10-Jailbreak-Research`),
  full stack: DNS 53 / HTTPS 443 / HTTP **8080**; tunnel `ps5.mutaqan.com` verified 200.
- The index menu (root + `probes/index.html`) has a top **"NOW: VC-04"** section with the
  V973 DC links (SAVE / BP / CONTROL) — open from the PS5 through the tunnel.
- `host-beacons.log` ownership fixed to `ps5:ps5` (a prior sudo run left it `root:root`,
  silently dropping JSONL writes between Nov 8 23:21 and Nov 10). If you ever run
  host.py under sudo again, chown the log back afterwards.
- Windows PC-side artifacts of this session also present in the local checkout
  (`results/vc04/*`, `tools/vc04_encode.py`, runbook, DC probe).

### Device steps (14.20)
1. **Baseline clock:** start `tools/host.py`; note host UTC clock. The probe's
   `DC-ENV` beacon carries `devMs` (device epoch ms) → record skew once per session.
2. **Reset & run (primary = V923H-SAVE):** open
   `probes/canvas-uaf/v973-vc04-dc.html?mode=save&reset=1` once (clears state), then
   reopen **without** `reset`. Expected per load: `ENV → BOOT → TRIGGERED → ARM →
   PRE → (crash) →` next load logs `CRASH pending=...`. **Stop after 2 crashes**
   (`&stop=1` or just close).
3. **Control (optional):** `?mode=save&arm=0&reset=1` then reopen — full setup, no
   fatal call; klog baseline for contrast.
4. **Capture klog immediately after the crash run** (ring buffer holds it; the
   browser died but the kernel log persists):
   `python tools/vc04_encode.py capture --host <PS5_IP> --out results/vc04/runs/<stamp>`
   (requires the usual 14.20 JB root context for `/dev/klog`).
5. **Encode:** `python tools/vc04_encode.py correlate --beacons <host-beacons.log | extract> --probe V973 --klog results/vc04/runs/<stamp>/klog-snapshot.txt --case v923h-dc-save`
   → emits `results/vc04/VC04_v923h-dc-save_<ts>.{json,md}`.
6. **Attribute (when PC/stack exists):** `python tools/vc04_encode.py attribute --stackfile <stack.txt> [--pc 0x...] --out results/vc04/VC04_<case>-attribution.json`
   → matches against the WebKit-1400 candidate table (source refs from `WebKit_1400_src/`).

### What the tight bracket buys
On the default DC run the only events after `PRE` are `POST/CLEAR/ALIVE1/ALIVE3`.
If the process dies, the fault is pinned to the sub-second window around the single
fatal call — removing V923H's ambiguity (its crash window included the post-save
AB scan and the `CANARY` sync XHR; in V923C/H no `CANARY` beacon ever arrived, so
the fault is at/before the end of the call+scan block).

### Attribution expectations (WebKit-1400, from source)
- `save()` is **inline, non-virtual** (`CanvasRenderingContext2DBase.h:143` —
  `++m_unrealizedSaveCount`): a fault *inside* it implies either the write hit
  freed/decommitted memory, or the fault is in the binding trampoline
  (`castThisValue`/dispatch) above it — the `attribute` table encodes both plus
  `realizeSaves`/`realizeSavesLoop`/`restore`/`beginPath→Path::clear`/dtor paths
  with file:line refs.
- Record only fault facts (module, PC, signal, fault address). **No primitive or
  impact claims** from the stack alone (VC-06 evidence required separately).

### Handling constraints (unchanged)
- Crashes are inferred until (B) lands; do not run address-scan/memory-dialog
  probes (V923E/I) alongside the capture run — a second dialog source would
  contaminate the klog window.
- If the klog ring buffer has rotated past the crash lines, re-run steps 2–4 and
  capture sooner (crash → capture gap should be minutes, not hours).