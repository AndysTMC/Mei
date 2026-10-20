# 0005. Keep API keys only in the keyring; the runtime reads them there

Status: accepted
Date: 2026-10-20
Deciders: owner (delegated)
Supersedes: 0001
Superseded-by: —

## Context

0001 kept a plaintext copy of each API key in GSettings (`provider-configs`) because the keyring could be unavailable to the Shell process after a Shell restart, which left every cloud provider without a credential. Since 0002 the Shell no longer calls providers: the runtime, a systemd user service, makes every provider request and needs the key, and the Shell only renders the chat. The plaintext copy is readable by any process in the session through dconf, and it ends up in dconf backups and dotfile syncs.

## Options

- A. Keep 0001: keyring first, plaintext GSettings copy as fallback.
- B. Keyring only. The runtime looks keys up when a turn starts; a locked or missing keyring is an error the user can act on.
- C. Encrypt keys in Mei's own store with a key held in the keyring.

## Decision

B. Keys live only in the Secret Service default collection under the existing schema (`xdg:schema=com.andystmc.mei.provider-api-key`, `extension=mei@andystmc.com`, `provider=<id>`). The preferences window writes them with libsecret, and saving fails visibly when the keyring can't take the key: there is no fallback store. The runtime reads them by provider id (`runtime/src/mei/secrets.py`). It reports a locked keyring as "the keyring is locked. Unlock it, then try again", not as a missing key. Keys never cross Mei's own D-Bus interface or appear in its config, events, or logs.

Migration: on first start against the user's real data, the runtime moves every plaintext key from `provider-configs` (and the old single `api-key`, into slot `legacy`) into the keyring. It reads each one back, and only then scrubs it from dconf and marks the provider `apiKeyStorage: "secret"`. A key that can't be stored or read back stays in dconf and is retried at the next start (`runtime/src/mei/legacy.py`).

## Assumptions

- [A1] The runtime, as a user service in the graphical session, can reach an unlocked default keyring when the user chats. This is GNOME Keyring unlocked at login on the reference distros (revisit if headless or autologin use matters).
- [A2] A clear error on a locked keyring is better than storing the key somewhere weaker.

## Consequences

One copy of each key, in the store designed for it. With autologin and no keyring password, the user may see the locked-keyring error until they unlock it. C (or a key-file fallback) can come later if that proves common. Tests need a real or private keyring: the process test runs gnome-keyring on a private session bus. Do not reintroduce a GSettings copy.

## Revisit if

Mei must run where no Secret Service exists, or users routinely hit a locked keyring during normal use.
