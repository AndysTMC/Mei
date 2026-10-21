"""The desktop ports and the capabilities on them, against the real tools where that's safe:
GSettings through a private keyfile backend, pdftotext in its sandbox. Apps are never launched."""

import os
from pathlib import Path

import pytest

from mei import paths
from mei.capabilities.apps import AppsLaunch, AppsList, LaunchParams, ListParams
from mei.capabilities.base import ActionContext, App, CapabilityError, Window
from mei.capabilities.settings import GetParams, SetParams, SettingsGet, SettingsSet
from mei.capabilities.sound import SetVolumeParams, SoundSetVolume
from mei.desktop import apps as desktop_apps
from mei.desktop.gsettings import GSETTINGS, GSettingsCli
from mei.desktop.pdf import PdfToText
from mei.ipc.peers import is_shell_executable

from agent_harness import make_world, put

FIXTURES = Path(__file__).parent / "fixtures"
needs_gsettings = pytest.mark.skipif(not os.access(GSETTINGS, os.X_OK), reason="needs /usr/bin/gsettings")


@pytest.fixture
def env(tmp_path):
    return make_world(tmp_path)


@pytest.fixture
def private_gsettings(tmp_path):
    return GSettingsCli(env={"GSETTINGS_BACKEND": "keyfile", "XDG_CONFIG_HOME": str(tmp_path / "config")})


# ── Settings ────────────────────────────────────────────────────────────────


@needs_gsettings
async def test_settings_set_records_the_old_value_and_reads_back(env, private_gsettings):
    env.gsettings = private_gsettings
    before = await private_gsettings.get("org.gnome.desktop.interface", "color-scheme")  # distros set their own default
    wanted = "prefer-light" if before == "'prefer-dark'" else "prefer-dark"
    cap, p = SettingsSet(), SetParams(schema="org.gnome.desktop.interface", key="color-scheme", value=wanted)
    assert cap.resources(p, env)[0].aliases[0] == "dark mode"
    r = await cap.run(p, ActionContext(env, "a1"))
    assert r.undo["old"] == before and r.undo["new"] == f"'{wanted}'"
    assert (await cap.verify(p, r, ActionContext(env, "a1"))).status == "passed"
    got = await SettingsGet().run(GetParams(schema="org.gnome.desktop.interface", key="color-scheme"),
                                  ActionContext(env, "a2"))
    assert got.observation.endswith(f"'{wanted}'")


@needs_gsettings
@pytest.mark.parametrize("key,value,message", [
    ("color-scheme", "very-dark", "must be one of default, prefer-dark, prefer-light"),
    ("text-scaling-factor", "9", "between 0.5 and 3.0"),
    ("enable-animations", "maybe", "true or false"),
])
async def test_settings_set_explains_values_that_dont_fit(env, private_gsettings, key, value, message):
    env.gsettings = private_gsettings
    with pytest.raises(CapabilityError) as err:
        await SettingsSet().run(SetParams(schema="org.gnome.desktop.interface", key=key, value=value),
                                ActionContext(env, "a1"))
    assert message in err.value.message


def test_only_allow_listed_settings_can_be_named(env):
    with pytest.raises(CapabilityError) as err:
        SettingsSet().resources(SetParams(schema="org.gnome.desktop.wm.keybindings", key="close", value="[]"), env)
    assert "can't change" in err.value.message


async def test_volume_is_recorded_and_checked(env):
    class FakeVolume:
        level = (40, False)

        async def get(self):
            return self.level

        async def set(self, percent, muted):
            self.level = (percent, muted)

    env.volume = FakeVolume()
    cap, p = SoundSetVolume(), SetVolumeParams(percent=70)
    r = await cap.run(p, ActionContext(env, "a1"))
    assert r.undo == {"kind": "volume", "old": [40, False]}
    assert (await cap.verify(p, r, ActionContext(env, "a1"))).status == "passed"


# ── Apps ────────────────────────────────────────────────────────────────────


def entry(folder: Path, name: str, body: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("[Desktop Entry]\nType=Application\n" + body)


def test_installed_apps_follow_xdg_precedence_and_visibility(tmp_path):
    user, system = tmp_path / "user/applications", tmp_path / "system/applications"
    entry(system, "org.gnome.Nautilus.desktop", "Name=Files\nName[fr]=Fichiers\nGenericName=File Manager\n"
                                                "Keywords=folder;manager;\nExec=nautilus\n")
    entry(system, "org.example.Hidden.desktop", "Name=Old\nExec=old\n")
    entry(user, "org.example.Hidden.desktop", "Name=Old\nHidden=true\n")  # the user removed it
    entry(system, "org.kde.Thing.desktop", "Name=Thing\nOnlyShowIn=KDE;\n")
    entry(system, "missing.desktop", "Name=Missing\nTryExec=/nonexistent/binary\n")
    entry(system, "nodisplay.desktop", "Name=Helper\nNoDisplay=true\n")
    entry(system / "sub", "app.desktop", "Name=Nested\n")
    (system / "link.desktop").write_text("[Desktop Entry]\nType=Link\nName=Link\n")
    apps = desktop_apps.installed([user, system])
    assert [(a.id, a.name) for a in apps] == [("org.gnome.Nautilus", "Files"), ("sub-app", "Nested")]
    assert apps[0].generic == "File Manager" and apps[0].keywords == ("folder", "manager")


def test_app_dirs_from_the_environment():
    dirs = desktop_apps.app_dirs({"XDG_DATA_HOME": "/h/.local/share", "XDG_DATA_DIRS": "/a:relative:/b"})
    assert dirs == [Path("/h/.local/share/applications"), Path("/a/applications"), Path("/b/applications")]


FILES = App(id="org.gnome.Nautilus", name="Files", generic="File Manager", path=Path("/usr/share/applications/x"))


class RecordingBridge:
    def __init__(self) -> None:
        self.launched: list = []

    async def list_windows(self) -> list[Window]:
        return [Window(app_id="org.gnome.Nautilus", title="Downloads")] if self.launched else []

    async def launch_app(self, app_id: str, uris: list[str]) -> None:
        self.launched.append((app_id, uris))


async def test_launch_goes_through_the_shell_and_checks_for_a_window(env):
    bridge = RecordingBridge()
    env.apps = lambda: [FILES]
    env.bridge = lambda: bridge
    env.launcher = desktop_apps.Launcher(env.bridge)
    cap, p = AppsLaunch(), LaunchParams(app_id="org.gnome.Nautilus", files=["~/Downloads"])
    resources = cap.resources(p, env)
    assert resources[0].aliases[:2] == ("Files", "File Manager") and resources[1].access == "read"
    r = await cap.run(p, ActionContext(env, "a1"))
    assert bridge.launched == [("org.gnome.Nautilus", [f"file://{env.home}/Downloads"])]
    assert (await cap.verify(p, r, ActionContext(env, "a1"))).status == "passed"
    with pytest.raises(CapabilityError):
        cap.resources(LaunchParams(app_id="org.nope"), env)
    listed = await AppsList().run(ListParams(query="file manager"), ActionContext(env, "a2"))
    assert "Files (org.gnome.Nautilus)" in listed.observation


async def test_launch_without_the_shell_runs_in_its_own_scope(monkeypatch):
    seen: list[list[str]] = []

    async def fake_checked(argv, **kw):
        seen.append(argv)
        return ""
    monkeypatch.setattr(desktop_apps, "checked", fake_checked)
    launcher = desktop_apps.Launcher(lambda: None, systemd_run="/bin/true")
    await launcher.launch(FILES, ["file:///home/u/Downloads"])
    argv = seen[0]
    assert argv[:5] == ["/bin/true", "--user", "--scope", "--quiet", "--collect"]
    assert argv[5].startswith("--unit=app-mei-org.gnome.Nautilus-")
    assert argv[6:] == ["--", desktop_apps.GIO, "launch", str(FILES.path), "file:///home/u/Downloads"]


# ── Files and identity ──────────────────────────────────────────────────────


@pytest.mark.skipif(not PdfToText.available(), reason="needs pdftotext")
async def test_pdf_text_from_the_sandboxed_parser():
    text = await PdfToText().pdf_text(FIXTURES / "invoice.pdf", 1000)
    assert "INVOICE 2026-0042" in text and "Total 120.00 EUR" in text and "\x0c" not in text


def test_user_dirs(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Téléchargements").mkdir(parents=True)
    (home / "Docs").mkdir()
    config = tmp_path / "config"
    config.mkdir()
    (config / "user-dirs.dirs").write_text('# comment\nXDG_DOWNLOAD_DIR="$HOME/Téléchargements"\n'
                                           'XDG_DOCUMENTS_DIR="$HOME/Docs"\nXDG_MUSIC_DIR="$HOME/Missing"\n'
                                           'XDG_DESKTOP_DIR="$HOME/"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    assert paths.user_dirs(home) == {"DOWNLOAD": home / "Téléchargements", "DOCUMENTS": home / "Docs"}


def test_this_test_process_is_not_the_shell():
    assert not is_shell_executable(os.getpid())
    assert not is_shell_executable(2 ** 22 + 12345)  # no such process


async def test_settings_tools_are_hidden_without_gsettings(env):
    from mei.capabilities.catalog import default_registry
    names = {s.name for s in default_registry().specs(env)}
    assert "settings_set" not in names and "apps_launch" not in names and "fs_move" in names
    put(env, "~/x")
