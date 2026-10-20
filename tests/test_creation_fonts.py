"""Surprise defaults (#637): creating a document never touches the network (the rolled pairing is installed by
the first text), the offline flag is thread-safe, the CLI says what creation chose, an MCP server refuses the
home folder or a filesystem root as a workspace nobody chose, and an empty document stays small."""

import threading
from pathlib import Path

import httpx
import pytest

from vixl import Project, creation, typefaces
from vixl.cli import dispatch
from vixl.cli_summary import summarize
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.typefaces import get_pairing, slug


@pytest.fixture
def auto_fonts(tmp_path, monkeypatch):
    """Automatic fonts on, an empty font cache (``_cache`` fills it for a pairing) and a network that refuses;
    returns the cache, a font file's bytes and the list of network attempts."""
    cache = tmp_path / "font-cache"
    cache.mkdir()
    font = (Path(typefaces.DATA) / "DejaVuSans.ttf").read_bytes()
    monkeypatch.setenv("VIXL_FONT_CACHE", str(cache))
    monkeypatch.setenv("VIXL_AUTO_FONTS", "on")
    monkeypatch.setattr(creation, "_offline", False)
    attempts = []

    def network():
        attempts.append(1)

        def refuse(request):
            raise httpx.ConnectError("no route", request=request)

        return httpx.Client(transport=httpx.MockTransport(refuse))

    monkeypatch.setattr(creation, "network_client", network)
    return cache, font, attempts


def _cache(cache, font, pairing):
    item = get_pairing(pairing)
    for role in ("heading", "body"):
        (cache / f"{slug(item[role]['family'])}-{item[role]['weight']}.ttf").write_bytes(font)


def test_creation_makes_no_network_call_until_text(auto_fonts):
    _, _, attempts = auto_fonts
    report = {}
    p = Project.new(seed=5, report=report)
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "width": 20, "height": 20})
    assert attempts == [] and report["creation"]["fonts"]["pending"]
    assert p.state["design_defaults"]["fonts"]["pending"] and "typography" not in p.state
    result = p.apply({"type": "text", "text": "Now fonts"})
    assert attempts == [1] and result["font_install"]["installed"] is False
    assert "pending" not in p.state["design_defaults"]["fonts"]


def test_first_text_installs_the_cached_pairing_and_dry_runs_change_nothing(auto_fonts):
    cache, font, attempts = auto_fonts
    p = Project.new(seed=9)
    _cache(cache, font, p.state["design_defaults"]["fonts"]["pairing"])
    p.apply({"type": "text", "text": "Trial"}, dry_run=True)
    assert p.state["design_defaults"]["fonts"]["pending"] and "typography" not in p.state
    result = p.apply({"type": "text", "text": "Hello", "font": "heading"})
    assert result["font_install"]["origin"] == "cache" and attempts == []
    assert p.state["typography"]["heading"] and p.state["design_defaults"]["fonts"]["installed"]
    p.undo()
    assert p.state["design_defaults"]["fonts"]["pending"]  # undoing the first text takes the fonts with it


def test_text_made_without_a_text_operation_still_gets_the_pairing(auto_fonts):
    cache, font, attempts = auto_fonts
    p = Project.new(width=800, height=600, seed=11)
    _cache(cache, font, p.state["design_defaults"]["fonts"]["pairing"])
    result = p.apply({"type": "container-place", "resource": "headline-left", "name": "card",
                      "variables": {"title": "Hi", "body": "There"}})
    assert result["font_install"]["installed"] and p.state["typography"]["body"]


def test_a_batch_that_chooses_fonts_skips_the_pending_pairing(auto_fonts, monkeypatch):
    _, font, attempts = auto_fonts
    monkeypatch.setattr(typefaces, "fetch_font", lambda family, weight=400, *a, **k: (font, family))
    p = Project.new(seed=4)
    from vixl.typefaces import pair_fonts

    pair_fonts(p, "source-serif-sans")
    p.apply({"type": "text", "text": "Own fonts"})
    assert attempts == [] and p.state["design_defaults"]["fonts"]["reason"] == "the document chose its own fonts"


def test_offline_flag_is_safe_across_threads_and_expires(monkeypatch):
    monkeypatch.setattr(creation, "_offline", False)
    threads = [threading.Thread(target=creation.mark_network_failed) for _ in range(16)]
    seen = []
    threads += [threading.Thread(target=lambda: seen.append(creation.network_failed())) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert creation.network_failed() is True and all(isinstance(value, bool) for value in seen)
    monkeypatch.setattr(creation, "_offline_since", creation.time.monotonic() - creation.OFFLINE_TTL - 1)
    assert creation.network_failed() is False


def test_new_summary_names_the_seed_and_the_font_status(auto_fonts, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    made, _ = dispatch(["new", "300x200", "--seed", "7", "-o", "a.vixl"])
    text = summarize(made, "new")
    assert "seed 7" in text and "fonts: " in text and "first text" in text
    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    made, _ = dispatch(["new", "300x200", "--seed", "7", "-o", "b.vixl"])
    assert "fonts: fallback (VIXL_AUTO_FONTS=off)" in summarize(made, "new")


def test_an_empty_new_document_is_small(auto_fonts, tmp_path, monkeypatch):
    cache, font, _ = auto_fonts
    monkeypatch.chdir(tmp_path)
    pairing = Project(seed=3, workspace_fonts=False).state["design_defaults"]["direction"]["pairing"]
    _cache(cache, font, pairing)  # even a cached pairing is not embedded before there is text
    dispatch(["new", "800x600", "--seed", "3", "-o", "empty.vixl"])
    assert (tmp_path / "empty.vixl").stat().st_size < 10_000


def test_session_refuses_home_or_root_as_an_implicit_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(VixlError) as caught:
        Session()
    assert caught.value.code == "unsafe_workspace" and "--workspace" in str(caught.value)
    assert Session(workspace=tmp_path).workspace == tmp_path.resolve()  # chosen explicitly: fine
    monkeypatch.chdir("/")
    with pytest.raises(VixlError):
        Session()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    assert Session().workspace == work.resolve()


def test_mcp_refuses_home_as_the_workspace_of_a_remembered_document(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    Project(20, 20).save(tmp_path / "doc.vixl")
    dispatch(["open", "doc.vixl"])
    with pytest.raises(VixlError) as caught:
        dispatch(["mcp"])
    assert caught.value.code == "unsafe_workspace"
