"""The popup's large page (decision 0034): the work page's latest picture and Pause, and PDF pages drawn
by pdftoppm in its jail. Pictures and files are the person's: only the Shell may ask for them."""

import base64
import json
import struct
import zlib

import pytest

from mei.core.states import TaskState
from mei.desktop.pdf import PdfPages
from mei.desktop.run import ToolFailed
from mei.ipc.service import RuntimeService
from mei.protocol import ProtocolError, TaskCommandArgs
from mei.store import repo

from agent_harness import Harness, call, turn
from test_computer import computer_harness, reaches

S = TaskState


def png(width: int, height: int) -> bytes:
    """A real (grey) PNG of this size."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"\x80" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def make_pdf(pages: int) -> bytes:
    """A small valid PDF with this many pages, each a filled box."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{3 + 2 * i} 0 R" for i in range(pages)), pages)]
    for i in range(pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] /Contents {4 + 2 * i} 0 R >>")
        stream = f"0 0 0 rg 20 20 {40 + 10 * i} 60 re f"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def service(h: Harness, shell: bool = True, pdf: PdfPages | None = None) -> RuntimeService:
    async def is_shell(_sender: str) -> bool:
        return shell
    return RuntimeService(bus=None, engine=h.engine, is_shell=is_shell, pdf=pdf)


def picturing(tmp_path, sizes: list[tuple[int, int]]):
    """A computer-use task that looks at the screen once per size, each look a real PNG of that size."""
    h, desktop = computer_harness(tmp_path, [*(turn(call("desktop_observe", picture=True)) for _ in sizes),
                                             {"text": "I see it."}])
    looks = iter(sizes)
    plain = desktop.observe

    async def observe(window, monitors, *, picture, max_nodes=250):
        data = await plain(window, monitors, picture=picture, max_nodes=max_nodes)
        width, height = next(looks)
        data["picture"] = {"png": base64.b64encode(png(width, height)).decode(), "width": width, "height": height}
        return data

    desktop.observe = observe
    return h, desktop


# ── The latest picture ──────────────────────────────────────────────────────


async def test_the_work_page_gets_the_newest_picture_and_actions_say_they_kept_one(tmp_path):
    h, _desktop = picturing(tmp_path, [(40, 30), (64, 40)])
    r = h.submit("what's in the Login window?")
    assert await h.until(r["task_id"]) == S.COMPLETED
    looks = [a for a in h.actions(r["task_id"]) if a["tool"] == "desktop_observe"]
    reply = await service(h)._latest_picture(":1.2", json.dumps({"conversation_id": r["conversation_id"]}))
    picture = reply["picture"]
    assert (picture["action_id"], picture["task_id"]) == (looks[-1]["id"], r["task_id"])
    assert (picture["width"], picture["height"]) == (64, 40)
    assert picture["path"].startswith(str(h.env.artifacts(r["conversation_id"])))
    views = [a for a in repo.conversation_snapshot(h.store, r["conversation_id"])["tasks"][0]["actions"]
             if a["tool"] == "desktop_observe"]
    assert [v["pictures"] for v in views] == [1, 1]


async def test_no_picture_a_deleted_one_and_one_outside_the_artifacts_are_none(tmp_path):
    h, _desktop = picturing(tmp_path, [(40, 30)])
    r = h.submit("what's in the Login window?")
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert h.engine.latest_picture(r["conversation_id"], task_id="another-task") is None
    picture = h.engine.latest_picture(r["conversation_id"])
    elsewhere = tmp_path / "elsewhere.png"
    elsewhere.write_bytes(png(8, 8))
    with h.store.tx() as tx:
        tx.execute("UPDATE actions SET result = json_set(result, '$.images', json_array(?)) WHERE id = ?",
                   (str(elsewhere), picture["action_id"]))
    assert h.engine.latest_picture(r["conversation_id"]) is None
    with h.store.tx() as tx:
        tx.execute("UPDATE actions SET result = json_set(result, '$.images', json_array(?)) WHERE id = ?",
                   (picture["path"], picture["action_id"]))
    assert h.engine.latest_picture(r["conversation_id"]) is not None
    (tmp_path / picture["path"]).unlink()
    assert h.engine.latest_picture(r["conversation_id"]) is None


async def test_only_the_shell_sees_pictures_and_files(tmp_path):
    h = Harness(tmp_path)
    stranger = service(h, shell=False, pdf=PdfPages(tmp_path / "pages"))
    for method, args in ((stranger._latest_picture, {"conversation_id": "c"}),
                         (stranger._pdf_info, {"path": "/tmp/a.pdf"}),
                         (stranger._pdf_page, {"path": "/tmp/a.pdf", "page": 1, "width": 400})):
        with pytest.raises(ProtocolError) as err:
            await method(":1.9", json.dumps(args))
        assert err.value.name == "AccessDenied"


# ── Pause and go on ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("go_on_before_an_act", [False, True])
async def test_pause_holds_the_next_act_until_go_on(tmp_path, go_on_before_an_act):
    h, desktop = computer_harness(tmp_path, [turn(call("desktop_observe")), {"text": "Done."}])
    r = h.submit("what's in the Login window?")
    paused = service(h)._pause(":1.9", json.dumps({"command_id": "c-pause", "task_id": r["task_id"]}))
    assert paused["paused"]
    if go_on_before_an_act:  # changed their mind before Mei got to an act: nothing waited
        h.engine.resume(TaskCommandArgs(command_id="c-resume", task_id=r["task_id"]))
    else:
        await reaches(h, r["task_id"], S.WAITING_RESOURCE)
        assert h.task(r["task_id"])["error"] == "Paused by you" and desktop.observed == 0
        h.engine.resume(TaskCommandArgs(command_id="c-resume", task_id=r["task_id"]))
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert desktop.observed == 1


async def test_the_kill_switch_stops_a_paused_task_and_a_finished_one_isnt_paused(tmp_path):
    h, desktop = computer_harness(tmp_path, [turn(call("desktop_observe")), {"text": "Done."}])
    r = h.submit("what's in the Login window?")
    h.engine.pause(TaskCommandArgs(command_id="c-pause", task_id=r["task_id"]))
    await reaches(h, r["task_id"], S.WAITING_RESOURCE)
    assert h.engine.stop_computer_use() == [r["task_id"]]  # the work page's Stop is the kill switch
    assert await h.until(r["task_id"]) == S.CANCELLED and desktop.observed == 0
    assert h.engine.pause(TaskCommandArgs(command_id="c-again", task_id=r["task_id"]))["paused"] is False
    with pytest.raises(ProtocolError):
        h.engine.pause(TaskCommandArgs(command_id="c-none", task_id="no-such-task"))


# ── PDF pages ───────────────────────────────────────────────────────────────

needs_poppler = pytest.mark.skipif(not PdfPages.available(), reason="poppler-utils isn't installed")


@needs_poppler
async def test_pdf_pages_are_counted_and_drawn_one_at_a_time_and_kept(tmp_path):
    doc = tmp_path / "three pages.pdf"
    doc.write_bytes(make_pdf(3))
    pages = PdfPages(tmp_path / "pages")
    assert await pages.pages(str(doc)) == 3
    drawn = await pages.page(str(doc), 2, 300)
    head = drawn.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", head[16:24]) == (300, 450)
    first = drawn.stat().st_mtime_ns
    assert await pages.page(str(doc), 2, 300) == drawn and drawn.stat().st_mtime_ns == first  # kept, not redrawn
    assert (await pages.page(str(doc), 1, 50000)).name.endswith("-1-2400.png")  # widths are bounded
    doc.write_bytes(make_pdf(4))  # changed: drawn again
    assert await pages.pages(str(doc)) == 4 and await pages.page(str(doc), 2, 300) != drawn


@needs_poppler
async def test_bad_pdfs_folders_and_missing_files_fail_with_a_reason(tmp_path):
    pages = PdfPages(tmp_path / "pages")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is not really a PDF")
    with pytest.raises(ToolFailed):
        await pages.pages(str(broken))
    with pytest.raises(FileNotFoundError):
        await pages.pages(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        await pages.page(str(tmp_path / "gone.pdf"), 1, 300)
    doc = tmp_path / "one.pdf"
    doc.write_bytes(make_pdf(1))
    with pytest.raises(ToolFailed):
        await pages.page(str(doc), 5, 300)  # past the last page


@needs_poppler
async def test_pdf_methods_over_the_service(tmp_path):
    h = Harness(tmp_path)
    doc = tmp_path / "two.pdf"
    doc.write_bytes(make_pdf(2))
    shell = service(h, pdf=PdfPages(tmp_path / "pages"))
    assert await shell._pdf_info(":1.2", json.dumps({"path": str(doc)})) == {"pages": 2}
    drawn = await shell._pdf_page(":1.2", json.dumps({"path": str(doc), "page": 1, "width": 200}))
    assert drawn["path"].startswith(str(tmp_path / "pages")) and (drawn["width"], drawn["height"]) == (200, 300)
    for path, name in ((f"{tmp_path}/../two.pdf", "InvalidArgument"), ("two.pdf", "InvalidArgument"),
                       (str(tmp_path / "gone.pdf"), "NotFound")):
        with pytest.raises(ProtocolError) as err:
            await shell._pdf_info(":1.2", json.dumps({"path": path}))
        assert err.value.name == name
    with pytest.raises(ProtocolError) as err:
        await service(h, pdf=None)._pdf_info(":1.2", json.dumps({"path": str(doc)}))
    assert err.value.name == "Unsupported"  # the viewer falls back to the file's name and size
