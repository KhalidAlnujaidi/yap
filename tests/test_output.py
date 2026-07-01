from parakeet_dictation.output import OutputSink


def _make(focused=False):
    state = {"clip": None, "pastes": 0}
    sink = OutputSink(
        set_clipboard=lambda t: state.__setitem__("clip", t),
        is_field_focused=lambda: focused,
        paste=lambda: state.__setitem__("pastes", state["pastes"] + 1),
    )
    return sink, state


def test_empty_text_is_ignored():
    sink, state = _make()
    assert sink.deliver("   ") is False
    assert state["clip"] is None
    assert sink.recent() == []


def test_delivers_to_clipboard_always():
    sink, state = _make(focused=False)
    assert sink.deliver("hello") is True
    assert state["clip"] == "hello"
    assert state["pastes"] == 0  # no paste when unfocused


def test_pastes_when_field_focused():
    sink, state = _make(focused=True)
    sink.deliver("hi there")
    assert state["clip"] == "hi there"
    assert state["pastes"] == 1


def test_recent_is_newest_first_and_capped_at_15():
    sink, _ = _make()
    for i in range(20):
        sink.deliver(f"line {i}")
    recent = sink.recent()
    assert len(recent) == 15
    assert recent[0] == "line 19"
    assert recent[-1] == "line 5"
