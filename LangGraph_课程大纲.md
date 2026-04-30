# LangGraph 学习课程大纲（从 0 到可落地）

> 本文件为**唯一主大纲**；已吸收 `LangGraph_课程大纲_v2.md` 中的版本基线、硬约束、分阶段路线、统一验收标准（DoD）、里程碑，以及与仓库脚本一致的编号说明。`v2` 可作历史对照，**以本文件为准**。

## 课程说明

本大纲用于系统学习 LangGraph，目标是从基础概念逐步过渡到可上线的工程实践。

**核心强调**：

- 按固定依赖版本进行学习与实践
- 每课以**可运行示例**为主轴，并逐步满足下方 **DoD**（主路径 + 故障/边界 + 最小回归）
- 逐步构建完整的 Agent 工作流能力

每课除「具体内容」外，增加 **图结构** 说明，便于对照代码与 `invoke` 时的实际路径。

---

## 版本与接口基线（须严格保持）

- Python: `3.11.3`
- `langgraph==1.1.10`
- `langchain==1.2.15`
- `langchain-openai==1.2.1`
- `python-dotenv==1.2.2`
- `ipykernel==7.2.0`
- `volcengine-python-sdk[ark]==5.0.25`（第六课火山 Ark 官方 SDK 路径）

> 原则：示例、状态字段与对外约定以当前依赖能力为准。升级依赖须单独做兼容性评审，避免破坏「接口不变」约束（与 v2 精神一致）。

---

## 课程硬约束（吸收 v2「精修版」）

- 固定依赖版本学习，不随意升级接口
- 每课尽量具备：**可运行主路径（Happy Path）**、**至少一条故障或边界路径（Failure Path）**、**最小回归方式**（手工步骤或一条命令 / 小脚本）
- 课程演进以 **可复现、可调试、可扩展** 为优先

---

## 分阶段路线（与下方第 1–20 课编号一致）

| 阶段 | 课号范围 | 主题侧重 |
|------|----------|----------|
| **A** | 第 1–4 课 | 图编排基础：线性、分支、循环、Mini-Agent |
| **A+（插学）** | 见下「专题」 | 状态与 **Reducer**（合并策略），对应 v2 单列的第 5 课思想 |
| **B** | 第 5–6 课 | 工具节点、LLM 与提示词分层（含多 Provider、条件边路由） |
| **C** | 第 7–12 课 | 消息与上下文、多工具、子图、并行、HITL、Checkpoint |
| **D** | 第 13–18 课 | 可观测、鲁棒性、评测、RAG、多 Agent、生产治理 |
| **E** | 第 19–20 课 | Capstone、复盘与进阶 |

**与 v2（22 课）编号差异的说明**：v2 将 **Reducer** 设为正式第 5 课，并将工具/LLM 后移。本仓库脚本已按 **第 5 课 = 工具（`05_*`）、第 6 课 = LLM（`06_*`）** 固化，故将 v2 的 Reducer **吸收为阶段 A+ 插学专题**，不整体改号，避免与现有文件名冲突。

**v2 中另两项扩展，建议在主大纲课号内消化**（不必单开新课号亦可）：

- **结构化输出与解析防护**（v2 第 9 课）：可在实现第 7–8 课时增加「解析失败回退 / 格式重试」节点或 sidecar 示例
- **执行模式与运行控制**（v2 第 13 课：`invoke` / `stream` / `RunnableConfig`、`thread_id`）：可在第 12 课 Checkpoint 或第 13 课可观测性中一并实践

---

## 专题（插学）：状态模型与合并机制（Reducer）

**对应文件**：`04b_reducer_graph.py`（运行后可选生成 `04b_reducer_graph.png` / `.mmd`）  
**建议时机**：完成第 4 课后、进入第 5 课前；或与第 10 课「并行分支」学习前搭配，更易体会「多写入同一字段」问题。

**具体内容**：多个节点或并行写入同一 `state` 字段时的冲突；使用 `Annotated` 与 **reducer** 声明合并策略；「冲突复现 → reducer 修复」最小示例。

**图结构**（示意）：`parallel_writers → merge_via_reducer → validate_state → END`（实现时以官方 API 为准）。

**验收**：能用自己的话解释「为什么同一字段在复杂图里必须声明合并策略」，并跑通最小示例。

---

## 每课统一验收标准（DoD）

每节课结束**建议**满足：

1. 有可运行主示例（Happy Path）
2. 有故障或边界示例（Failure Path），或在教案/注释中明确如何触发
3. 有最小回归验证（可手工或脚本）
4. 维护本课 **「接口不变」清单**：状态字段名、与外部约定的节点入参（若暴露为 API）

规划中、尚未落盘的课程，在编写示例时一体满足上述四条。

---

## 里程碑检查点（20 课制，与上表阶段对应）

- **里程碑 A**（第 4 课完成，且建议完成 **Reducer 插学**）：掌握线性、分支、循环与 Mini-Agent 骨架，理解状态合并的基本动机
- **里程碑 B**（第 6 课完成）：掌握工具节点与 LLM 接入（含环境配置、多 Provider、图上条件路由）
- **里程碑 C**（第 12 课完成）：掌握消息上下文、多工具路由、子图、并行、HITL 与 Checkpoint 基础
- **里程碑 D**（第 18 课完成）：掌握可观测、鲁棒性、评测、RAG、多 Agent 与生产治理的完整认知
- **里程碑 E**（第 20 课完成）：完成 Capstone 与复盘，能独立规划后续进阶（可对齐 v2 的 30/60/90 天路线，自选）

---

## 第1课：`Hello LangGraph` 最小可运行图

**对应文件**：`01_hello_langgraph.py`

**具体内容**：`StateGraph` 基本结构、`START/END`、节点函数输入输出、`invoke` 执行与状态流转。

**图结构**（线性）：

```text
START → prepare_message → summarize_result → END
```

**本课 DoD 提示**：运行脚本；对照 `state` 在节点间如何被更新。

---

## 第2课：条件分支与路由（Branching / Routing）

**对应文件**：`02_branching_graph.py`

**具体内容**：`add_conditional_edges`、路由函数设计、状态驱动的动态分支、默认分支策略。

**图结构**（分类后三路分支，各自到 END）：

```text
START → analyze_input ──route_next_step──→ weather_node ──→ END
                          │                math_node    ──→ END
                          └                chat_node    ──→ END
```

**本课 DoD 提示**：三组输入各走一条分支；可尝试无法命中关键词的输入观察默认分支。

---

## 第3课：循环与重试（Loop / Retry）

**对应文件**：`03_loop_graph.py`

**具体内容**：循环回边、完成条件设计、`max_iterations` 安全退出、防止无限循环。

**图结构**（检查后可回到写作节点，或进入结束节点）：

```text
START → write_or_expand_draft → check_completion ──route_after_check──→ continue_writing → write_or_expand_draft（循环）
                          │                                              finish → finish_node → END
                          └
```

---

## 第4课：Mini-Agent 工作流（分支 + 循环 + 自检）

**对应文件**：`04_mini_agent_graph.py`

**具体内容**：任务分类、候选答案生成、评估反馈、失败重试、通过收敛。

**图结构**（先分支，再生成—评估—条件边重试或结束）：

```text
START → classify_task ──route_task──→ qa_prepare ──┐
                     └ rewrite_prepare ────────────┤
                                                   ↓
                                          generate_answer → evaluate_answer
                                                   ↑              │
                                                   │              └──route_after_evaluation──→ finish → END
                                                   └ retry_generate（回到 generate_answer）
```

**本课 DoD 提示**：QA 与改写各跑一例；关注 `attempt` 与 `quality_score` 的迭代过程。

---

## 第5课：工具调用基础（Tool Node）

**对应文件**：`05_tool_call_graph.py`

**具体内容**：把“计算器/时间查询”等函数封装成工具节点、工具输入输出协议、工具失败处理。

**图结构**（决策后多工具，再汇总）：

```text
START → decide_tool ──route_tool──→ calculator_tool ──┐
                     │                time_tool       ├──→ finalize_result → END
                     └                no_tool_node ───┘
```

---

## 第6课：LLM 接入与提示词分层

**对应文件**：`06_llm_integration_graph.py`  
**图导出**：运行脚本后可在同目录生成 `06_llm_integration_graph.png`（失败时回退 `06_llm_integration_graph.mmd`）。

**具体内容**：接入 `langchain-openai` 与火山 Ark SDK、系统提示词与任务提示词分层、按 `LLM_PROVIDER` 切换、运行后导出图图片。

**图结构**（双层条件边：先按 mode，再按 provider / 配置校验）：

```text
START → init_request ──route_mode──→ fallback_node → END
                     │
                     └ load_llm_config ──route_provider──→ call_openai_node → END
                                                     │      call_ark_node   → END
                                                     └      config_error_node → END
```

**本课 DoD 提示**：`mode=fallback` 与 `mode=llm` 各跑一例；配置错误应进入 `config_error_node`；运行后检查是否生成 `06_llm_integration_graph.png` 或 `.mmd`。

---

## 第7课：消息状态与对话上下文

**对应文件**：`07_messages_context_graph.py`  
**图导出**：运行后同目录 `07_messages_context_graph.png`（失败时 `07_messages_context_graph.mmd`）。

**具体内容**：消息列表状态管理、`add_messages` 与 `RemoveMessage` 裁剪历史、单轮到多轮的状态演进（手动传递 `messages`；持久化见第 12 课）。

**图结构**（典型多轮对话骨架）：

```text
START → append_user_message ──route──→ trim_history → generate_with_context → END
                        └──（空输入）→ empty_input_node ────────────────────→ END
```

（`generate_with_context` 内直接追加 `AIMessage`，与大纲中 append_assistant 一步合并。）

**本课 DoD 提示**：fallback 多轮与空输入分支必绿；尝试 `max_messages_to_keep=2` 观察记忆丢失；配置齐全时跑 `mode=llm`。

## 第8课：多工具路由与工具选择策略

**对应文件**：（规划中）

**具体内容**：多个工具并存时的路由设计、工具选择器、回退策略与兜底答复。

**图结构**：

```text
START → select_tools / route_tools ──→ tool_A → merge_results ──→ END
                    │                  tool_B ↗
                    └                  fallback_reply → END
```

---

## 第9课：子图（Subgraph）与模块化编排

**对应文件**：（规划中）

**具体内容**：把复杂流程拆成子图、子图复用、主图-子图接口设计、分层工作流架构。

**图结构**（逻辑视图）：

```text
START → subgraph_A（内部自有节点与边）→ subgraph_B → END
```

主图只暴露与子图约定的 state 字段，子图内部结构可独立演进。

---

## 第10课：并行分支与聚合（Fan-out / Fan-in）

**对应文件**：（规划中）

**具体内容**：并行执行多个节点、结果汇总聚合、冲突合并策略、性能与复杂度权衡。

**图结构**：

```text
START → fan_out ──→ branch_1 ──┐
              └──→ branch_2 ──┼──→ aggregate → END
              └──→ branch_n ──┘
```

---

## 第11课：人机协同（Human-in-the-loop）

**对应文件**：（规划中）

**具体内容**：在关键节点等待人工确认、人工纠错回流、审批/中断/继续机制设计。

**图结构**：

```text
START → agent_step → human_review ──→ approved → continue_flow → END
                              └──→ rejected / edit → agent_step（回流）
```

---

## 第12课：持久化与记忆（Checkpoint / Memory）

**对应文件**：（规划中）

**具体内容**：状态持久化、会话恢复、短期记忆与长期记忆边界、可重放执行。

**图结构**（与业务图正交：在 compile 或运行时挂 checkpoint store，节点拓扑可与第4–6课类似，多会话通过 thread_id 区分）：

```text
业务图：START → … → END
持久化：每次节点前后可写入 / 恢复 checkpoint（由 LangGraph 运行时与 checkpointer 配置完成）
```

---

## 第13课：可观测性与调试

**对应文件**：（规划中）

**具体内容**：节点级日志规范、状态快照、执行轨迹分析、常见故障定位方法。

**图结构**：不改变业务拓扑；在现有各课图结构上增加日志、追踪与 `get_graph()` 可视化导出等辅助手段。

---

## 第14课：错误处理与鲁棒性工程

**对应文件**：（规划中）

**具体内容**：异常捕获、重试退避、降级策略、幂等性、超时与熔断思路。

**图结构**（在关键节点旁路增加恢复路径）：

```text
START → risky_node ──success──→ END
              └──error──→ retry_or_degrade → END
```

---

## 第15课：评测体系与质量门禁

**对应文件**：（规划中）

**具体内容**：构建用例集、自动评测指标、回归测试、版本升级的兼容性检查（保证接口不变）。

**图结构**（评测可与主应用分离；若做在图内则为批处理）：

```text
START → load_cases → for_each_case → invoke_graph → score → report → END
```

---

## 第16课：RAG + LangGraph 基础整合

**对应文件**：（规划中）

**具体内容**：检索节点、重排节点、生成节点串联，打造可解释的检索增强问答流。

**图结构**：

```text
START → retrieve → rerank（可选）→ generate_answer → END
```

（可加上「无结果则直接答复」的条件边。）

---

## 第17课：多 Agent 协作图

**对应文件**：（规划中）

**具体内容**：Planner / Executor / Critic 协作模式、消息协议、冲突解决与收敛策略。

**图结构**：

```text
START → planner → executor ──→ critic ──pass──→ END
                         ↑         └──revise──┘（循环回 executor 或 planner）
```

---

## 第18课：生产化部署与版本治理

**对应文件**：（规划中）

**具体内容**：配置分环境管理、依赖锁定、接口契约、上线前检查清单、监控与回滚策略。

**图结构**：以运维与发布流程为主，应用层仍为多课组合的 LangGraph；可单独画「配置加载 → 健康检查 → 服务就绪」辅助图，与业务 Agent 图并列。

---

## 第19课：课程项目（Capstone）

**对应文件**：（规划中）

**具体内容**：从 0 到 1 搭建一个可演示的 LangGraph 应用（含工具、记忆、评测、日志、容错）。

**图结构**（综合示意，实际以项目为准）：

```text
START → classify → [工具分支 | 直答分支] → （可选循环自检）→ persist / log → END
```

---

## 第20课：复盘与进阶路线

**对应文件**：（无单独示例，复盘用）

**具体内容**：课程知识图谱回顾、项目代码审阅、后续进阶方向（高并发、复杂编排、企业级治理）。

**图结构**：无固定运行时图；可将第1–19课的典型图并列对比，形成「学习路径图」文档。

---

## 当前学习进度

- 已完成：第 1 课～第 7 课（含第 7 课消息状态、`add_messages`、裁剪与多轮演示）
- 建议插学（可选）：**专题 A+ Reducer**（`04b_reducer_graph.py`，与第 5 课前/并行课搭配）
- 待开始：第 8 课（多工具路由与工具选择策略）

**DoD 自检（第 1–7 课）**：每课脚本均可直接运行；第 2–7 课建议对照注释触发展示/故障分支（如非法表达式、未配置 Key、`mode=fallback`、空用户输入、`max_messages_to_keep` 裁剪等）。
