"""Which paths are off limits, which need a card even to read, and which are too big to change
without asking (§13.2 hard denies, §13.4 sensitive resources).

Each check looks at the path as given and at where its symlinks lead, so a link inside Documents
that points into ~/.ssh is treated as ~/.ssh.
"""

import os
from fnmatch import fnmatch
from pathlib import Path

# Never, from any tool (§13.2): keys, keyrings, browser profiles.
_DENIED_UNDER_HOME = (
    ".ssh", ".gnupg", ".local/share/keyrings", ".password-store", ".pki",
    ".mozilla", ".thunderbird", "snap/firefox", ".config/google-chrome", ".config/chromium",
    ".config/BraveSoftware", ".config/microsoft-edge", ".config/vivaldi", ".config/opera",
    ".var/app/org.mozilla.firefox", ".var/app/org.mozilla.Thunderbird", ".var/app/com.google.Chrome",
    ".var/app/org.chromium.Chromium", ".var/app/com.brave.Browser", ".var/app/com.microsoft.Edge",
)
# Ask every time, even to read: credentials and secrets people keep in ordinary files.
_SENSITIVE_UNDER_HOME = (
    ".aws", ".azure", ".config/gcloud", ".kube", ".docker", ".netrc", ".pgpass", ".git-credentials",
    ".config/gh", ".npmrc", ".pypirc", ".cargo/credentials.toml", ".config/rclone",
)
_SENSITIVE_NAMES = (".env", ".env.*", "*.kdbx", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ecdsa*",
                    "id_ed25519*", "id_dsa*", "*.gpg", "*.asc")
_SENSITIVE_SYSTEM = ("/proc", "/sys", "/etc/ssh", "/root", "/var/lib")
# Writing here makes something run later (at login, in a shell, from the app grid): always ask.
_RUNS_CODE_UNDER_HOME = (
    ".bashrc", ".bash_profile", ".bash_login", ".profile", ".zshrc", ".zprofile", ".zshenv", ".config/fish",
    ".config/autostart", ".config/systemd", ".config/environment.d", ".local/share/applications",
    ".local/share/dbus-1", ".local/share/gnome-shell/extensions", ".local/bin", "bin", ".xprofile", ".xsessionrc",
    ".pam_environment", ".config/gtk-3.0/settings.ini", ".gitconfig", ".ssh/config",
)
# Changing one of these as a whole (not something inside it) always needs a card.
_PROTECTED_UNDER_HOME = ("", ".config", ".local", ".local/share", ".cache", ".var", ".var/app", "snap")


class PathRules:
    def __init__(self, home: Path, user_dirs: dict[str, Path], mei_dirs: list[Path]) -> None:
        self.home = home
        # Each root as written and as it resolves: ~/Downloads may be a link to another drive.
        self._denied = _both([home / p for p in _DENIED_UNDER_HOME] + list(mei_dirs))
        self._sensitive = _both([home / p for p in _SENSITIVE_UNDER_HOME] + [Path(p) for p in _SENSITIVE_SYSTEM])
        self._protected = set(_both([home / p for p in _PROTECTED_UNDER_HOME] + list(user_dirs.values()) + [Path("/")]))
        self._runs_code = _both([home / p for p in _RUNS_CODE_UNDER_HOME])

    def denied(self, path: Path) -> bool:
        return any(inside(p, root) for p in _views(path) for root in self._denied)

    def sensitive(self, path: Path) -> bool:
        return any(inside(p, root) for p in _views(path) for root in self._sensitive) or \
            any(fnmatch(p.name, pattern) for p in _views(path) for pattern in _SENSITIVE_NAMES)

    def runs_code(self, path: Path) -> bool:
        """Is this a place where a written file is later run (shell start-up, autostart, app launchers)?"""
        return any(inside(p, root) for p in _views(path) for root in self._runs_code)

    def protected(self, path: Path) -> bool:
        return any(p in self._protected for p in _views(path))

    def skip_when_walking(self, path: Path) -> bool:
        """Directories a search never enters, whatever it is asked to include."""
        return self.denied(path) or self.sensitive(path)


def inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _both(roots: list[Path]) -> list[Path]:
    return list(dict.fromkeys(v for r in roots for v in _views(r)))


def _views(path: Path) -> list[Path]:
    """The path as written and as resolved (its nearest existing ancestor's real path, plus the rest)."""
    views = [path]
    try:
        real = Path(os.path.realpath(path))
    except (OSError, ValueError):
        return views
    if real != path:
        views.append(real)
    return views
