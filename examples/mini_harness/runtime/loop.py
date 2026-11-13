"""A deliberately small harness used by the pohe-agent test suite."""
from __future__ import annotations


class AgentRunner:
    def run_agent(self, task: str, model, tools, max_turns: int = 8) -> dict:
        history = []
        for turn in range(max_turns):
            response = model.complete(task, history)
            if response.tool_call is None:
                return {"status": "done", "turn": turn, "output": response.text}
            result = tools.invoke(response.tool_call)
            history.append({"turn": turn, "action": response.tool_call, "result": result})
        return {"status": "budget_exhausted", "turns": len(history)}
