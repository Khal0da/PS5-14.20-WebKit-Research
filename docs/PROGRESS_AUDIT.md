# Progress Audit

Status of the PS5 14.20 WebKit exploitation research as of November 4, 2026.

## Timeline

| Session | Date | Focus |
|---------|------|-------|
| 1-6 | Oct 15-16 | Bug discovery, stride correction, heap groom, JSString corruption |
| 7-8 | Oct 17 | Extraction attempts, RAB inversion, Relapse testing |
| 9 | Oct 17-18 | Sweep survival testing, MetadataTable declared BLOCKED/DEAD |
| 10 | Oct 18 | Pivot to new surfaces. Font/image recon. 17+ audit agents deployed |
| 11-13 | Oct 18-19 | CSSFontFace UAF (DoS-only), tee() type confusion (contained), WK-1400 audit |
| 14-16 | Oct 19-20 | IsoHeap OFF discovery, CVE-2026-43720 reopened, first reclaim attempts |
| 17-19 | Oct 20-21 | Same-type reclaim V573 CONFIRMED, full R/W via alias V562/V630 |
| 20-21 | Oct 21-22 | Crash oracle development, heap topology mapping V650-V655 |
| 22-23 | Oct 22-23 | Info leak hunting, APNG overread (V674), ASLR defeat work |
| 24 | Nov 2 | On-device beacons: V650 UAF trigger (bmr=OK, getter=true, inner=OK); V592 butterfly harvest (saves=32, cap=37, buf=14800, lwOff=12848, 4x consistent) |
| 25 | Nov 3 | V592 control harness: stage bisection shows the pre-read on freed-unreclaimed memory is the crash; same-type reclaim stable (lw=4.5678 x2); direct AB(768) reclaim crashes; `apng` is `unknown-op`; once-guard reset bug fixed; `reclaimread` read-only diagnostic added |
| 26 | Nov 3 | Session B on-device runs V680-V688: cross-type reclaim all miss, inline/non-Vector first touch crashes, AB(768) confirmed as the slot size class, only `idle`/`gc` survive on an AB-owned slot; V689 canaries deployed |
| 27 | Nov 4 | Results consolidation: V680-V688 matrix added to FINDINGS, 4 new dead ends in DEAD_ENDS, STRATEGY "do not repeat" list, shared probe index (46 links) covering both sessions |
| 28 | Nov 4 | V682 text a=704 all variants dead (ctxhit=1); V700 HTMLParser CE double-parent / microtask bypass dead; V182 font parser loca OOB read dead (px=0/diff=0 all offsets) |
| 29 | Nov 4 | V800 WebAudio recon: AudioContext/OfflineAudioContext unavailable on PS5 14.20; V900 browser capability snapshot: 21 APIs available, 14 unavailable |
| 30 | Nov 4 | V910 MSE basic recon: all edge cases handled safely; V920 CSSFontFaceSet reference_wrapper diagnostic: classic FontFace.prototype.then trigger does not fire, no crash |

## Exploit Chain Progress

| Stage | Status | Notes |
|-------|--------|-------|
| Bug identification | **DONE** | CVE-2026-43720 Canvas getContext() UAF |
| Source audit (WK-1400) | **DONE** | 15+ subsystems, IsoHeap OFF confirmed |
| Device fingerprinting | **DONE** | V399, V520, V521, V580, V583 |
| CVE triage (2023-2026) | **DONE** | 39+ CVEs dead, only CVE-43720 alive |
| UAF trigger | **DONE** | bitmaprenderer outer + defineProperty + 2d inner |
| Same-type reclaim | **DONE** | 500x Canvas2D spray, V573 confirmed |
| Bidirectional R/W via alias | **DONE** | All 12 Canvas2D APIs, V562/V630 |
| Crash oracle | **DONE** | Forge m_stateStack, lineWidth reads 8B at target |
| Heap topology mapping | **DONE** | V650-V655 binary subdivision, ~187KB resolution |
| DAZ bypass | **DONE** | BigUint64Array confirmed for raw pointer handling |
| UAF trigger (V650) | **DONE** | bmr=OK, getter=true, inner=OK on PS5 14.20 |
| Butterfly harvest (V592) | **DONE** | saves=32, cap=37, buf=14800, lwOff=12848 (4x consistent) |
| Info leak / ASLR defeat | **BLOCKED** | All tested paths dead, including V674 APNG overread (`APNGERR load-fail` on PS5 14.20). README claim of 1651 pointers is not reproducible. |
| Arbitrary R/W | Designed | lineDash Vector forge, needs info leak (blocked) |
| Code execution | Not started | vtable hijack or Config overwrite |
| Kernel exploit | BLOCKED | Needs browser code execution first |
| Privilege escalation | Not started | |

## What We Know About the Target

- Firmware 14.10, WebKit-1400 era (Safari 17.0 / AppleWebKit 605.1.15)
- LLInt-only execution (JIT disabled)
- FreeBSD r230171, AMD Zen 2, 16KB pages
- Gigacage disabled (AB shares heap with JSC objects)
- IsoHeap OFF (WTF_MAKE_ISO_ALLOCATED = FastMalloc)
- JSC Config unfrozen (startOfStructureHeap writable)
- MADV_FREE keeps virtual mappings after free
- ~1200MB usable memory before OOM kill
- DAZ ON (denormals flush to zero in float64 channels)
- All Relapse CVEs patched
- All WSA-2026-0003/0004 CVEs dead

## Probe Count

150+ probes across 23 sessions.
