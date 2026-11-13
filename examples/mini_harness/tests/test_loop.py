from runtime.loop import AgentRunner


class FakeModel:
    def __init__(self):
        self.calls = 0

    def complete(self, task, history):
        self.calls += 1
        if self.calls == 1:
            return type("Response", (), {"text": "", "tool_call": type("Call", (), {"name": "read", "arguments": {}})()})()
        return type("Response", (), {"text": "done", "tool_call": None})()


def test_runner_returns_after_tool_turn():
    class Tools:
        def invoke(self, call):
            return "file contents"

    result = AgentRunner().run_agent("read a file", FakeModel(), Tools(), max_turns=4)
    assert result["status"] == "done"
    assert result["turn"] == 1


def test_runner_stops_at_budget():
    class Tools:
        def invoke(self, call):
            return "again"

    class Endless:
        def complete(self, task, history):
            return type("Response", (), {"text": "", "tool_call": type("Call", (), {"name": "read", "arguments": {}})()})()

    result = AgentRunner().run_agent("loop", Endless(), Tools(), max_turns=3)
    assert result["status"] == "budget_exhausted"
