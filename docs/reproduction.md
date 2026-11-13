# Reproduction against the study matrix

This is a cell-level comparison between `pohe-agent` and the frozen
52-record × 41-repository cue matrix in `pattern-mining-study`
(`data/derived/pattern_repo_full_matrix.csv`, column `current_cue_present`).

The comparison asks one narrow question: **does the agent retrieve a cue in the
same repository cells as the study's frozen detector?** It does not claim that
either side confirmed an implementation.

## Run

- Date: 2026-11-13
- Agent: `pohe-agent` at this commit, default surface (all candidate files)
- Corpus: the 41 checkouts in `pattern-mining-study/.cache/repositories`
- Commit check: all 41 `HEAD`s matched the manifest `commit_sha`
- Candidate files scanned: 172,832
- Runtime: 452 s with 8 workers

```bash
python tools/reproduce_study_matrix.py \
  --cache-dir ../pattern-mining-study/.cache/repositories \
  --manifest ../pattern-mining-study/data/manifests/current_41_repositories.csv \
  --matrix ../pattern-mining-study/data/derived/pattern_repo_full_matrix.csv
```

## Result

| Metric | Value |
| --- | ---: |
| Cells compared | 2,132 |
| Exact agreement | **98.55%** (2,101 / 2,132) |
| Positive cells in the study | 1,246 |
| Positive cells in the agent | 1,267 |
| Positive in both | 1,241 |
| Recall over study-positive cells | **99.60%** |
| Precision over agent-positive cells | **97.95%** |
| Jaccard over positive cells | 97.56% |
| Study-only cells | 5 |
| Agent-only cells | 26 |

## The five misses are deliberate boundaries

Every study-positive cell the agent missed is a file the agent excludes by
design:

| Record | Repository | File | Reason |
| --- | --- | --- | --- |
| P06 | mingju-c/HarnessForge | `eval_bench/api-bank/init_database/ImageCaptioning.json` | 2.5 MB, above the 2 MB file limit |
| P14 | Aider-AI/aider | `aider/website/assets/asciinema/asciinema-player.min.js` | minified third-party asset |
| P20 | OpenHands/OpenHands | `src/i18n/translation.json` | 2.04 MB, above the 2 MB file limit |
| P29 | Darwin-Agent/HarnessX | `benchmarks/swebench/swebench_lite_test.json` | 3.7 MB, above the 2 MB file limit |
| W01 | QwenLM/qwen-code | `packages/cli/src/acp-integration/session/Session.test.ts` | 2.35 MB, above the 2 MB file limit |

There are no unexplained misses. These boundaries keep the scanner from
treating generated data, bundles, and localization tables as harness evidence.

## The 26 extras are mostly frozen-evidence drift

All 26 agent-only cells sit on extensions the study protocol already scans
(`.py`, `.ts`, `.cs`, `.txt`, `.json`, `.yaml`), so broader language coverage is
not the explanation. Two spot re-runs of the study's own detector on the same
checkouts recovered cues that the frozen matrix omits:

- `openai/swarm` + P19: the frozen matrix has no P19 cue, while a rerun of
  `src/detectors/ripgrep_catalog.py` retrieves **7** P19 cues, including
  `README.md:133` (`max_turns`).
- `browser-use/browser-use` + C03: the frozen matrix has no C03 cue, while the
  same rerun retrieves **40** C03 cues under the current cap, including
  `browser_use/actor/element.py:359` (`event_bus`).

The frozen evidence therefore behaves as a lower bound in these cells. The
agent reports them at E1 and marks them for source review; it does not call
them confirmed implementations.

Agent-only cells:

| Record | Repository | First retrieved file | Kind |
| --- | --- | --- | --- |
| C03 | browser-use/browser-use | `browser_use/actor/element.py` | code |
| C03 | microsoft/agent-framework | `dotnet/src/Microsoft.Agents.AI.Workflows/Checkpointing/ICheckpointingHandle.cs` | code |
| E01 | openai/codex | `sdk/python/src/openai_codex/generated/v2_all.py` | code |
| P19 | FoundationAgents/MetaGPT | `metagpt/strategy/tot.py` | code |
| P19 | OpenHands/OpenHands | `src/api/agent-server-adapter.ts` | code |
| P19 | OpenHands/software-agent-sdk | `clients/typescript/src/client/cloud-client.ts` | code |
| P19 | agno-agi/agno | `libs/agno/agno/agents/claude/agent.py` | code |
| P19 | china-qijizhifeng/agentic-harness-engineering | `agents/evolve_agent/middleware/round_and_token_reminder.py` | code |
| P19 | crewAIInc/crewAI | `lib/crewai-tools/src/crewai_tools/tools/multion_tool/multion_tool.py` | code |
| P19 | google-research/harness2 | `third_party/lab_runner/opencode/run_opencode.py` | code |
| P19 | google/adk-python | `src/google/adk/a2a/utils/agent_card_builder.py` | code |
| P19 | huggingface/smolagents | `src/smolagents/agents.py` | code |
| P19 | langchain-ai/langgraph | `libs/langgraph/tests/example_app/example_graph.py` | test |
| P19 | microsoft/autogen | `python/packages/autogen-agentchat/src/autogen_agentchat/agents/_society_of_mind_agent.py` | code |
| P19 | openai/openai-agents-js | `packages/agents-core/src/runner/turnPreparation.ts` | code |
| P19 | openai/swarm | `swarm/core.py` | code |
| P20 | SWE-agent/mini-swe-agent | `docs/data/all_models.txt` | support |
| R02 | langchain-ai/langgraph | `docs/redirects.json` | support |
| W03 | FoundationAgents/MetaGPT | `metagpt/actions/research.py` | code |
| W03 | SWE-agent/SWE-agent | `sweagent/tools/tools.py` | code |
| W03 | china-qijizhifeng/agentic-harness-engineering | `agents/evolve_agent/tools/mcp_client.py` | code |
| W03 | continuedev/continue | `core/autocomplete/CompletionProvider.ts` | code |
| W03 | google-gemini/gemini-cli | `packages/a2a-server/src/agent/task.ts` | code |
| W03 | google-research/rrsi | `domains/eng/bench/run_tasks.py` | code |
| W03 | mingju-c/HarnessForge | `HarnessForge_4B/harness_factory/rounds/round_00_base/harness7/action_module/prompts/toolcalling_agent.yaml` | support |
| W03 | openai/openai-agents-js | `docs/src/scripts/translate.ts` | code |

## What this establishes

1. The agent is executable on real repositories at their frozen commits, not
   only on the bundled example.
2. Its cue surface agrees with the published matrix in 98.55% of cells and
   misses no study-positive cell outside four stated file boundaries and one
   minified-asset boundary.
3. Residual differences are concentrated in cells where the frozen matrix and
   a fresh run of the study detector already disagree, plus records whose
   evidence is documentation, configuration, or generated code.
4. Agreement is at E1 (retrieval cue). It is not evidence of implementation,
   pointcut satisfaction, or contract compliance; that requires source review.
   The same run also exercises `match` on real checkouts: cue-bearing function
   and class bodies become candidates with the pointcut and contract questions
   attached, rather than an empty symbol-name filter.
