import pytest
from yunta.api import Block, BlockType, Message, Role
from yunta.compact import TokenBudgetCompactor


def test_token_budget_below_70_percent():
    compactor = TokenBudgetCompactor(max_tokens=1000)
    messages = [
        Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="hola " * 50)]),  # ~50 tokens
    ]
    res = compactor.compact(messages)
    assert len(res) == 1
    assert compactor.usage_ratio(messages) < 0.70


def test_token_budget_70_percent_warning():
    compactor = TokenBudgetCompactor(max_tokens=1000)
    # Generate ~750 tokens (75% of 1000 max_tokens)
    long_text = "token " * 500
    messages = [
        Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="inicio")]),
        Message(role=Role.ASSISTANT, content=[Block(type=BlockType.TEXT, text=long_text)]),
    ]
    res = compactor.compact(messages)
    assert len(res) == 3
    assert res[1].role == Role.USER
    assert "[AVISO COMPACT" in res[1].content[0].text
    assert "(70%)" in res[1].content[0].text


def test_token_budget_80_percent_masking():
    compactor = TokenBudgetCompactor(max_tokens=1000)
    long_result = "X" * 3500  # ~875 tokens (>80%)
    messages = [
        Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="ejecuta")]),
        Message(
            role=Role.USER,
            content=[
                Block(
                    type=BlockType.TOOL_RESULT,
                    tool_use_id="1",
                    tool_result=long_result,
                    is_error=False,
                )
            ],
        ),
    ]
    res = compactor.compact(messages)
    # The tool result block should be masked
    tr_block = res[-1].content[0]
    assert "[... contenido enmascarado por 80% de presupuesto de tokens ...]" in tr_block.tool_result
    assert len(tr_block.tool_result) < len(long_result)


def test_token_budget_85_percent_pruning():
    compactor = TokenBudgetCompactor(max_tokens=1000)
    # Create 12 messages with ~900 tokens total
    messages = [Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="primero")])]
    for i in range(11):
        role = Role.USER if i % 2 == 0 else Role.ASSISTANT
        messages.append(Message(role=role, content=[Block(type=BlockType.TEXT, text="cadena de texto " * 20)]))

    res = compactor.compact(messages)
    assert len(res) < len(messages)
    assert res[0].content[0].text == "primero"


def test_token_budget_99_percent_summary():
    compactor = TokenBudgetCompactor(max_tokens=1000)
    # ~1000 tokens
    messages = [Message(role=Role.USER, content=[Block(type=BlockType.TEXT, text="primero")])]
    for i in range(10):
        role = Role.USER if i % 2 == 0 else Role.ASSISTANT
        messages.append(Message(role=role, content=[Block(type=BlockType.TEXT, text="palabras varias " * 25)]))

    res = compactor.compact(messages)
    assert len(res) <= 6
    assert "[RESUMEN DE HISTORIAL (99% de presupuesto" in res[1].content[0].text
