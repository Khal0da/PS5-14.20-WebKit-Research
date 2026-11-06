# Publication Scope

This folder is the sanitized public subset of the research workspace.

## Included

- Documentation: findings, dead ends, strategy, research map, progress audit,
  capability snapshot, and the Canvas UAF write-up.
- Diagnostic probes:
  - `probes/index.html` - menu
  - `probes/v2000-all-in-one.html` - 23-test battery
  - `probes/v1000-smil-fuzz.html` - SVG SMIL lifecycle fuzzer
  - `probes/v1001-imagebitmap-fuzz.html` - ImageBitmap lifecycle fuzzer
  - `probes/feature-detect.html` - capability snapshot

## Excluded

- Any operational exploit chain, ROP builder, pointer forging, or payload.
- Kernel payloads, ELF binaries, and firmware offset tables.
- Third-party exploit copies and re-hosted archives.
- Raw server logs, credentials, and network identifiers.
- Scratch transcripts and dispatch notes.

## Sanitization

Before publication:

- LAN addresses replaced with `the-console`.
- Beacon log filenames replaced with `beacon log`.
- Server domain replaced with `example.invalid`.
- Credentials and host keys removed.
- Probes use relative `/beacon/...` paths only, so no host is embedded.

A final scan for addresses, domains, credentials, and key material returns
no matches.

## Why the exploit code is excluded

The purpose of this repository is to document the *research path* and make the
negative results reproducible. Publishing a half-working exploit chain would:

1. spread unverified claims that cannot be reproduced on retail 14.20;
2. mix diagnostic probes with weaponized code, making both harder to audit;
3. imply a capability that does not exist (there is no info leak yet).

The diagnostics are enough to reproduce every claim in the documentation.
