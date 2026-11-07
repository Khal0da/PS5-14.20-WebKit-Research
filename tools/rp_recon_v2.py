#!/usr/bin/env python3
"""V915b - PS5 Remote Play 9295 pre-auth differential recon (cautious).
Extends rp_recon.py with small, rate-limited parser-variation probes.
Run from dev PC via Tailscale bridge (192.168.0.102:9295). Non-destructive intent.
"""
import socket, time

PS5 = "192.168.0.102"
PORT = 9295
TIMEOUT = 5.0
DELAY = 0.8  # cautious pacing (V915 saw transient stall on 2KB header)

def probe(name, payload, read_timeout=4.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        s.connect((PS5, PORT))
    except Exception as e:
        return name, None, "connect-fail: %s" % e
    try:
        s.sendall(payload)
    except Exception as e:
        try: s.close()
        except Exception: pass
        return name, None, "send-fail: %s" % e
    data = b""
    try:
        s.settimeout(read_timeout)
        while len(data) < 8192:
            chunk = s.recv(4096)
            if not chunk: break
            data += chunk
    except socket.timeout:
        pass
    except Exception as e:
        try: s.close()
        except Exception: pass
        return name, data, "recv-fail: %s" % e
    try: s.close()
    except Exception: pass
    return name, data, None

def base(method, path, headers="", body=b""):
    h = "%s %s RTSP/1.0\r\nHOST: 192.168.1.122\r\nUser-Agent: remoteplay Windows\r\nConnection: close\r\n" % (method, path)
    if body is not None and "Content-Length" not in headers:
        h += "Content-Length: %d\r\n" % len(body)
    h += headers + "\r\n"
    return h.encode("latin-1") + (body or b"")

D = b"A" * 0x40
# Bounded, non-destructive variations (sizes kept < 1024)
PROBES = [
    ("setup-transport-udp", base("SETUP","rtsp://192.168.0.102/","CSeq: 1\r\nRP-Version: 9.0\r\nTransport: RTP/AVP/UDP;unicast;client_port=9296-9297\r\n")),
    ("setup-transport-tcp", base("SETUP","rtsp://192.168.0.102/","CSeq: 1\r\nRP-Version: 9.0\r\nTransport: RTP/AVP/TCP;interleaved=0-1\r\n")),
    ("setup-session-hdr", base("SETUP","rtsp://192.168.0.102/","CSeq: 1\r\nRP-Version: 9.0\r\nSession: 12345678\r\n")),
    ("announce-rpver", base("ANNOUNCE","rtsp://192.168.0.102/","CSeq: 1\r\nRP-Version: 9.0\r\nContent-Type: application/sdp\r\n", b"v=0\r\n")),
    ("cseq-maxint", base("OPTIONS","*","CSeq: 2147483647\r\nRP-Version: 9.0\r\n")),
    ("cseq-zero", base("OPTIONS","*","CSeq: 0\r\nRP-Version: 9.0\r\n")),
    ("cseq-neg", base("OPTIONS","*","CSeq: -1\r\nRP-Version: 9.0\r\n")),
    ("dup-rpver", base("OPTIONS","*","RP-Version: 9.0\r\nRP-Version: 12.0\r\n")),
    ("dup-cl", ("OPTIONS * RTSP/1.0\r\nHOST: 192.168.1.122\r\nConnection: close\r\nContent-Length: 0\r\nContent-Length: 4\r\n\r\n").encode()),
    ("method-lower", base("options","*","CSeq: 1\r\n")),
    ("unknown-method", base("PLAYX","*","CSeq: 1\r\nRP-Version: 9.0\r\n")),
    ("http10-ver", b"OPTIONS * HTTP/1.0\r\nCSeq: 1\r\nRP-Version: 9.0\r\nConnection: close\r\n\r\n"),
    ("rtsp10-spaces", b"OPTIONS  *  RTSP/1.0\r\nCSeq: 1\r\nRP-Version: 9.0\r\nConnection: close\r\n\r\n"),
    ("many-headers-20", base("OPTIONS","*","RP-Version: 9.0\r\n" + "".join("X-H%d: v\r\n" % i for i in range(20)))),
    ("hdrname-long-256", base("OPTIONS","*","RP-Version: 9.0\r\n" + ("X" * 256) + ": v\r\n")),
    ("hdrval-long-512", base("OPTIONS","*","RP-Version: 9.0\r\nX-V: " + ("B" * 512) + "\r\n")),
    ("cl-mismatch-over", ("POST /sie/ps5/rp/sess/rgst RTSP/1.0\r\nHOST: 192.168.1.122\r\nRP-Version: 9.0\r\nConnection: close\r\nContent-Length: 8\r\n\r\nAA").encode()),
    ("post-ctype-sdp", base("POST","/sie/ps5/rp/sess/rgst","RP-Version: 9.0\r\nContent-Type: application/sdp\r\n", D)),
    ("post-ctype-octet", base("POST","/sie/ps5/rp/sess/rgst","RP-Version: 9.0\r\nContent-Type: application/octet-stream\r\n", D)),
    ("uri-absolute", base("OPTIONS","rtsp://192.168.0.102:9295/sie/ps5/rp/sess/rgst","RP-Version: 9.0\r\n")),
    ("uri-query", base("OPTIONS","/sie/ps5/rp/sess/rgst?x=1&y=2","RP-Version: 9.0\r\n")),
    ("uri-fragment", base("OPTIONS","/sie/ps5/rp/sess/rgst#frag","RP-Version: 9.0\r\n")),
    ("null-in-path", b"OPTIONS /sie/ps5/\x00rp/sess RTSP/1.0\r\nCSeq: 1\r\nRP-Version: 9.0\r\nConnection: close\r\n\r\n"),
    ("bare-lf", b"OPTIONS * RTSP/1.0\nCSeq: 1\nRP-Version: 9.0\nConnection: close\n\n"),
]

results = []
for name, payload in PROBES:
    n, data, err = probe(name, payload)
    if err and data is None:
        results.append((name, "ERR", err[:90], 0, ""))
        time.sleep(DELAY); continue
    text = data.decode("latin-1", "replace") if data else ""
    status = text.split("\r\n")[0].strip()[:70] if text else ("(empty)" if data == b"" else "?")
    reason = "-"
    for line in text.split("\r\n"):
        if line.lower().startswith("rp-application-reason"): reason = line.split(":",1)[1].strip(); break
    diff = ""
    if status != "HTTP/1.1 403 Forbidden" or reason != "80108bff":
        diff = "DIFF"
    results.append((name, status[:50], reason, len(data), diff))
    time.sleep(DELAY)

print("%-22s %-50s %-10s %5s %s" % ("probe","status","reason","bytes","flag"))
print("-"*105)
for r in results:
    print("%-22s %-50s %-10s %5d %s" % r)
diffs = [r for r in results if r[4]=="DIFF" or r[1]=="ERR" or "fail" in r[1].lower()]
print("\nDIFFS/ERRS:", len(diffs))
for r in diffs: print(" ", r)
