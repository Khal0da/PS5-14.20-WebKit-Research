# Network Access & Console Surfaces

Established 2026-11-06. How we reach the PS5 from the dev environment, and what is
listening on the console itself.

## Topology (verified)

```
Dev PC (albetaar1)          Tailscale            Home PC (upturn-uds)      LAN           PS5
192.168.1.122 (srv LAN)  <-  100.x mesh  ->   100.114.95.12 (tailscale)  ---->   192.168.0.102
100.121.197.121 (ts)                              192.168.0.x (home LAN)          (14.20, browser)
```

- Both networks are bridged via Tailscale. Subnet route `192.168.0.0/24` is
  advertised by `upturn-uds` and approved in the Tailscale admin console
  (route visible in `route print -4` on the dev PC: `192.168.0.0 ... 100.121.197.121`).
- The research server (192.168.1.54, Zoraxy at .176, tunnel `ps5.mutaqan.com`) is on
  the dev PC's LAN, NOT the console's LAN. Browser probes still go through the tunnel;
  console-side probing goes through the Tailscale bridge.

## Console port scan (2026-11-06, from dev PC via bridge)

Target `192.168.0.102`, TCP connect scan, 29 ports:

| Ports | Result |
|-------|--------|
| 80, 443, 85, 987, 1337, 2121, 3074, 3659, 9020-9027, 9222, 9229, 9293, 9296, 9297, 52235-52237, 9911, 9912, 10050, 10051 | closed |
| **9295** | **OPEN — Remote Play RTSP** |

- Loader ports (9020-9027) and WebKit inspector (9222/9229) closed, as expected:
  `src/loader.js` requires WebKit userland ARW+ROP to start its 9027 listener, and
  we do not have ARW on 14.20. The loader path is armed but blocked at Stage 2.
- ICMP ping is blocked by the console; TCP scanning works.

## 9295 — Remote Play RTSP (pre-auth parser reachable)

Banner grab (any method — OPTIONS/DESCRIBE/GET — same response):

```
HTTP/1.1 403 Forbidden
Connection: close
Pragma: no-cache
Content-Length: 0
RP-Version: 1.0
RP-Application-Reason: 80108bff
```

- `RP-Version: 1.0`, reason `0x80108bff` = unregistered/unauthorized device.
- The server **parses arbitrary requests pre-auth** (responds to anything) — this is
  Sony's `remote_play` daemon, a non-WebKit Stage-1 surface reachable from the LAN.
- Protocol reference: chiaki (open-source PS5 Remote Play client) documents the
  RTSP + regist handshake; PS5 regist requires a PSN token since FW 7.0+.
- A pre-auth parsing bug here would be a browser-independent entry point. Crashes
  in this daemon are console-side (UI error), independent of WebProcess reloads.

## V915 recon round 1 (2026-11-07, tools/rp_recon.py via bridge)

## V915b recon round 2 (2026-11-08, tools/rp_recon_v2.py from dev PC via Tailscale)
**Result: flat pre-auth wall confirmed (0 DIFFs).** 24 cautious, rate-limited variations
(SETUP+Transport/Session, ANNOUNCE, CSeq extremes, duplicate headers, method/version
variants, RTSP spacing, 20 headers, 256-char hdr name, 512-char value, CL mismatch,
Content-Type, absolute/query/fragment URI, NUL-in-path, bare LF) all returned identical
`HTTP/1.1 403 Forbidden / RP-Application-Reason 80108bff` (132 bytes). No differential
parser signal and no stalls observed at these bounded sizes. **Conclusion:** pre-auth
9295 offers no actionable unauthenticated differential surface from this recon; deeper
parsing remains gated on legitimate registration (PSN + Link Device/PIN).

**TCP 9295 - flat pre-auth wall.** 17 differential probes (OPTIONS/DESCRIBE/GET/SETUP/POST,
paths /sie/ps5/rp/sess/rgst + /sie/ps4/... + long path, RP-Version absent/9.0/12.0,
Content-Length 0/-1/16/0x400/0x10000, chiaki double-request-line quirk, 2KB header,
chiaki User-Agent): **every one returns the identical 132-byte 403 / RP-Application-Reason
80108bff**. No differential parser signal pre-auth; the console rejects unregistered
clients before meaningful parsing.

**One transient signal:** the 2KB-header probe was followed by a connect-timeout on the
next connection (recovered within seconds, daemon alive - rate limit / accept-queue stall,
not a crash).

**UDP 9295 (discovery):** SRC3/SRC2 (exact, junk-suffixed), empty, HTTP, 2KB, random magic
- all silent. chiaki documents the console only answers SRC3 while the Link Device screen
(open with PIN) is up.

**Chiaki protocol facts (lib/src/regist.c):** local registration = UDP SRC3 search ->
TCP POST /sie/ps5/rp/sess/rgst (User-Agent: remoteplay Windows, RP-Version, 0x400-byte
payload: 0x1e0 filler + PIN-derived encrypted inner headers with Client-Type/Np-AccountId).
Reason 80108bff = unregistered/unauthorized. Deep parsing (RTSP session, control stream)
only happens for registered devices.

**Gate:** this thread's depth requires a legitimate registration (own console + own PSN
account, console in Link Device mode). Post-registration surface: RTSP session negotiation,
control protocol, stream handlers - larger, and where chiaki compatibility work keeps
finding issues.

## Re-run the scan

```sh
python - <<'EOF'
import socket, concurrent.futures
PS5='192.168.0.102'
PORTS=[80,443,85,987,1337,2121,3074,3659,9020,9021,9022,9023,9024,9025,9026,9027,9222,9229,9293,9295,9296,9297,52235,52236,52237,9911,9912,10050,10051]
def check(p):
    s=socket.socket(); s.settimeout(1.5)
    try: s.connect((PS5,p)); return p, True
    except Exception: return p, False
    finally: s.close()
with concurrent.futures.ThreadPoolExecutor(28) as ex: r=list(ex.map(check,PORTS))
print('OPEN :', [p for p,ok in r if ok] or 'NONE')
EOF
```
