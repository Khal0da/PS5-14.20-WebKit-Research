# V923/V924 offset verification & small doc corrections (2026-11-07)

This file records a verification pass on an external claim ("fix(canvas) #2 / commit 5022d61 / p635") and the small, safe corrections that follow. **No probe logic was changed. V923/V924 offsets and behavior remain as-is.**

## 1) External claim — not present in this repo

- **Alleged:** commit `5022d61` / PR #195 (ZigZagBoi1) adding p630–p635, claiming 464B State / `lineWidth @ +64`.
- **Checked in this repo (`Khal0da/PS5-14.20-WebKit-Research`):**
  - `git cat-file -t 5022d61` → not a valid object.
  - `git log --all` contains no such commit/PR.
  - `git status` clean w.r.t. `tools/host.py`, `tools/build_standalone.py`, `tools/selftest.js`, `docs/bugs/canvas-getcontext-uaf.md`.
  - No `p635/p652/p653` files exist.
- **Environment mismatch (claim vs. our runs):** claim reports PS5 **14.10** / IP `.37` / port 443; our runs are PS5 **14.20** / IP `.176` / host 8080. PS5 uses **JSC** (not V8).
- **Internal contradiction in the claim:** states "lineWidth actual at State+64" but also summarizes "lineWidth at +48 (State+0x30)".

**Conclusion:** the alleged PR/commit is not in this repo and cannot be confirmed from here. The claim also contains factual/technical errors; treat as unverified external noise.

## 2) `State` size / `lineWidth` offset — device measurements refute 464/+64

Device telemetry (V650, PS5 14.20, **4× consistent**, per `docs/STRATEGY.md`):
- `cap=37, buf=14800, saves=32, lwOff=12848`

| Model | Computation | Result |
|---|---|---|
| **400B / +48 (current)** | `37 × 400 = 14800` ; `32 × 400 + 48 = 12848` | ✅ matches device exactly |
| **464B / +64 (claim)** | `37 × 464 = 17168` ; `32 × 464 + 64 = 14912` | ❌ does not match |

Two independent measurements pin **`sizeof(State)=400`** and **`lineWidth @ State+48`**. **Do not change V923/V924 offsets.**

## 3) Correct `WTF::Vector` field order (small, real correction)

`WTF::Vector` / `VectorBufferBase` layout (relevant tail):
- `+112` — `m_buffer` (pointer)
- `+120` — **`m_capacity`** (u32/bitfield storage)
- `+124` — **`m_size`**

Several comments/docs in this repo label `+120/+124` in the opposite order (e.g. `docs/bugs/canvas-getcontext-uaf.md:127`, comments in V923/V924/V665).

**Impact on V923/V924 (current):** **harmless** — the forge writes the same value `k=1` to both `v[30]` (+120) and `v[31]` (+124), so read behavior is unchanged.
**Future impact:** any forge that sets `size != capacity` (e.g. `setLineDash` in-place when `capacity >= N`) **must** use the correct order: `+120 = capacity`, `+124 = size`. Getting this backwards risks an unintended OOB write.

Recommended follow-up (comments/docs only, no logic change):
- Fix label swap in `v923-roundrect-leak.html` / `v924-moveTo-leak.html` comments (`v[30]=capacity`, `v[31]=size`).
- Fix `docs/bugs/canvas-getcontext-uaf.md:127` ordering.
- Keep V923/V924 runtime values as-is until a size!=capacity forge is actually needed.

## 4) Fabricated fix citation in docs

`docs/bugs/canvas-getcontext-uaf.md:5` cites `2693828e8d73` as the Canvas fix — this commit is (per prior verification in-project notes) a YARR regex JIT fix, unrelated to Canvas. Treat that citation as fabricated/misleading and replace with the correct CVE-2026-43720 fix reference when confirmed from a primary source.

## 5) Summary

| Item | Verdict | Action |
|---|---|---|
| Alleged PR/commit/files | ❌ not in repo / unverified | ignore |
| `State=464 / lineWidth=+64` | ❌ refuted by device (400/+48) | **no change** to V923/V924 |
| `Vector` `+120/+124` labels | ⚠️ labels swapped in comments/docs | fix labels/comments only; values OK today |
| Canvas fix commit citation (doc:5) | ⚠️ likely fabricated | correct with primary source |

**Bottom line:** V923/V924 remain correct for the current read/forge shape. The only real correction is the `m_capacity/m_size` *labeling* and the doc citation — keep those in a separate, reviewable change.