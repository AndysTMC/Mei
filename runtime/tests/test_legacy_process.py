"""The legacy import and key migration with the real tools, on a fully private session.

Private bus, private dconf database (XDG_CONFIG_HOME), a throwaway unlocked gnome-keyring behind a
short private XDG_RUNTIME_DIR (so the real keyring can't be found), and MEI_LEGACY_IMPORT=1.
The test also checks the user's real dconf database is untouched.
"""

import hashlib
from pathlib import Path

import pytest

from private_session import TOOLS_PRESENT, run_private

REAL_DCONF = Path.home() / ".config" / "dconf" / "user"
pytestmark = pytest.mark.skipif(not TOOLS_PRESENT, reason="needs dbus, dconf and gnome-keyring")


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_import_and_key_migration_end_to_end(tmp_path):
    before = digest(REAL_DCONF)
    r, _stderr = run_private("legacy_scenario.py", tmp_path, MEI_LEGACY_IMPORT="1")
    assert digest(REAL_DCONF) == before, "the real dconf database must not change"
    assert r["active"] == "gemini" and r["providers"] == ["gemini", "openrouter"] and r["model"] == "gemini-x"
    assert r["keys_in_keyring"] == {"gemini": "AIza-test-secret", "openrouter": "sk-or-test-secret",
                                    "legacy": "sk-ancient-secret"}
    assert not r["plaintext_left_in_dconf"] and not r["legacy_api_key_left"] and r["non_secret_fields_kept"]
    assert r["imported_messages"] == ["hello", "hi"]
    assert r["second_run_revision_same"] and r["conversation_count_after_restart"] == 1
    assert r["purge"] == {"deleted": 3, "left": 0, "keys_after": []}
