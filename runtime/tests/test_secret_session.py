"""The Secret Service transport encryption, against a simulated keyring side (no bus needed).
The real gnome-keyring is exercised by the process tests (test_legacy_process, test_key_privacy)."""

import pytest

from mei.secret_session import GROUP_BYTES, PRIME, KeyExchange, Transport


def test_the_group_is_rfc_2409_second_oakley():
    assert PRIME.bit_length() == 1024 and PRIME % 2 == 1
    assert hex(PRIME).startswith("0xffffffffffffffffc90fdaa22168c234") and hex(PRIME).endswith("ffffffffffffffff")


def test_both_sides_derive_the_same_key_and_secrets_round_trip():
    ours, keyring = KeyExchange(), KeyExchange()
    assert len(ours.public) == GROUP_BYTES
    key = ours.session_key(keyring.public)
    assert key == keyring.session_key(ours.public) and len(key) == 16
    transport = Transport(key)
    for secret in (b"", b"k", b"sk-" + b"x" * 15, b"\xf0\x9f\x8c\xb8 unicode", b"y" * 100):
        params, sealed = transport.seal(secret)
        assert len(params) == 16 and len(sealed) % 16 == 0
        if len(secret) >= 8:  # a shorter one turns up in random ciphertext by chance (b"k": ~6% of runs)
            assert secret not in sealed
        assert transport.open(params, sealed) == secret
    assert transport.seal(b"same")[1] != transport.seal(b"same")[1]  # a fresh IV each time


def test_a_bad_public_value_or_tampered_secret_is_refused():
    ours = KeyExchange()
    for bad in (b"\x00", b"\x01", (PRIME - 1).to_bytes(GROUP_BYTES, "big"), PRIME.to_bytes(GROUP_BYTES, "big")):
        with pytest.raises(ValueError):
            ours.session_key(bad)
    transport = Transport(ours.session_key(KeyExchange().public))
    params, sealed = transport.seal(b"secret")
    with pytest.raises(ValueError):
        Transport(bytes(16)).open(params, sealed)  # the wrong key: padding check fails


def test_plain_sessions_pass_secrets_through():
    assert Transport(None).seal(b"k") == (b"", b"k")
    assert Transport(None).open(b"", b"k") == b"k"
