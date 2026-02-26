import json
from types import SimpleNamespace

from senior_cpp_agent.runtime import JsonFormatter


def test_json_formatter_emits_structured_fields():
    formatter = JsonFormatter()
    record = SimpleNamespace(
        levelname="INFO",
        name="senior_cpp_agent.runtime",
        getMessage=lambda: "hello",
        request_id="req-1",
        run_id="run-1",
        event="run_start",
    )

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello"
    assert payload["request_id"] == "req-1"
    assert payload["run_id"] == "run-1"
    assert payload["event"] == "run_start"
