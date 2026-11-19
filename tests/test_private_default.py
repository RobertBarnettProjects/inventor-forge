"""An Inventor this session starts is its own: started private when the client asks, closed when the session ends,
and never closed while it holds unsaved work. Offline: COM is replaced by small fakes."""
from types import SimpleNamespace

from inventor_forge.session import Session
from inventor_forge.tools import docs


class _Docs(list):
    @property
    def Count(self):
        return len(self)

    def Item(self, i):
        return self[i - 1]


def _session(private=True, dirty=False):
    s = Session(visible=False)
    app = SimpleNamespace(Caption="Inventor", Visible=False,
                          Documents=_Docs([SimpleNamespace(DisplayName="bracket", Dirty=dirty)]))
    s._app, s.private, s.pid = app, private, 4242
    return s, app


def test_unsaved_work_is_shown_not_closed(monkeypatch):
    s, app = _session(dirty=True)
    monkeypatch.setattr(docs, "close_private_inventor", lambda s: (_ for _ in ()).throw(AssertionError("closed")))
    out = docs.finish_session(s)
    assert out["left_open"] == 4242 and out["unsaved"] == ["bracket"] and app.Visible is True


def test_clean_private_inventor_is_closed(monkeypatch):
    s, _ = _session(dirty=False)
    closed = []
    monkeypatch.setattr(docs, "close_private_inventor", lambda s: closed.append(s.pid) or {"closed": s.pid})
    assert docs.finish_session(s) == {"closed": 4242} and closed == [4242]


def test_an_attached_inventor_is_never_touched(monkeypatch):
    s, app = _session(private=False, dirty=False)
    monkeypatch.setattr(docs, "close_private_inventor", lambda s: (_ for _ in ()).throw(AssertionError("closed")))
    assert docs.finish_session(s) == {"closed": None} and app.Visible is False


def test_client_preference_starts_a_private_inventor(monkeypatch):
    monkeypatch.setenv("INVENTOR_FORGE_PRIVATE", "1")
    s = Session(visible=False)
    started = []
    monkeypatch.setattr(s, "start_private", lambda: started.append(1) or "own")
    assert s._connect() == "own" and started == [1]
    monkeypatch.delenv("INVENTOR_FORGE_PRIVATE")
    assert not Session(visible=False).prefer_private


def test_asking_for_the_users_inventor_drops_the_preference(monkeypatch):
    monkeypatch.setenv("INVENTOR_FORGE_PRIVATE", "1")
    s = Session(visible=False)
    seen = {}

    class Stop(Exception):
        pass

    def fake_private():
        seen["private"] = True
        raise Stop

    monkeypatch.setattr(s, "start_private", fake_private)
    monkeypatch.setattr(type(s), "app", property(lambda self: (_ for _ in ()).throw(Stop())))
    try:
        docs.connect.__wrapped__(s, private=False) if hasattr(docs.connect, "__wrapped__") else docs.connect(s, private=False)
    except Stop:
        pass
    assert s.prefer_private is False and "private" not in seen
