import sys

sys.path.insert(0, ".")

from yunta.api import Block, BlockType, Message, Role
from yunta.compact import NoCompaction, SlidingWindow


def msg_user(text="q"):
    return Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text=text)])


def msg_tool_result():
    return Message(
        role=Role.USER,
        content=[Block(type=BlockType.TOOL_RESULT, tool_use_id="1", tool_result="r")],
    )


def msg_assistant():
    return Message(role=Role.ASSISTANT, content=[Block(type=BlockType.TEXT, text="a")])


def test_no_compaction_passthrough():
    msgs = [msg_user(), msg_assistant()]
    assert NoCompaction().compact(msgs) is msgs


def test_sliding_window_noop_under_limit():
    msgs = [msg_user(), msg_assistant()]
    assert SlidingWindow(max_messages=10).compact(msgs) == msgs


def test_sliding_window_cuts_at_safe_boundary():
    msgs = (
        [msg_user("1"), msg_assistant(), msg_tool_result()]
        + [msg_user("2"), msg_assistant()]
        + [msg_user("3"), msg_assistant()]
    )
    out = SlidingWindow(max_messages=4).compact(msgs)
    assert len(out) <= 5
    # el primer mensaje restante debe ser un user sin tool_results
    assert out[0].role == Role.USER and not out[0].has_tool_result()
    # nunca queda un tool_result huérfano al inicio
    assert not out[0].has_tool_result()
