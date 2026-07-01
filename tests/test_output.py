from yap.output import OutputSink


def _make(auto_paste=True):
    state = {"clip": None, "pastes": 0}
    sink = OutputSink(
        set_clipboard=lambda t: state.__setitem__("clip", t),
        paste=lambda: state.__setitem__("pastes", state["pastes"] + 1),
        auto_paste=auto_paste,
    )
    return sink, state


def test_empty_text_is_ignored():
    sink, state = _make()
    assert sink.deliver("   ") is False
    assert state["clip"] is None
    assert sink.recent() == []


def test_delivers_to_clipboard_and_pastes_by_default():
    sink, state = _make(auto_paste=True)
    assert sink.deliver("hello") is True
    assert state["clip"] == "hello"
    assert state["pastes"] == 1


def test_no_paste_when_auto_paste_disabled():
    sink, state = _make(auto_paste=False)
    assert sink.deliver("hi there") is True
    assert state["clip"] == "hi there"  # clipboard still set
    assert state["pastes"] == 0


def test_recent_is_newest_first_and_capped_at_15():
    sink, _ = _make()
    for i in range(20):
        sink.deliver(f"line {i}")
    recent = sink.recent()
    assert len(recent) == 15
    assert recent[0] == "line 19"
    assert recent[-1] == "line 5"
