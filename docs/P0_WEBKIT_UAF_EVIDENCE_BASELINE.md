# P0 — WebKit UAF Evidence Baseline (PS5 14.20)

**Status:** P0 extraction/classification **verified from beacon extracts** (2026-11-08). Pending: Recovery/Failed Recovery review sign-off, contradictions closure, and formal adoption (items 6–8). **UAF claim level remains: suspected, not confirmed.**  
**Scope:** WebKit / JavaScriptCore, Canvas 2D path. Local isolated lab evidence (beacons + probe defs) + upstream-ref P1 (`docs/P1_SOURCE_REVIEW_UPSTREAM_REF.md`). No V925/random probes.  
**Evidence nature:** `host-beacons.log` = **JS HTTP beacons**. Crashes are **inferred** (`*-PRE` → next-load `CRASH pending=...` / `LWCRASH` / reload). **No native stack/klog/panic/sigsegv/minidump in beacons** (grep `STACK|KLOG|PANIC|SIGSEGV|SIGBUS|FAULT|BACKTRACE|EXCEPTION` → 0 rows).

## Checklist (user P0)
- [x] **1. استلام الملف الأصلي / 2. قراءة جميع السطور / 3. سلامة JSON / 4. بصمة الملف الأصلي** — **N/A لسياق أدلة canvas-UAF الحالية.** لا يوجد “ملف أصلي JSON” مرفق لهذا المسار؛ الأدلة هي سجلات beacons نصية + تعريفات probes. (إن كان المقصود ملف/تصدير محدد، يلزم تسليمه لإكمال 1–4.)
- [x] **5. استكمال استخراج التجارب والتحقق من تصنيفها** — **مكتمل** للنطاق المتاح في `host-beacons.log` (V569, V923C/E/G/H/I/J/K/L/M, **V925**). كل سجل مُتحقَّق مقابل extract محفوظ. تحقق: `V569` HIT/LEAK=0؛ `V923I` HIT/LEAK/DONE/EXHAUSTED=0 (PAUSED attempt=120,next=0x201194000)؛ `V923C`/`V923G`/V923J–M DONE؛ `V923E` tail بلا DONE؛ **V925 DONE ×3** (21:24:18 n=8→spray[6], 21:28:00 n=8→spray[3], 21:34:02 n=12→spray[3])، كلٌ: `sameAsOrig=false`, state/wb/crossdraw/`rr ok`.
- [ ] **6. مراجعة Recovery وFailed Recovery** — مراجعة أولية أدناه؛ تحتاج تأكيد اعتماد.
- [ ] **7. إغلاق تقارير الفجوات والتناقضات** — الفجوات الحرجة موثقة (VC-02/04/05/08، تشخيص native)؛ الإغلاق يتطلب مدخلات خارجية (source 14.20 / crash dumps) أو قرار إغلاق إداري.
- [ ] **8. اعتماد Evidence Baseline** — بعد 6–7 + تأكيد قبول الأدلة.

## Evidence artifacts
- Beacon extracts (remote `host-beacons.log`, 2026-11-08/09): `results/beacon-logs/p0-2026-11-08/v569-beacons.txt`, `v923c-beacons.txt`, `v923e-beacons.txt`, `v923g-beacons.txt`, `v923h-beacons.txt`, `v923i-beacons.txt` (all V923I rows, 478), `v923j-beacons.txt`, `v923k-beacons.txt`, `v923l-beacons.txt`, `v923m-beacons.txt`, `v925-beacons.txt` (alias discriminator, 14.20 base).
- Probe definitions: `archive/v569.html`; `probes/canvas-uaf/v923{c,e,g,h,i,j,k,l,m}-*.html`. Index (frozen context): `probes/index.html` (V923M `cb=939`; V923I STOPPED — لا تشغيل).
- Prior docs: `docs/bugs/canvas-getcontext-uaf.md`, `docs/WK1400_SOURCE_AUDIT.md`, `docs/P1_SOURCE_REVIEW_UPSTREAM_REF.md`, `docs/P2_CONFIRMATION_PLAN.md`, `docs/DEAD_ENDS.md`.

**Gaps (open):** native crash reports/stack/klog for V923C/H/E/I-class failures; 14.20/WK-1400-aligned WebKit source/diff (getContext reentrancy/lifecycle, CanvasRenderingContext2DBase/CanvasPath, Cairo Path/`roundRect`/layout); no V569 scan HIT evidence; V923E full scan not completed (impractical: memory dialog). UA observed: `AppleWebKit/605.1.15` on PS5 14.20 (V923*).

## Per-experiment records (verified)

| Exp | Probe/Config (from def+beacons) | Observation (verified) | Crash (inferred) | Classification / VC | Alt. explanations |
|---|---|---|---|---|---|
| **V569** | `archive/v569.html` cal+scan/self; AB(768) spray n=200; scan 0x200000000-0x280000000 stride N768*768; `P5HIT/LEAK` searched = 0 | cal completes repeatedly (P2 ctx OK, P3 sprayed=200, P4S/T OK, DONE); P5D AB0-5 zeros. scan progressed attempts 0..2 across sessions (`base/next` advanced) **no HIT/LEAK** | scan miss by design can crash (no post-fault beacon) — **not captured** | **INCONCLUSIVE** (no primitive/leak evidence) | zeros ≠ proof of reclaim; progression ≠ correct base |
| **V923C** | 32-save trigger, zeroed AB spray; stages `bp-nospray,bp-ab50/100/200/400/800,save-ab50/100/200/400/800,rr-ab50/100/200/400/800` (verified extract: 192 rows, 18:08:44–18:11:17, 14.20) | **12/12 BP** inferred crashes (6 BP stages ×2: `BP-PRE beginPath`→`CRASH`) + **20/20 SAVE** inferred crashes (10 save/rr-ab stages ×2: `SAVE-PRE save-canary`→`CRASH`); each 2/2→`BLACKLIST`→`ADV`, then `V923C-DONE all stages complete`. no SLOT/CANARY/LEAK | **inferred** `*-PRE`→`CRASH pending=...` per attempt (verified counts from `v923c-beacons.txt`) | **INCONCLUSIVE (root cause, VC-04)**; **negative** for AB-usable reclaim via this method | AB-reclaim/zeroed-slot/dispatch or invalid state plausible (#59 consistent); **no native stack/klog** |
| **V923E** | full addr scan (trigger+AB self-forge/rr path), stride-based | progressed to tail evidence `attempt=911,next=0x208598000,load=912` (LWCRASH/reload pattern) — **no DONE/HIT/LEAK** in extract | LWCRASH/reload inferred; memory dialog blocks progress | **INCONCLUSIVE / impractical** (stopped) | miss→crash+memory dialog; not evidence of/against UAF |
| **V923G** | valid 2D-context reclaim (250 ctx), stale `CTX` ops | `BP-OK,SAVE-OK,RR-OK,BP2-OK,RR2SURV bp+roundRect survived on 2d-reclaimed slot`, 0 crashes (19:14:58–19:15:19 DONE) | none | **INCONCLUSIVE for UAF proof**; **operational PASS**: `bp/save/rr` execute under valid 2D reclaim | aliasing to live valid same-type object possible (not proof of freed misuse) |
| **V923H** | minimal trigger + zeroed AB(768) canary; `CTX.save()` scan across stages `save200/400/800,rr400,rr800` (verified extract: 19:22:53–19:24:11, 14.20) | **10/10 inferred SAVE crashes** (5 stages ×2: each `V923H-SAVE-PRE`→`V923H-CRASH pending=* :SAVE,try=1/2`→2/2 `BLACKLIST`→`ADV`), no `SAVE-OK/CANARY/SLOT/NOSLOT/LEAK`; `V923H-DONE` 19:23:53 (verified from `v923h-beacons.txt`) | **inferred** 10/10 (2/2 per stage, consistent) | **INCONCLUSIVE (VC-04/05)**; consistent negative for canary/AB-slot detectability | same class as V923C AB+SAVE; cause **undetermined without native stack/klog** |
| **V923I** | chunked scan, STOPPED in index | 478 beacon rows; **0 HIT/LEAK/DONE/EXHAUSTED**; 4 `PAUSED` milestones → `attempt=120,next=0x201194000,end=0x280000000` (30/30 per session) | per-miss LWCRASH/memory dialog (by design/context) | **INCONCLUSIVE / stopped**; negative for hit within scanned range | incomplete coverage; memory dialog impractical |
| **V923J** | valid 2D reclaim (300) + stale `roundRect` then observe (stale path ops, reclaiming ctx ops/fill/path, chain) | `RR-OK`; `OBSSTALE ipp/ips/bp/cp=true`; `OBSREC ok=60,err=0,ctrl=true/true,anom=`; `OBSFILL ok=40,err=0`; `OBSPATH survived=true`, `CHAINRES ok=true`; DONE | none | **INCONCLUSIVE VC-04/06**; **negative** for observable corruption in tested ops | JS-observable only; no raw memory read |
| **V923K** | valid 2D reclaim (300) + deep stress post-rr | `RR-OK`; `ALLPATH ok=300,err=0,anom=`; `ALLDRAW ok=300,err=0,anom=`; `ALLSTATE ok=300,err=0,anom=`; `CYCRES ok=300,err=0`; `HEAVYRES ok=30,err=0`; DONE | none | **INCONCLUSIVE VC-04/06**; **negative** for observable corruption primitive | absence of anomaly ≠ proof of memory safety |
| **V923L** | valid 2D reclaim (250) + rr + getImageData/draw/putImageData on all, stale ops | `GIDALL ok=250,err=0`; `DRAWGID ok=250,err=0`; `STALEGID ipp=true`; `PUTCR ok=250,err=0`; DONE | none | **INCONCLUSIVE**; **negative** for pixel/data deviation observable here | pixel checks limited to exercised paths |
| **V923M** | method/property survey (12 stages) on valid 2D reclaim, frozen probe `cb=939` | all stages `OPS-OK` incl. `rect/roundRect/roundRect4`, transforms, state props, dash, draw, query (`isPointIn* true, getImageData OK`), gradients/pattern, text, image/putImageData, misc; `reset=OK=na`; **0 ERR/CRASH/BLACKLIST**; DONE 20:04:47 | none | **INCONCLUSIVE**; **negative** catalog (no new anomaly/surface) | catalog ≠ exhaustive unsafe states |
| **V925** | alias discriminator (VC-03, 14.20 base, compact, fixed) — trigger + reclaim `n` real 2D contexts w/ markers + identity/state/writeback/crossdraw/`roundRect` | **DONE ×3 (reproducible):** (1) 21:24:18 n=8 → alias spray[6] (`v925s6`, lw1006/ga.07/sb6, wb hit6, xdraw red hit6 alpha18, rr ok). (2) 21:28:00 n=8 → alias spray[3] (lw1003/ga.04/sb3, wb/xdraw hit3 alpha10, rr ok). (3) 21:34:02 n=12 → alias spray[3] (same markers/hits, rr ok). All `sameAsOrig=false`, `hitN=1`. Prior diagnostics isolated & fixed: in-getter sync XHR (post-getter crash) and pre-reclaim `CTX.canvas` access. V923G control DONE same session. | none in completed runs | **PARTIAL (VC-01 strengthened, VC-03 strong behavioral aliasing)**; **INCONCLUSIVE** for proven free-before-use (VC-02) and root-cause/impact (VC-04/05/06). **Not proof of UAF** alone. | coherent alias to live spray ctx supports UAF+reclaim *or* implementation-specific aliasing; VC-02 needs 14.20 lifecycle/source mapping. Variable index (6,3,3) expected. |

## VC status (verified)
| VC | Criterion | Status | Basis / gap |
|----|-----------|--------|-------------|
| VC-01 | Reproducibility | **PARTIAL (strengthened)** | V923G/H/J/K/L/M/V923G-control complete; V923C 2/2 per stage then DONE; **V925 DONE on 14.20 base** (n=8 compact, alias spray[6], coherent state/wb/crossdraw/rr). V569 cal reproducible, scan no HIT; V923E/I incomplete/stopped. + external ref #184 (14.20 Pro, p553 3/3) supports scope — third-party, not our extract. |
| VC-02 | Object Lifecycle | **INCONCLUSIVE** | Trigger/free points **not source-mapped to 14.20**. Upstream main reentrancy can block documented replacement (P1 ref) — 14.20 delta unknown. V925 aliasing to spray object is consistent with UAF+reclaim but does not prove free timing alone. |
| VC-03 | Reference Validity | **PARTIAL (behavioral aliasing observed)** | V925 shows stale `CTX` aliases live spray 2D ctx (sameAsSpray=6, matching state/wb/crossdraw) — strong discriminating evidence. Still **cannot prove** freed-vs-aliased-lifecycle without VC-02/source mapping; treated as **not confirmed UAF**. |
| VC-04 | Memory Safety | **INCONCLUSIVE** | **No native stacks/klog/minidumps.** V923C/H crashes inferred only; V923E/I LWCRASH impractical; no confirmed UAF fault signature. |
| VC-05 | Root Cause | **INCONCLUSIVE** | Hypotheses (Cairo/`m_path`, gate-free `roundRect` path per upstream-ref, `save` unrealized) **not mapped to 14.20**. |
| VC-06 | Impact | **INCONCLUSIVE** | No proven controllable primitive (no pointer read; no observed corruption/leak). |
| VC-07 | Reliability | **PARTIAL** | Strong within-run/internal consistency (e.g., 300-ctx × ops clean); cross-build/session reliability unknown. |
| VC-08 | Version Scope | **PARTIAL** | PS5 14.20 / AppleWebKit 605.1.15 observed; exact WebKit revision/build mapping unknown. |

**Rule applied:** no PASS from “no crash”; no FAIL from “crash” without supported interpretation.

## Item 6 — Recovery / Failed Recovery (review from evidence)
- **Recovery harness works (beacon-observable):** PENDING→reload detection records crashes (`V923C-CRASH`, `V923H-CRASH`, `V923I-LWCRASH`), then stages blacklist/advance (`*-BLACKLIST`, `*-ADV`, `V923C-DONE`, `V923H-DONE`) or pause/stop (V923I `PAUSED`, V923E progress tail). V923G/J/K/L/M progress across reload-safe stage boundaries to `DONE`/`ALREADY`.
- **Failed/limited recovery:** V923E/I **cannot complete** intended scan goals due to 14.20 memory dialog / LWCRASH-per-miss behavior (operational failure, not harness bug proven). V569 scan produced no HIT and post-fault state not beacon-capturable.
- **Conclusion (P0):** recovery *instrumentation* is adequate for JS-level classification; **insufficient for root-cause** without native diagnostics. → needs sign-off (item 6).

## Item 7 — Gaps & contradictions (open)
- **Critical gaps:** 14.20-aligned source (VC-02/03/05/08); native crash diagnostics for V923C/H (VC-04/05). V569 HIT/LEAK absent. V923E incomplete.
- **Contradiction to resolve on 14.20:** upstream `main` `HTMLCanvasElement::getContext` reentrancy appears to block the documented bitmaprenderer-replacement trigger, **but** V923G/J/K/L/M show stale `CTX` usable under 2D reclaim on 14.20 — requires 14.20 lifecycle mapping (alias vs true free). *Not a data contradiction in beacons; a source-vs-observation gap.*
- **No internal beacon contradictions found** in verified extracts (counts/stages/DONE/PAUSE markers consistent).

## P0 decision — **P0 هل مكتمل؟**
- **استخراج/تحقق التجارب (بند 5): نعم، مكتمل** للنطاق المتاح في `host-beacons.log` (كل تجارب V569,V923C/E/G/H/I/J/K/L/M مستخرجة/متحقق تصنيفها ومحفوظة في `results/beacon-logs/p0-2026-11-08/`).
- **P0 كـ Evidence Baseline مُعتمَد (بنود 1–8): لا، غير مكتمل اعتمادًا.** مفتوح: (1) بنود 1–4 غير منطبقة على هذا السياق ما لم يُسلَّم “ملف أصلي JSON/تصدير” محدد؛ (2) بند 6/7/8 تحتاج مراجعة واعتماد؛ (3) فجوات حرجة تمنع إغلاق VC-02/04/05/08 (source 14.20 + crash diagnostics) لكنها **لا تمنع** تجميد baseline الحالي كـ “مشتبه/غير مؤكد”.
- **UAF confirmed?** **No.** Proceed only via gated P2 when blockers supplied (`docs/P2_CONFIRMATION_PLAN.md`). No V925.

## Next (concrete)
1. إن وُجد “ملف أصلي/JSON” مقصود ببنود 1–4: سلّمه (مسار/محتوى) لأستخرج سطوره/أتحقق JSON/أحسب بصمته.
2. اعتمد/علّق على بند 6 (Recovery) وبند 7 (قبول الفجوات كـ open blockers أو توفير مدخلات).
3. عند توفر **14.20 source/diff** أو **crash stack/klog/minidump** (V923C/H): نفّذ P2-T1/T2/T3.

## Host beacon parsing (PROBE_ID) — reanalysis note
- `tools/host.py` parses probe IDs via `/beacon/(?:([A-Za-z]\d+[A-Za-z0-9]*)-)?...` (supports suffix IDs like `V923H`/`V923C`/`V925`). Correct parsing is required for per-probe grouping and accurate reanalysis of `host-beacons.log`/extracts; misparsing can misattribute events in old logs. Verify path-derived IDs match `V###X`. Document/retain any local `PROBE_ID` fix in `tools/host.py` alongside log reanalysis.
