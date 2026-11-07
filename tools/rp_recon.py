#!/usr/bin/env python3
"""V915 - PS5 Remote Play 9295 pre-auth surface recon (differential).

Gentle, well-formed-ish requests with small controlled variations.
Records: status line, RP-Application-Reason, connection behavior.
Run from the dev PC via the Tailscale bridge (192.168.0.102:9295).
"""
import socket
import sys
import time

PS5 = "192.168.0.102"
PORT = 9295
TIMEOUT = 5.0

# chiaki's known reason codes get decoded by the caller afterwards.

def probe(name, payload, read_timeout=4.0):
    """Send raw bytes, return (ok, response_bytes_or_err)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        s.connect((PS5, PORT))
    except Exception as e:
        return name, None, "connect-fail: %s" % e
    try:
        s.sendall(payload)
    except Exception as e:
        s.close()
        return name, None, "send-fail: %s" % e
    data = b""
    try:
        s.settimeout(read_timeout)
        while len(data) < 8192:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    except Exception as e:
        s.close()
        return name, data, "recv-fail: %s" % e
    s.close()
    return name, data, None


def hdr(method, path, extra="", body=None, cl=None, quirk=False):
    """Build a chiaki-style request."""
    req = "%s %s HTTP/1.1\r\n" % (method, path)
    if quirk:
        req += " HTTP/1.1\r\n"
    req += "HOST: 192.168.1.122\r\n"
    req += "User-Agent: remoteplay Windows\r\n"
    req += "Connection: close\r\n"
    if cl is not None:
        req += "Content-Length: %d\r\n" % cl
    if extra:
        req += extra
    req += "\r\n"
    if body:
        req = req.encode("latin-1") + body
        return req
    return req.encode("latin-1")


DUMMY_PAYLOAD = b"A" * 0x400  # chiaki uses 0x1e0 filler + encrypted inner; we send unencrypted filler

PROBES = [
    ("baseline-options",
     b"OPTIONS * RTSP/1.0\r\nCSeq: 1\r\n\r\n"),
    ("options-rpver-9",
     b"OPTIONS * RTSP/1.0\r\nCSeq: 1\r\nRP-Version: 9.0\r\n\r\n"),
    ("options-rpver-12",
     b"OPTIONS * RTSP/1.0\r\nCSeq: 1\r\nRP-Version: 12.0\r\n\r\n"),
    ("describe-rpver",
     b"DESCRIBE rtsp://192.168.0.102/ RTSP/1.0\r\nCSeq: 2\r\nRP-Version: 9.0\r\nUser-Agent: remoteplay Windows\r\n\r\n"),
    ("chiaki-quirk-double-line",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 9.0\r\n", body=DUMMY_PAYLOAD, cl=len(DUMMY_PAYLOAD), quirk=True)),
    ("post-rgst-clean",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 9.0\r\n", body=DUMMY_PAYLOAD, cl=len(DUMMY_PAYLOAD))),
    ("post-rgst-rpver-12",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 12.0\r\n", body=DUMMY_PAYLOAD, cl=len(DUMMY_PAYLOAD))),
    ("post-rgst-no-rpver",
     hdr("POST", "/sie/ps5/rp/sess/rgst", body=DUMMY_PAYLOAD, cl=len(DUMMY_PAYLOAD))),
    ("post-rgst-ps4-path",
     hdr("POST", "/sie/ps4/rp/sess/rgst", "RP-Version: 10.0\r\n", body=DUMMY_PAYLOAD, cl=len(DUMMY_PAYLOAD))),
    ("post-rgst-short-body",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 9.0\r\n", body=b"A" * 16, cl=16)),
    ("post-rgst-cl-large",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 9.0\r\n", body=DUMMY_PAYLOAD, cl=0x10000)),
    ("post-rgst-cl-zero",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 9.0\r\n", body=None, cl=0)),
    ("post-rgst-cl-neg",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 9.0\r\n", body=None, cl=-1)),
    ("post-rgst-long-path",
     hdr("POST", "/sie/ps5/rp/sess/rgst" + "A" * 512, "RP-Version: 9.0\r\n", body=DUMMY_PAYLOAD, cl=len(DUMMY_PAYLOAD))),
    ("post-rgst-long-header",
     hdr("POST", "/sie/ps5/rp/sess/rgst", "RP-Version: 9.0\r\n" + "X-Fuzz: " + "B" * 2048 + "\r\n", body=DUMMY_PAYLOAD, cl=len(DUMMY_PAYLOAD))),
    ("get-root-rpver",
     hdr("GET", "/", "RP-Version: 9.0\r\n")),
    ("setup-session",
     b"SETUP rtsp://192.168.0.102/ RTSP/1.0\r\nCSeq: 3\r\nRP-Version: 9.0\r\nUser-Agent: remoteplay Windows\r\n\r\n"),
]

results = []
for name, payload in PROBES:
    n, data, err = probe(name, payload)
    if err and data is None:
        results.append((name, "ERR", err[:80], 0))
        continue
    # extract status line + reason
    text = data.decode("latin-1", "replace") if data else ""
    status = "?"
    reason = "-"
    if text:
        first = text.split("\r\n")[0] if "\r\n" in text else text[:60]
        status = first.strip()[:60]
        for line in text.split("\r\n"):
            if line.lower().startswith("rp-application-reason"):
                reason = line.split(":", 1)[1].strip()
    results.append((name, status, reason, len(data)))
    time.sleep(0.3)

print("%-28s %-40s %-12s %s" % ("probe", "status", "reason", "bytes"))
print("-" * 100)
for r in results:
    print("%-28s %-40s %-12s %d" % r)
