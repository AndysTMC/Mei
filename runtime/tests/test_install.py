"""Per-user install and uninstall against a fake host and temporary XDG directories."""

import json
from pathlib import Path

import pytest

from mei import install
from mei.install import Paths, format_strv, parse_strv
from mei.protocol import EXTENSION_UUID as UUID


class FakeHost(install.Host):
    def __init__(self, enabled="['other@x.org']", disabled="@as []", user_off="false", shell_has=False):
        self.settings = {"enabled-extensions": enabled, "disabled-extensions": disabled,
                         "disable-user-extensions": user_off}
        self.calls: list[tuple] = []
        self.shell_has = shell_has
        self.keys = (2, 0)
        self.systemd_ok = True
        self.gsettings_broken = False

    def gsettings_get(self, schema, key):
        assert schema == "org.gnome.shell"
        if self.gsettings_broken:
            raise FileNotFoundError("/usr/bin/gsettings")
        return self.settings[key]

    def gsettings_set(self, schema, key, value):
        self.settings[key] = value

    def dconf_reset_dir(self, path):
        self.calls.append(("dconf-reset", path))

    def systemctl(self, *args):
        self.calls.append(("systemctl", *args))
        return True

    def reload_buses(self):
        self.calls.append(("reload",))
        return self.systemd_ok

    def shell_has_extension(self):
        return self.shell_has

    def delete_keys(self):
        self.calls.append(("delete-keys",))
        return self.keys


@pytest.fixture
def env(tmp_path):
    ext = tmp_path / "built"
    (ext / "schemas").mkdir(parents=True)
    (ext / "metadata.json").write_text(json.dumps({"uuid": UUID}))
    (ext / "extension.js").write_text("// v1")
    (ext / "schemas/gschemas.compiled").write_bytes(b"\x00GVariant")
    p = Paths(unit=tmp_path / "config/systemd/user/mei-runtime.service",
              dbus_service=tmp_path / "data/dbus-1/services/com.andystmc.Mei1.service",
              extensions=tmp_path / "data/gnome-shell/extensions", data=tmp_path / "data/mei")
    return ext, p


def test_strv_round_trip():
    assert parse_strv("@as []") == []
    assert parse_strv("['a@x.org', 'b@y.org']") == ["a@x.org", "b@y.org"]
    assert parse_strv("[\"it's\", 'back\\\\slash']") == ["it's", "back\\slash"]
    for values in ([], ["a"], ["it's", "x, y"]):
        assert parse_strv(format_strv(values)) == values
    with pytest.raises(ValueError):
        parse_strv("'not a list'")


def test_first_install_writes_everything_and_asks_for_a_log_out(env):
    ext, p = env
    host = FakeHost(disabled=f"['{UUID}']")
    r = install.install(host, extension=ext, python="/opt/venv/bin/python", p=p)
    assert not r.notes and not r.errors and r.log_out
    assert "ExecStart=/opt/venv/bin/python -m mei serve" in p.unit.read_text()
    assert "SystemdService=mei-runtime.service" in p.dbus_service.read_text()
    assert (p.extension / "extension.js").read_text() == "// v1"
    assert (p.extension / "schemas/gschemas.compiled").is_file()
    assert parse_strv(host.settings["enabled-extensions"]) == ["other@x.org", UUID]
    assert parse_strv(host.settings["disabled-extensions"]) == []
    assert ("systemctl", "try-restart", "mei-runtime.service") in host.calls
    # Nothing staged is left where the Shell would try to load it.
    assert [d.name for d in p.extensions.iterdir()] == [UUID]
    assert not list(p.extensions.parent.glob(".mei-extension.*"))


def test_rerun_is_a_quiet_no_op_once_the_shell_has_loaded_it(env):
    ext, p = env
    install.install(FakeHost(), extension=ext, p=p)
    host = FakeHost(enabled=f"['other@x.org', '{UUID}']", shell_has=True)
    r = install.install(host, extension=ext, p=p)
    assert r.lines == [] and not r.notes and not r.log_out
    assert parse_strv(host.settings["enabled-extensions"]) == ["other@x.org", UUID]


def test_rerun_before_logging_in_still_asks_for_the_log_out(env):
    ext, p = env
    install.install(FakeHost(), extension=ext, p=p)
    r = install.install(FakeHost(enabled=f"['{UUID}']", shell_has=False), extension=ext, p=p)
    assert r.log_out


def test_upgrade_replaces_changed_extension_files(env):
    ext, p = env
    install.install(FakeHost(), extension=ext, p=p)
    (p.extension / "stale.js").write_text("left over")
    (ext / "extension.js").write_text("// v2")
    r = install.install(FakeHost(enabled=f"['{UUID}']", shell_has=True), extension=ext, p=p)
    assert r.log_out
    assert (p.extension / "extension.js").read_text() == "// v2"
    assert not (p.extension / "stale.js").exists()


def test_a_development_symlink_is_left_alone_unless_forced(env, tmp_path):
    ext, p = env
    checkout = tmp_path / "checkout-dist"
    checkout.mkdir()
    (checkout / "metadata.json").write_text("{}")
    p.extensions.mkdir(parents=True)
    p.extension.symlink_to(checkout)

    r = install.install(FakeHost(), extension=ext, p=p)
    assert p.extension.is_symlink() and any("symlink" in x for x in r.notes)

    r = install.install(FakeHost(), extension=ext, force=True, p=p)
    assert not p.extension.is_symlink() and (p.extension / "extension.js").is_file()
    assert (checkout / "metadata.json").read_text() == "{}"  # the checkout is untouched


def test_user_extensions_switched_off_is_reported(env):
    ext, p = env
    r = install.install(FakeHost(user_off="true"), extension=ext, p=p)
    assert any("Extensions are switched off" in x for x in r.notes)


def test_missing_bundle_is_a_clear_error(env, tmp_path):
    _ext, p = env
    r = install.install(FakeHost(), extension=tmp_path / "nothing", p=p)
    assert r.errors and not p.unit.exists()


def test_a_failing_system_tool_is_an_error_not_a_crash(env):
    ext, p = env
    host = FakeHost()
    host.gsettings_broken = True
    r = install.install(host, extension=ext, p=p)
    assert r.errors and "enabled extensions" in r.errors[0]
    assert p.unit.exists() and (p.extension / "extension.js").exists()  # the steps before it stand
    r = install.uninstall(host, p=p)
    assert r.errors and not p.unit.exists() and not p.extension.exists()


def test_systemd_not_reloading_is_reported(env):
    ext, p = env
    host = FakeHost()
    host.systemd_ok = False
    r = install.install(host, extension=ext, p=p)
    assert not r.errors and any("next login" in n for n in r.notes)


def test_a_failed_swap_puts_the_old_extension_back(env, monkeypatch):
    ext, p = env
    install.install(FakeHost(), extension=ext, p=p)
    (ext / "extension.js").write_text("// v2")
    real_rename = Path.rename

    def rename(self, target):
        if self.name == ".mei-extension.new":
            raise OSError("disk full")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    r = install.install(FakeHost(enabled=f"['{UUID}']", shell_has=True), extension=ext, p=p)
    assert r.errors and "disk full" in r.errors[0]
    assert (p.extension / "extension.js").read_text() == "// v1"


def test_uninstall_keeps_data_unless_purged(env):
    ext, p = env
    install.install(FakeHost(), extension=ext, p=p)
    p.data.mkdir(parents=True)
    (p.data / "mei.db").write_text("x")
    host = FakeHost(enabled=f"['other@x.org', '{UUID}']")
    r = install.uninstall(host, p=p)
    assert not p.unit.exists() and not p.dbus_service.exists() and not p.extension.exists()
    assert parse_strv(host.settings["enabled-extensions"]) == ["other@x.org"]
    assert (p.data / "mei.db").exists() and ("delete-keys",) not in host.calls
    assert any("--purge" in line for line in r.lines)

    host = FakeHost()
    host.keys = (1, 1)
    r = install.uninstall(host, purge=True, p=p)
    assert not p.data.exists()
    assert ("dconf-reset", "/org/gnome/shell/extensions/mei/") in host.calls
    assert any("locked" in x for x in r.notes)


def test_uninstall_removes_only_the_link_of_a_development_install(env, tmp_path):
    _ext, p = env
    checkout = tmp_path / "checkout-dist"
    checkout.mkdir()
    (checkout / "extension.js").write_text("dev")
    p.extensions.mkdir(parents=True)
    p.extension.symlink_to(checkout)
    install.uninstall(FakeHost(), p=p)
    assert not p.extension.exists() and (checkout / "extension.js").read_text() == "dev"


def test_bundled_extension_is_absent_in_a_source_checkout():
    # scripts/build-release.sh copies it in only while building the wheel.
    assert install.bundled_extension() is None
    assert install.paths().extension.name == UUID
