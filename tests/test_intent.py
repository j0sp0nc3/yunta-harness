"""Pruebas unitarias para yunta/intent.py."""

from yunta.intent import IntentClassifier, TaskIntent


def test_classify_software_prompts():
    assert IntentClassifier.classify("refactor the login function and fix pytest error") == TaskIntent.SOFTWARE_IMPLEMENTATION
    assert IntentClassifier.classify("agregale un test al modulo de api") == TaskIntent.SOFTWARE_IMPLEMENTATION
    assert IntentClassifier.classify("corrige el bug en la compilacion de dotnet") == TaskIntent.SOFTWARE_IMPLEMENTATION


def test_classify_research_and_consulting_prompts():
    assert IntentClassifier.classify("resume la cátedra de medicina de cardiología de hoy") == TaskIntent.RESEARCH_AND_CONSULTING
    assert IntentClassifier.classify("transcribe esta clase de audio y genera un glosario de fármacos") == TaskIntent.RESEARCH_AND_CONSULTING
    assert IntentClassifier.classify("dame una consultoría sobre estrategias de arquitectura de datos") == TaskIntent.RESEARCH_AND_CONSULTING


def test_should_enforce_sdd():
    assert IntentClassifier.should_enforce_sdd(TaskIntent.SOFTWARE_IMPLEMENTATION) is True
    assert IntentClassifier.should_enforce_sdd(TaskIntent.RESEARCH_AND_CONSULTING) is False


def test_evaluate_triviality_true_when_only_readonly_tools_recent():
    calls = [("read_file", '{"path":"a.py"}'), ("grep", '{"pattern":"x"}')]
    assert IntentClassifier.evaluate_triviality(calls, "sigue investigando") is True


def test_evaluate_triviality_false_with_no_history():
    assert IntentClassifier.evaluate_triviality([], "lo que sea") is False


def test_evaluate_triviality_false_when_mutating_tool_present():
    calls = [("read_file", "x"), ("write_file", '{"path":"a.py","content":"x"}')]
    assert IntentClassifier.evaluate_triviality(calls, "listo") is False

    calls2 = [("str_replace", "x")]
    assert IntentClassifier.evaluate_triviality(calls2, "listo") is False

    calls3 = [("bash", "ls")]
    assert IntentClassifier.evaluate_triviality(calls3, "listo") is False


def test_evaluate_triviality_false_when_unknown_tool_present():
    """Tools fuera del allowlist explícito (ni de lectura confirmada ni
    mutante conocida) tampoco se consideran triviales -- por defecto
    conservador."""
    calls = [("read_file", "x"), ("delegate_subtask", "x")]
    assert IntentClassifier.evaluate_triviality(calls, "listo") is False


def test_evaluate_triviality_false_when_deep_reasoning_keyword_in_prompt():
    calls = [("read_file", "x")]
    assert IntentClassifier.evaluate_triviality(calls, "dame la causa raíz de este bug") is False


def test_evaluate_reasoning():
    from yunta.intent import ReasoningLevel

    # Explicit keyword matches
    assert IntentClassifier.evaluate_reasoning("haz un razonamiento profundo sobre este problema") == ReasoningLevel.HIGH
    assert IntentClassifier.evaluate_reasoning("dame la causa raíz de este bug") == ReasoningLevel.HIGH
    assert IntentClassifier.evaluate_reasoning("rápido crea un archivo de prueba.txt") == ReasoningLevel.OFF

    # User override tests
    assert IntentClassifier.evaluate_reasoning("hola", user_override="high") == ReasoningLevel.HIGH
    assert IntentClassifier.evaluate_reasoning("piensa profundamente", user_override="off") == ReasoningLevel.OFF
    assert IntentClassifier.evaluate_reasoning("analiza", user_override="medium") == ReasoningLevel.MEDIUM

