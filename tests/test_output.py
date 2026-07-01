from yap.output import OutputSink


def _make(auto_paste=True):
    state = {"clip": None, "pastes": 0, "spaces": 0}
    sink = OutputSink(
        set_clipboard=lambda t: state.__setitem__("clip", t),
        paste=lambda: state.__setitem__("pastes", state["pastes"] + 1),
        type_space=lambda: state.__setitem__("spaces", state["spaces"] + 1),
        auto_paste=auto_paste,
    )
    return sink, state


def test_empty_text_is_ignored():
    sink, state = _make()
    assert sink.deliver("   ") is False
    assert state["clip"] is None
    assert sink.recent() == []


def test_delivers_pastes_and_adds_space_by_default():
    sink, state = _make(auto_paste=True)
    assert sink.deliver("hello") is True
    assert state["clip"] == "hello"      # clipboard stays clean (no trailing space)
    assert state["pastes"] == 1
    assert state["spaces"] == 1          # a separating space is typed after paste


def test_no_paste_or_space_when_auto_paste_disabled():
    sink, state = _make(auto_paste=False)
    assert sink.deliver("hi there") is True
    assert state["clip"] == "hi there"   # clipboard still set
    assert state["pastes"] == 0
    assert state["spaces"] == 0


def test_recent_is_newest_first_and_capped_at_15():
    sink, _ = _make()
    for i in range(20):
        sink.deliver(f"line {i}")
    recent = sink.recent()
    assert len(recent) == 15
    assert recent[0] == "line 19"
    assert recent[-1] == "line 5"
