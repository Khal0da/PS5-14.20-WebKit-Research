# Sanitization Report

Generated before publication. Scope: every `.md`, `.html`, `.js`, `.json` and
`.txt` file in this bundle.

## Checks

| Check | Pattern | Result |
|-------|---------|--------|
| IPv4 addresses | `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b` | 0 matches |
| Server domain | project domain literal | 0 matches |
| Home directories | `/home/<user>` | 0 matches |
| Email addresses | `user@host.tld` | 0 matches |
| SSH keys | `ssh-rsa`, `ssh-ed25519`, `BEGIN ... PRIVATE KEY` | 0 matches |
| Credentials | `password`, `passwd`, `passphrase`, `api_key`, `access_token`, `bearer` | 0 matches |
| Absolute server paths | host-specific paths | 0 matches |

## Remaining URLs (all benign)

The only `http://` / `https://` strings left are:

1. `http://www.w3.org/2000/svg` - the standard SVG namespace, required to
   create SVG elements. Not a network destination.
2. Fuzzer input literals: `http://x/...`, `http://base/`, `https://[::1]:...`,
   `http://%zz/`, `blob:http://x/y`. These are malformed strings fed to the URL
   parser as test data; they are never fetched.

## Network behaviour of the probes

Probes post progress to a **relative** path: `/beacon/<TAG>?...`.

Because the path is relative, no host, port or domain is embedded in any file.
The probes work on any origin that serves them; if no beacon endpoint exists,
the requests simply 404 and the on-page result table still shows everything.

## Repository metadata

The local git identity used for the bundle commit is a placeholder
(`PS5 Research <research@example.invalid>`). No personal identity, token or
remote URL is stored in the bundle.
