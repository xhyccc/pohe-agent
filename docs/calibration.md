# Canonical calibration audit

This report checks each frozen record against the one canonical example
stored in the catalog. It separates retrieval, anchor scope, and
structural coverage. A gap is a review signal about the pointcut, the
exemplar, or the operational signature; it is not a prevalence estimate.

## Summary

| Metric | Value |
| --- | ---: |
| Records audited | 51 |
| Canonical anchor retrieved | 51 |
| Retrieval gaps | 0 |
| Frozen cue missed, operational cue recovered | 17 |
| Cue hit did not enter the anchored scope | 1 |
| Anchor is a file or non-code unit | 12 |
| Structure roles missing | 34 |
| Negative-control risk | 6 |
| `source_matched` | 9 |
| `pointcut_candidate` | 9 |
| `structural_candidate` | 22 |
| `cue_only` | 6 |
| `rejected` | 5 |
| Anchor missing | 0 |

## Records

| Record | Anchor | Scope | Cue hits | Verdict | Missing roles | Gaps |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | `python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_base_group_chat_manager.py:25` | class `BaseGroupChatManager` | 0 frozen / 1 operational / 1 in scope | `rejected` | mediator, routing | frozen_cue_miss, structure_gap, negative_control_risk |
| C02 | `packages/core/src/events/event-emitter/index.ts:21` | class `EventEmitterPubSub` | 0 frozen / 40 operational / 3 in scope | `pointcut_candidate` | ordering | frozen_cue_miss, structure_gap |
| C03 | `packages/core/src/events/pubsub.ts:19` | class `PubSub` | 22 frozen / 0 operational / 2 in scope | `source_matched` | — | — |
| C04 | `packages/core/src/events/unix-socket-pubsub.ts:325` | class `UnixSocketPubSub` | 158 frozen / 0 operational / 7 in scope | `rejected` | schema, transport | structure_gap, negative_control_risk |
| E01 | `lib/crewai/src/crewai/agent/core.py:223` | class `Agent` | 1 frozen / 0 operational / 1 in scope | `structural_candidate` | subtype | structure_gap |
| E02 | `harness2/core/recursion.py:360` | function `run_parallel` | 0 frozen / 10 operational / 4 in scope | `structural_candidate` | probe, evaluator | frozen_cue_miss, structure_gap |
| E03 | `rrsi/critic.py:28` | file `<file>` | 1 frozen / 5 operational / 6 in scope | `cue_only` | validation, regularization, budget | anchor_gap, structure_gap |
| E04 | `HarnessForge_4B/tools/half_select_harnesses.py:108` | function `pareto_front` | 4 frozen / 0 operational / 1 in scope | `pointcut_candidate` | constraint | structure_gap |
| E05 | `harnessx/core/builder.py:73` | class `HarnessBuilder` | 47 frozen / 0 operational / 2 in scope | `source_matched` | — | — |
| E06 | `HarnessForge_4B/evolved_pairs/pairs.yaml:1` | file `<file>` | 1 frozen / 0 operational / 1 in scope | `rejected` | evaluator, attribution | anchor_gap, structure_gap, trigger_gap, negative_control_risk |
| E07 | `recipe/gaia_evolver/run_meta.py:437` | function `run_evolve_loop` | 0 frozen / 2 operational / 1 in scope | `structural_candidate` | generator, archive | frozen_cue_miss, structure_gap |
| E09 | `src/carryon/main.py:176` | function `_amain` | 0 frozen / 6 operational / 6 in scope | `structural_candidate` | feedback | frozen_cue_miss, structure_gap |
| E10 | `evolve.py:5` | file `<file>` | 0 frozen / 18 operational / 18 in scope | `structural_candidate` | regression | frozen_cue_miss, anchor_gap, structure_gap |
| P01 | `src/agents/run_internal/run_loop.py:987` | function `start_streaming` | 20 frozen / 0 operational / 18 in scope | `source_matched` | — | — |
| P02 | `openhands-sdk/openhands/sdk/agent/parallel_executor.py:51` | class `ParallelToolExecutor` | 20 frozen / 0 operational / 15 in scope | `source_matched` | — | — |
| P03 | `libs/langgraph/langgraph/graph/state.py:131` | class `StateGraph` | 1 frozen / 0 operational / 1 in scope | `structural_candidate` | — | — |
| P04 | `python/packages/core/agent_framework/_middleware.py:860` | class `AgentMiddleware` | 552 frozen / 0 operational / 12 in scope | `pointcut_candidate` | short_circuit | structure_gap |
| P05 | `src/agents/models/chatcmpl_stream_handler.py:603` | method `handle_stream` | 0 frozen / 36 operational / 29 in scope | `structural_candidate` | cancellation, cleanup | frozen_cue_miss, structure_gap |
| P06 | `packages/core/src/session/inbox.ts:54` | file `<file>` | 0 frozen / 99 operational / 99 in scope | `structural_candidate` | — | frozen_cue_miss, anchor_gap |
| P07 | `src/agents/run_internal/prompt_cache_key.py:17` | class `PromptCacheKeyResolver` | 21 frozen / 21 operational / 16 in scope | `structural_candidate` | — | negative_control_risk |
| P08 | `src/agents/models/interface.py:150` | class `ModelProvider` | 1 frozen / 0 operational / 1 in scope | `structural_candidate` | subtype, error | structure_gap |
| P09 | `src/agents/tool.py:1641` | class `ToolSearchTool` | 35 frozen / 0 operational / 3 in scope | `source_matched` | — | — |
| P10 | `src/agents/sandbox/util/token_truncation.py:73` | function `truncate_with_token_budget` | 47 frozen / 0 operational / 5 in scope | `cue_only` | — | context_gap |
| P11 | `openhands-tools/openhands/tools/workflow/definition.py:1` | file `<file>` | 13 frozen / 0 operational / 13 in scope | `structural_candidate` | — | anchor_gap |
| P12 | `openhands-sdk/openhands/sdk/subagent/schema.py:202` | class `AgentDefinition` | 6 frozen / 0 operational / 6 in scope | `cue_only` | result, correlation | structure_gap |
| P13 | `openhands/automation/models.py:222` | class `AutomationRun` | 0 frozen / 1 operational / 1 in scope | `structural_candidate` | cursor, append | frozen_cue_miss, structure_gap |
| P14 | `openhands-sdk/openhands/sdk/conversation/state.py:342` | method `append_event` | 4 frozen / 0 operational / 1 in scope | `rejected` | schema, projector | structure_gap, negative_control_risk |
| P15 | `openhands-sdk/openhands/sdk/skills/skill.py:179` | class `Skill` | 17 frozen / 0 operational / 8 in scope | `source_matched` | — | — |
| P16 | `python/packages/core/agent_framework/_agent_hooks.py:3` | file `<file>` | 0 frozen / 190 operational / 190 in scope | `structural_candidate` | — | frozen_cue_miss, anchor_gap |
| P17 | `harnessx/processors/control/self_verify.py:95` | class `SelfVerifyProcessor` | 0 frozen / 3 operational / 3 in scope | `pointcut_candidate` | continuation | frozen_cue_miss, structure_gap |
| P18 | `harnessx/processors/control/loop_detection.py:38` | class `LoopDetectionProcessor` | 7 frozen / 0 operational / 4 in scope | `structural_candidate` | escalation | structure_gap |
| P19 | `packages/core/src/session/runner/max-steps.ts:1` | file `<file>` | 1 frozen / 1 operational / 2 in scope | `structural_candidate` | termination, escalation | anchor_gap, structure_gap |
| P20 | `examples/01_standalone_sdk/31_iterative_refinement.py:370` | function `run_iterative_refinement` | 34 frozen / 0 operational / 18 in scope | `cue_only` | retry, revision | structure_gap |
| P21 | `openhands-sdk/openhands/sdk/security/shell_parser.py:58` | function `parse` | 0 frozen / 12 operational / 3 in scope | `structural_candidate` | policy, schema | frozen_cue_miss, structure_gap |
| P22 | `packages/core/src/permission.ts:20` | file `<file>` | 0 frozen / 2 operational / 2 in scope | `structural_candidate` | floor | frozen_cue_miss, anchor_gap, structure_gap |
| P23 | `src/agents/sandbox/sandbox_agent.py:31` | class `SandboxAgent` | 16 frozen / 0 operational / 16 in scope | `structural_candidate` | profile, enforcement | structure_gap |
| P24 | `src/agents/tool.py:1498` | class `ShellTool` | 5 frozen / 23 operational / 4 in scope | `pointcut_candidate` | escalation | structure_gap |
| P25 | `src/gateway/method-scopes.ts:215` | function `resolveLeastPrivilegeOperatorScopesForMethod` | 152 frozen / 0 operational / 1 in scope | `source_matched` | — | — |
| P26 | `openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:861` | method `fork` | 1 frozen / 0 operational / 0 in scope | `pointcut_candidate` | — | hit_outside_scope |
| P27 | `packages/core/src/session/compaction.ts:298` | file `<file>` | 102 frozen / 0 operational / 102 in scope | `structural_candidate` | — | anchor_gap |
| P28 | `packages/memory/src/processors/observational-memory/observational-memory.ts:423` | class `ObservationalMemory` | 0 frozen / 117 operational / 6 in scope | `pointcut_candidate` | provenance | frozen_cue_miss, structure_gap |
| P29 | `openhands-sdk/openhands/sdk/agent/acp_agent.py:1815` | class `ACPAgent` | 9 frozen / 0 operational / 2 in scope | `pointcut_candidate` | adapter | structure_gap |
| R01 | `src/smolagents/agents.py:270` | class `MultiStepAgent` | 5 frozen / 0 operational / 3 in scope | `source_matched` | — | — |
| R02 | `packages/memory/src/processors/observational-memory/reflector-agent.ts:50` | function `buildReflectorSystemPrompt` | 0 frozen / 40 operational / 5 in scope | `source_matched` | — | frozen_cue_miss |
| W01 | `src/google/adk/agents/sequential_agent.py:91` | class `SequentialAgent` | 0 frozen / 13 operational / 9 in scope | `rejected` | stage, schema, validation, result | frozen_cue_miss, structure_gap, trigger_gap, negative_control_risk |
| W02 | `examples/agent_patterns/routing.py:10` | file `<file>` | 0 frozen / 4 operational / 4 in scope | `structural_candidate` | classifier | frozen_cue_miss, anchor_gap, structure_gap |
| W03 | `examples/agent_patterns/parallelization.py:7` | file `<file>` | 1 frozen / 0 operational / 1 in scope | `cue_only` | partition, worker, correlation | anchor_gap, structure_gap |
| W04 | `examples/01_standalone_sdk/42_file_based_subagents.py:24` | file `<file>` | 4 frozen / 0 operational / 4 in scope | `cue_only` | plan, synthesis | anchor_gap, structure_gap |
| W05 | `examples/agent_patterns/llm_as_a_judge.py:47` | function `main` | 3 frozen / 0 operational / 1 in scope | `structural_candidate` | revision | structure_gap |
| W06 | `lib/crewai/src/crewai/crew.py:1533` | method `_create_manager_agent` | 36 frozen / 0 operational / 8 in scope | `pointcut_candidate` | plan | structure_gap |
| W07 | `src/agents/handoffs/__init__.py:127` | class `Handoff` | 108 frozen / 0 operational / 25 in scope | `structural_candidate` | authority | structure_gap |

## Review queue

- **Frozen cue missed its own exemplar (operational cue recovered)** (17): C01, C02, E02, E07, E09, E10, P05, P06, P13, P16, P17, P21, P22, P28, R02, W01, W02
- **Anchor is a file or non-code unit** (12): E03, E06, E10, P06, P11, P16, P19, P22, P27, W02, W03, W04
- **Negative control fires on the anchor** (6): C01, C04, E06, P07, P14, W01
- **Structure roles missing** (34): C01, C02, C04, E01, E02, E03, E04, E06, E07, E09, E10, P04, P05, P08, P12, P13, P14, P17, P18, P19, P20, P21, P22, P23, P24, P28, P29, W01, W02, W03, W04, W05, W06, W07
- **Cue hit outside the anchored declaration** (1): P26

## How to read a gap

- **retrieval_gap** — neither cue family reaches the canonical file.
- **frozen_cue_miss** — the frozen regex does not match its own exemplar,
  but a signature cue does. This is a catalog/vocabulary disagreement.
- **hit_outside_scope** — a cue is present in the file but not in the
  declaration that contains the canonical line. The anchor and the cue
  point at different evidence units.
- **anchor_gap** — the anchor is a file, declaration, prompt, or
  configuration. It can locate the record but cannot evidence a full
  implementation.
- **structure_gap** — the anchor scope lacks signature roles. Treat it as
  a question: is the pointcut too strong, the anchor partial, or the
  signature too strict?
- **negative_control_risk** — the anchor scope matches the record's own
  contrast. Inspect before treating the anchor as an exemplar.

## Method

The audit anchors the canonical line to the smallest enclosing scope,
then runs the same dimension, negative-control, and verdict logic as
`analyze`. Retrieval applies the frozen regex plus any operational cues
stored with the signature; both use identifier-aware boundaries so
snake_case and camelCase identifiers match their token forms. This is a
direct exemplar check, not a repository-wide ranking.
