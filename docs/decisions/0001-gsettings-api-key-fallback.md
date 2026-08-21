# 0001. Keep a GSettings copy of API keys stored in libsecret

Status: accepted
Date: 2026-08-22
Deciders: existing project
Supersedes: —
Superseded-by: —

## Context

Cloud providers need an API key at request time. The desktop Secret Service (libsecret) is the right store, but it can succeed while the preferences window saves a key and then be unavailable after a GNOME Shell restart. If the only copy lives in the keyring, every cloud provider is recreated with an empty credential.

## Options

- A. Store keys only in libsecret.
- B. Store keys only in GSettings (`provider-configs`).
- C. Prefer libsecret, keep a GSettings copy as fallback.

## Decision

We will prefer libsecret (`com.andystmc.mei.provider-api-key`) and still keep the key in GSettings when the keyring write succeeds (`src/providers/apiKeys.ts`). If libsecret is missing or fails, store plaintext in GSettings and log that fallback.

## Assumptions

- [A1] Secret Service can disappear across Shell restarts on the desktops Mei targets (revisit if a reliable always-on keyring is guaranteed).
- [A2] GSettings on the user session is an acceptable fallback for a local desktop secret (revisit if Mei is no longer single-user / same-machine).

## Consequences

Keys may exist in two places. GSettings remains sensitive. Gemini keys still go in the `x-goog-api-key` header, not the URL. Do not "fix" this by dropping the GSettings copy.

## Revisit if

libsecret stays available across Shell restarts in the environments we support, or Mei gains a multi-user or remote threat model that forbids GSettings secrets.
