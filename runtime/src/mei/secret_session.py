"""Encrypted transfer of secrets to and from the Secret Service.

Implements the `dh-ietf1024-sha256-aes128-cbc-pkcs7` session algorithm from the Secret Service API
(the one libsecret and secret-tool use): a Diffie-Hellman exchange over the RFC 2409 1024-bit MODP
group, HKDF-SHA256 to a 128-bit key, then AES-128-CBC with PKCS#7 padding for each secret. It keeps
keys out of anything that records the session bus (a `dbus-monitor` capture pasted into a bug
report); it is not protection from other programs of the same user, which can ask the keyring.
"""

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ALGORITHM = "dh-ietf1024-sha256-aes128-cbc-pkcs7"

# RFC 2409, section 6.2: the Second Oakley Group, which the Secret Service spec names for this algorithm.
PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE65381"
    "FFFFFFFFFFFFFFFF", 16)
GENERATOR = 2
GROUP_BYTES = 128
AES_BLOCK = 16


class KeyExchange:
    """Our half of the Diffie-Hellman exchange for one session."""

    def __init__(self) -> None:
        self._private = int.from_bytes(os.urandom(GROUP_BYTES), "big") % (PRIME - 3) + 2
        self.public = pow(GENERATOR, self._private, PRIME).to_bytes(GROUP_BYTES, "big")

    def session_key(self, peer_public: bytes) -> bytes:
        """The AES key both sides derive. Raises ValueError for a public value outside the group."""
        peer = int.from_bytes(peer_public, "big")
        if not 1 < peer < PRIME - 1:
            raise ValueError("the keyring sent an invalid public key")
        shared = pow(peer, self._private, PRIME).to_bytes(GROUP_BYTES, "big")
        return HKDF(algorithm=hashes.SHA256(), length=AES_BLOCK, salt=None, info=b"").derive(shared)


@dataclass(frozen=True)
class Transport:
    """How secrets are wrapped in one session: AES with `key`, or as they are when key is None
    (a keyring that only offers the "plain" algorithm)."""

    key: bytes | None

    def seal(self, secret: bytes) -> tuple[bytes, bytes]:
        """(parameters, value) for a Secret struct."""
        if self.key is None:
            return b"", secret
        iv = os.urandom(AES_BLOCK)
        padder = padding.PKCS7(AES_BLOCK * 8).padder()
        encryptor = Cipher(algorithms.AES(self.key), modes.CBC(iv)).encryptor()
        return iv, encryptor.update(padder.update(secret) + padder.finalize()) + encryptor.finalize()

    def open(self, parameters: bytes, value: bytes) -> bytes:
        """The secret from a Secret struct. Raises ValueError if it doesn't decrypt."""
        if self.key is None:
            return value
        decryptor = Cipher(algorithms.AES(self.key), modes.CBC(parameters)).decryptor()
        unpadder = padding.PKCS7(AES_BLOCK * 8).unpadder()
        return unpadder.update(decryptor.update(value) + decryptor.finalize()) + unpadder.finalize()
