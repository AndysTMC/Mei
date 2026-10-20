# 0006. API keys cross the bus encrypted, go only to configured endpoints, and never come back in errors

Status: accepted
Date: 2026-10-21
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

0005 keeps keys only in the keyring, with the runtime reading them at the start of each turn. Two reviews of Stage 2a found three ways a key could still leave that path:

- The runtime opened Secret Service sessions with the `plain` algorithm, so every read put the key on the session bus unencrypted. Anything recording the bus captured it, including a `dbus-monitor` log pasted into a bug report.
- `ListModels` attached a provider's stored key to a URL supplied by the caller. Any local process could ask Mei to send the user's key to a host of its choosing, a confused deputy (§13.7).
- Some upstreams repeat the key in error messages, both in HTTP error bodies and in error frames inside a successful stream. That text became the task's error, which is stored and sent to the UI.

## Options

- Transfer: keep `plain`; implement `dh-ietf1024-sha256-aes128-cbc-pkcs7` (what libsecret and secret-tool use), which needs AES; or read keys through libsecret via PyGObject, which the uv-managed Python doesn't have.
- Endpoint: authorize callers by process; or bind a stored key to endpoints the user configured.
- Errors: rely on pattern redaction; or remove the exact key value from every provider error.

## Decision

- **Encrypted transfer.** The runtime negotiates `dh-ietf1024-sha256-aes128-cbc-pkcs7` (`runtime/src/mei/secret_session.py`), using the `cryptography` package for AES and HKDF. It falls back to `plain` with a warning only if the keyring doesn't offer that algorithm, as libsecret does. The preferences window already uses libsecret, which negotiates the same algorithm.
- **Keys go only where settings send them.** A stored key is sent only to the provider's built-in endpoint or the endpoint saved in its settings (`models.credential_allowed`). Any other URL gets a "save this endpoint first" error. Changing the saved endpoint is a config change that every client sees.
- **Errors never carry the key.** The factory wraps every adapter in `KeyScrubbing`, which removes the exact key value from any provider error. Pattern redaction stays on top of that for keys Mei didn't send.

## Assumptions

- [A1] Same-user malware stays out of scope (§5): it can ask the keyring directly. These measures stop accidental disclosure and casual misuse by other local processes.
- [A2] Every keyring Mei supports offers the DH algorithm. GNOME Keyring does.

## Consequences

The runtime now depends on `cryptography`, a large native package with prebuilt wheels everywhere uv installs Mei. `test_key_privacy.py` monitors the whole private bus with a real gnome-keyring. It asserts the key appears in no message at all, not even in keyring traffic. It covers a key echoed in an HTTP error and inside a stream, and a `ListModels` call aimed at another origin. The test fails if the transfer falls back to `plain`.

## Revisit if

The Secret Service gains a newer transfer algorithm, Mei needs a keyring without DH support, or Mei adds a feature that sends credentials anywhere new (tools, MCP servers). Such a feature must follow the same rule.
