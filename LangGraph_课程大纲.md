# LangGraph 学习课程大纲（从 0 到可落地）

> 本文件为**唯一主大纲**；已吸收 `LangGraph_课程大纲_v2.md` 中的版本基线、硬约束、分阶段路线、统一验收标准（DoD）、里程碑，以及与仓库脚本一致的编号说明。`v2` 可作历史对照，**以本文件为准**。

## 课程说明

本大纲用于系统学习 LangGraph，目标是从基础概念逐步过渡到可上线的工程实践。

**核心强调**：

- 按固定依赖版本进行学习与实践
- 每课以**可运行示例**为主轴，并逐步满足下方 **DoD**（主路径 + 故障/边界 + 最小回归）
- 逐步构建完整的 Agent 工作流能力

每课除「具体内容」外，增加 **图结构** 说明，便于对照代码与 `invoke` 时的实际路径。

**代码文件记录时间（维护约定）**：

- 凡**新增**某一课、或对**该课主示例** `.py`（「对应文件」所指脚本）做**实质性改版**（逻辑、状态字段、对外 `invoke` 约定等），须在本文件对应课节中增加或更新一行：  
  **`代码文件记录时间`**：`YYYY-MM-DD HH:mm[:ss]`（建议填写保存脚本时的**本地时间**；纯文案/错别字可酌情不刷）
- 已落盘课程若从 Git 历史可追溯首次引入时刻，亦可与提交时间对齐后写入

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

## 分阶段路线（与下方第 1–21 课编号一致；第 21 课为选修补遗）

| 阶段 | 课号范围 | 主题侧重 |
|------|----------|----------|
| **A** | 第 1–4 课 | 图编排基础：线性、分支、循环、Mini-Agent |
| **A+（插学）** | 见下「专题」 | 状态与 **Reducer**（合并策略），对应 v2 单列的第 5 课思想 |
| **B** | 第 5–6 课 | 工具节点、LLM 与提示词分层（含多 Provider、条件边路由） |
| **C** | 第 7–12 课 | 消息与上下文、多工具、子图、并行、HITL、Checkpoint |
| **D** | 第 13–18 课 | 可观测、鲁棒性、评测、RAG、多 Agent、生产治理 |
| **E** | 第 19–20 课 | Capstone、复盘与进阶 |
| **F（选修）** | 第 21 课 | **`stream_mode` 全貌与扩展演示**：接续第 13 课，补足 `custom` / `messages` / `tasks` / `debug` 等语义与选型（见 **第21课** 正文） |

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

## 里程碑检查点（20 课主路径 + 第 21 课选修，与上表阶段对应）

- **里程碑 A**（第 4 课完成，且建议完成 **Reducer 插学**）：掌握线性、分支、循环与 Mini-Agent 骨架，理解状态合并的基本动机
- **里程碑 B**（第 6 课完成）：掌握工具节点与 LLM 接入（含环境配置、多 Provider、图上条件路由）
- **里程碑 C**（第 12 课完成）：掌握消息上下文、多工具路由、子图、并行、HITL 与 Checkpoint 基础
- **里程碑 D**（第 18 课完成）：掌握可观测、鲁棒性、评测、RAG、多 Agent 与生产治理的完整认知
- **里程碑 E**（第 20 课完成）：完成 Capstone 与复盘，能独立规划后续进阶（可对齐 v2 的 30/60/90 天路线，自选）
- **里程碑 F（选修）**（第 21 课）：能对照官方文档逐项说明 **`stream_mode` 全量取值**（`values` / `updates` / `custom` / `messages` / `checkpoints` / `tasks` / `debug` 及 **`stream_mode` 列表→`(mode, data)`** 语义），并说清第 13 课主脚本**为何只常驻三种**及各扩展模式的前提（如 LLM → `messages`，`StreamWriter` → `custom`）与适用场景。

---

## 第1课：`Hello LangGraph` 最小可运行图

**对应文件**：`01_hello_langgraph.py`  
**代码文件记录时间**：2026-04-28 14:43:52

**具体内容**：`StateGraph` 基本结构、`START/END`、节点函数输入输出、`invoke` 执行与状态流转。

**图结构**（线性）：

```text
START → prepare_message → summarize_result → END
```

**本课 DoD 提示**：运行脚本；对照 `state` 在节点间如何被更新。

---

## 第2课：条件分支与路由（Branching / Routing）

**对应文件**：`02_branching_graph.py`  
**代码文件记录时间**：2026-04-28 15:02:37

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
**代码文件记录时间**：2026-04-28 21:03:55

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
**代码文件记录时间**：2026-04-28 21:38:20

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
**代码文件记录时间**：2026-04-28 21:49:24

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
**代码文件记录时间**：2026-04-30 08:52:24  
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
**代码文件记录时间**：2026-04-30 12:17:39  
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

**对应文件**：`08_multi_tool_routing_graph.py`  
**代码文件记录时间**：2026-04-30 14:09:13  
**Java 对照**：`java/.../l08_multi_tool_routing/Lesson08App.java`（LangGraph4j）  
**图导出**：`08_multi_tool_routing_graph.png`（失败时 `.mmd`）。

**具体内容**：在一张图内放置多个工具（算术、时间、静态词典）+ **兜底分支**；`select_tools` 定义**固定优先级**与 `route_note` 策略说明；**每轮 invoke 只执行其中一个工具**；工具支路经 `finalize_result` 把**该次**工具输出统一排版（与第 5 课同义，不是多工具结果合并）；未命中走 `fallback_reply`。

**图结构**：

```text
START → select_tools ──route_tools──→ calculator_tool ──┐
                      │               time_tool ────────┼──→ finalize_result → END
                      │               lookup_tool ──────┤
                      └               fallback_reply ─────────────→ END
```

**本课 DoD 提示**：算术/时间/词典/闲聊兜底各跑一例；故意错误表达式观察 `finalize_result` 中的 `tool_error`；对照运行 Java 同级示例（需本机 Maven + JDK17）。

---

## 第9课：子图（Subgraph）与模块化编排

**对应文件**：`09_subgraph_modular_graph.py`  
**代码文件记录时间**：2026-04-30 14:26:34  
**Java 对照**：`java/.../l09_subgraph_modular_graph/Lesson09App.java`（子图 `compile()` 后由包装节点 `invoke`）  
**图导出**：`09_subgraph_modular_graph.png`（失败时 `.mmd`）。

**具体内容**：将流程拆为子图 `sub_alpha`（normalize→brief）与 `sub_beta`（elaborate）；主图 `gate_input` 门禁后串联子图并 `assemble_final`；Python 侧 `add_node("sub_*", compiled)` 嵌入子图。

**图结构**（逻辑视图）：

```text
START → gate_input ──route──→ sub_alpha → sub_beta → assemble_final → END
                       └──→ bad_input ─────────────────────────────→ END
```

**补充（生产向）**：`09b_order_subgraph_input_schema_graph.py` — OMS 全量状态 + WMS 子图 `WmsSubState` + 支付对账节点 `input_schema=PaymentReconInput`。**代码文件记录时间**（09b）：2026-04-30 16:37:25。

---

## 第10课：并行分支与聚合（Fan-out / Fan-in）

**对应文件**：`10_parallel_fanin_graph.py`  
**代码文件记录时间**：2026-04-30 16:38:57  
**Java 对照**：`java/.../l10_parallel_fanin_graph/Lesson10App.java`（与 04c 一样用静态多分边；动态 `Send` 见 l04b 注释）  
**图导出**：`10_parallel_fanin_graph.png`（失败时 `.mmd`）。

**具体内容**：在 **04c 静态 fan-out** 与 **reducer** 前提上，强调 **fan-in**：并行分支只往列表型槽位 `fragments` 追加；**屏障**（`add_edge([branch_1,…], "aggregate")`）后由 **单节点** `aggregate` 写入标量 `final_report`，避免多路争用同一汇总字段；简要提示并行度与聚合成本权衡。

**图结构**：

```text
START → fan_out ──→ branch_1 ──┐
              └──→ branch_2 ──┼──→ aggregate → END
              └──→ branch_3 ──┘
```

**本课 DoD 提示**：对照 04c 区分「列表 reducer」与「单点汇总」；跑 Python/Java 观察 `stream` 中屏障前后的 chunk；若未装图渲染依赖可仅用 `.mmd`。

---

## 第11课：人机协同（Human-in-the-loop）

**对应文件**：`11_human_in_the_loop_graph.py`  
**代码文件记录时间**：2026-04-30 17:19:11  
**Java 对照**：`java/.../l11_human_in_the_loop_graph/Lesson11App.java`（`BlockingQueue` 模拟外部审批；**完整 `interrupt()+Command` 以 Python 为准**）  
**图导出**：`11_human_in_the_loop_graph.png`（失败时 `.mmd`）。

**具体内容**：关键节点 `interrupt()` 挂起；`InMemorySaver` + `thread_id` + `Command(resume=...)` 恢复；分支 **通过 / 驳回 / 修改回流**（修改回到 `agent_step` 后再送审）。注意：恢复时含 `interrupt` 的节点从**节点头**重入，前面代码应幂等。

**图结构**：

```text
START → agent_step → human_review ──→ continue_flow → END
                              ├──→ end_rejected → END
                              └──→ agent_step（回流）
```

**本课 DoD 提示**：跑通「首次挂起 → resume edit → 再次挂起 → resume approved」；另开 `thread_id` 演示 `rejected`；第 12 课将扩展持久化 checkpoint。

**补充（控制台交互）**：`11b_human_in_the_loop_console_graph.py` — 与 11 课同图，用 `input()` 循环决定每次 `Command(resume=...)`，便于本地亲手试 HITL。**代码文件记录时间**（11b）：2026-04-30 18:35:17。

---

## 第12课：持久化与记忆（Checkpoint / Memory）

**对应文件**：`12_checkpoint_memory_graph.py`  
**代码文件记录时间**：2026-04-30 22:23:49  
**Java 对照**：（无）本课以 Python `CompiledGraph.get_state` / `get_state_history` / `update_state` 为主；LangGraph4j 对照见各版本文档。  
**图导出**：`12_checkpoint_memory_graph.png`（失败时 `.mmd`）。

**具体内容**：**短期状态**由 `checkpointer`（本课 `InMemorySaver`）按 **`thread_id`** 分链存储；演示 **`get_state`**（最新快照）、**`get_state_history`**（可追溯 checkpoint 链）、**同线程第二次 `invoke`** 的合并与再跑、`update_state` 人工打补丁；**长期记忆**仍建议图外存储（向量库/SQL 等），与 checkpoint 分工。

**图结构**（业务拓扑；持久化由 `compile(checkpointer=...)` 注入）：

```text
START → normalize → enrich → summarize → END
```

**本课 DoD 提示**：观察 Alice/Bob 两 `thread_id` 互不串线；列一段 `get_state_history`；改 SQLite/Postgres checkpointer 须另装官方扩展包，接口仍为 `checkpointer` + `thread_id`。

---

## 第13课：可观测性与调试

**对应文件**：`13_observability_debug_graph.py`  
**代码文件记录时间**：2026-05-01 16:28:00  
**Java 对照**：`java/.../l13_observability_debug_graph/Lesson13App.java`（`logging` + `stream` chunks；以 Python `stream_mode` 为准）  
**图导出**：`13_observability_debug_graph.png`（失败时 `.mmd`）。

**具体内容**：标准库 **`logging`** 做节点关联日志；**`CompiledGraph.stream(..., stream_mode=[...])`** 实操 `updates` / `values` / `checkpoints`；**`print_mode`** 仅镜像控制台；**`RunnableConfig`** 的 `tags` / `metadata`（与 **`thread_id`** 并存）；故障路径：空输入或含 **`boom`** → `stub_error` 写入 `diagnostics`；仍需 **`get_graph().draw_mermaid_png()`** 做结构自检。

**图结构**：

```text
START → gate ──route_after_gate──→ process → finalize → END
                            └──→ stub_error → END
```

**本课 DoD 提示**：主路径、`boom` / 空格三例跑通；对照 `updates` 与 `values` 的输出形状差异；看一眼 `checkpoints` 事件中 `checkpoint_id` / `next`；可与第 12 课 `get_state_history` 一起理解「离线读链 vs 在线流事件」。

**延伸（选修）**：`stream_mode` 在 **`langgraph==1.1.10`** 下**不限于**本课示例的三种；其余模式（`custom` / `messages` / `tasks` / `debug`）的语义、前置条件与教学取舍见 **第 21 课**。

---

## 第14课：错误处理与鲁棒性工程

**对应文件**：`14_error_handling_robustness_graph.py`  
**代码文件记录时间**：2026-05-01 17:25:50  
**Java 对照**：`java/.../l14_error_handling_robustness_graph/Lesson14App.java`（与 Python 同拓扑：`risk_status` 路由 + 退避重试环）  
**图导出**：`14_error_handling_robustness_graph.png`（失败时 `.mmd`）。

**具体内容**：节点内 **不抛未捕获异常** → 写入 `risk_status` + `diagnostics` 再路由；**`flaky`** 触发 **指数退避（cap）** 与 **条件边循环** 回到 `risky_call`；**`fatal` / `boom` / 空输入** 走 **降级支路** `degraded_finish`；本课 **文件头说明** 中交代 **幂等、超时、熔断** 在生产侧的通常摆放（客户端 / 中间件）。

**图结构**：

```text
START → risky_call ──route──→ finalize_success → END
                  │ backoff_then_retry → risky_call（循环）
                  └──→ degraded_finish → END
```

**本课 DoD 提示**：Happy / `flaky`（观察 `attempt` 与两次 `backoff`）/ `fatal` / 空输入四例跑通；理解「可重入节点 + state 驱动路由」与第 13 课 `stub_error` 的递进关系。

**补充（真实业务场景）**：`14b_payment_capture_resilience_graph.py` — 以 **PSP 支付请款（Capture）** 为背景：503/限流等 **可重试**、拒付/风控 **硬失败**、空报文 **校验降级**；图拓扑与 14 课一致，字段更名为 `correlation_id` / `capture_payload` / `psp_attempt` 等。**代码文件记录时间**（14b）：2026-05-01 17:27:04  
**Java 对照**（14b）：`java/.../l14b_payment_capture_resilience/Lesson14bApp.java`  
**图导出**（14b）：`14b_payment_capture_resilience_graph.png`（失败时 `.mmd`）。

---

## 第15课：评测体系与质量门禁

**对应文件**：`15_evaluation_quality_gate_graph.py`  
**代码文件记录时间**：2026-05-01 18:33:54  
**Java 对照**：`java/src/main/java/study/langgraph/lessons/l15_evaluation_quality_gate_graph/Lesson15App.java`（SUT + 编排图 + 黄金套件；`RunnableConfig.thread_id` 以 Python 为准）  
**图导出**：运行脚本后同目录 `15_evaluation_quality_gate_sut_graph.png`、`15_evaluation_quality_gate_orchestration_graph.png`（失败时对应 `.mmd`）。

**具体内容**：**SUT（客服意图→草稿回复）** 与 **评测代码解耦**：`GoldenCase` 黄金用例集、对 `CompiledGraph.invoke` 终态做 **intent 精确匹配 + reply 子串断言**；**质量门禁** `MIN_PASS_RATIO`（默认 1.0）失败则 **退出码 1**；**薄编排图** `bootstrap_run → regression_worker → gate_finalize` 演示 CI 批处理骨架（worker 内循环调用 SUT，生产可换队列/`Send`）；`EVIL_CASE` 演示故意错误期望；契约说明：**状态字段名为「接口不变」的可执行定义之一**。

**图结构**（SUT — 主业务图）：

```text
START → normalize_message → classify_intent ──route_intent──→ draft_refund   ──┐
                         │                    │              draft_shipping ├──→ seal_response → END
                         │                    │              draft_general  ──┤
                         │                    └──→ draft_invalid ──────────────┘
```

**图结构**（评测编排 — 薄包装）：

```text
START → bootstrap_run → regression_worker → gate_finalize → END
```

**本课 DoD 提示**：跑通 Python 脚本（含编排图二次汇总）；故意 `EVIL_CASE=True`（Python）或 `EVIL_CASE=true`（Java）观察门禁失败；对照双端状态键与 `intent` 枚举；有 Maven 时运行 `Lesson15App`。

---

## 第16课：RAG + LangGraph 基础整合

**对应文件**：`16_rag_langgraph_graph.py`  
**代码文件记录时间**：2026-05-01 22:49:27  
**Java 对照**：`java/src/main/java/study/langgraph/lessons/l16_rag_langgraph_graph/Lesson16App.java`（与 Python 同拓扑：`normalize` 门禁 + `retrieve` / `rerank` / `generate` + 无命中与非法输入收口）  
**图导出**：运行脚本后同目录 `16_rag_langgraph_graph.png`（失败时 `16_rag_langgraph_graph.mmd`）。

**具体内容**：**RAG 流水线节点化**：`normalize_query`（空查询门禁）→ `retrieve_lexical`（内存 KB 词元重叠粗排，含 `FORCE_NO_HIT` 桩）→ **条件边函数** `route_after_retrieve`（非节点：仅在「有/无 `retrieved_chunks`」间路由）→ 无命中 → `seal_no_evidence_answer`；有命中 → `rerank_heuristic`（标题命中加权精排）→ `generate_with_evidence`（`mode=llm` 时按 **`LLM_PROVIDER`** 与第 6 课一致：`openai` 走 `langchain-openai`，**`ark`** 走 **`volcenginesdkarkruntime`**；默认 `fallback` 模板归纳）；状态显式携带 **`retrieved_chunks` / `context_chunks` / `citations`**。

**图结构**：

```text
START → normalize_query ──route_after_normalize──→ retrieve_lexical ──route_after_retrieve──→ rerank_heuristic → generate_with_evidence → END
                          │                                                      └→ seal_no_evidence_answer → END
                          └→ seal_invalid_query → END
```

**本课 DoD 提示**：跑通退款 / 429 限流失两例主路径 + `FORCE_NO_HIT` + 空查询；对照 `diagnostics` 与 Python/Java 状态键；有 Maven 时可运行 `Lesson16App`。

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

**图结构**：无固定运行时图；可将第1–19课的典型图并列对比，形成「学习路径图」文档；**第 13 课 streaming 的完整补遗见第 21 课（选修）**。

---

## 第21课（选修）：`stream_mode` 全貌、前置条件与扩展演示

**对应文件**：（规划中；落盘时可在 `13_observability_debug_graph.py` 内以**可选段落/开关**扩展，或单开 `21_stream_mode_supplement_graph.py`，满足 DoD 后再填写 **代码文件记录时间**）  
**Java 对照**：（规划中，与 Python 扩展范围对齐即可）

**与第 13 课分工**：

- **第 13 课主脚本**聚焦三条「与 checkpoint / 日常排错最顺」的观测线：**`updates`**（节点增量）、**`values`**（全状态快照）、**`checkpoints`**（与第 12 课持久化语义对齐的在线事件），并配合 **`logging`**、`RunnableConfig` 的 `tags` / `metadata`。
- **未在同一脚本内默认展开**其余模式，是出于**教学收敛**（避免单课变成「流式 API 大全」），而非 API 限制。

**`stream_mode` 全量取值（须以本仓库固定版本 `langgraph==1.1.10` 及官方 streaming 文档为准）**：

| 取值 | 要点 | 第 13 课未默认演示的常见原因（大纲约定） |
|------|------|------------------------------------------|
| `values` | 每步后完整状态 | 第 13 课**已演示** |
| `updates` | 每步各节点返回的增量 | 第 13 课**已演示** |
| `checkpoints` | checkpoint 创建节拍，与 `get_state` 类信息对齐 | 第 13 课**已演示** |
| `custom` | 节点内通过 **`StreamWriter`** 等机制推送自定义数据 | 多一段 API 与运行时注入，宜在理解 `updates`/`values` 后单开最小示例 |
| `messages` | 图内 **LLM 调用**时的 token/消息流与 metadata | 第 13 课图为无 LLM 的纯节点，缺产生源；宜接第 6～7 课环境再演示 |
| `tasks` | 任务起止、并行任务等粒度事件 | 与 `updates` 并存时信息量大，宜在需要排查调度/并行时再开 |
| `debug` | 每步极尽详细的调试负载 | 默认跑通易刷屏，宜本机按需单次打开 |

**列表形式 `stream_mode=[...]`**：可同时订阅多种模式；流式产出一般为 **`(mode, data)`**（与第 13 课对 `updates`/`values`/`checkpoints` 的拆包方式一致），具体形态以当前版本行为为准。

**具体内容（第 21 课应覆盖的学习成果）**：

1. 能不看讲义，口述各 `stream_mode` **解决什么问题**、与 **`invoke`** 黑盒输出的差异。
2. 能说明 **`custom` / `messages` / `tasks` / `debug`** 各自需要的**图内前提**（Writer、LLM、并行与体积）。
3. 最小可运行补充示例（规划落盘后）：至少各选 **一种**扩展模式做 **Happy Path**（例如 `custom` 或 `messages` 二选一 + 文档化 `tasks`/`debug` 的手动触发方式），并保留 **Failure Path** 或「无 LLM 时 `messages` 为空」的边界说明。

**图结构**：无固定统一拓扑；以「在第 13 课图或最小 LLM 子图上加观测点」为主，落盘时在对应 `.py` 文件头用 ASCII 补充即可。

**本课 DoD 提示**：以 **第 13 课已跑通**为前提；对照官方 **Streaming** 文档核对枚举与 `print_mode` / `subgraphs` 等参数；扩展脚本落盘后补 **代码文件记录时间** 与本表 **对应文件** 字段。

---

## 当前学习进度

- **本轮学习起点**：自 **第 7 课**起实操推进（第 7～11 课主脚本「代码文件记录时间」见各课节；本地时间以你机器为准）
- 已完成：第 1 课～第 **16** 课（含第 **16** 课 RAG：检索 / 重排 / 生成与可解释引用）
- 建议插学（可选）：**专题 A+ Reducer**（`04b_reducer_graph.py`，与第 5 课前/第 10 课并行搭配）
- **选修（延伸）**：**第 21 课**已将 **`stream_mode` 全量取值**、与第 **13** 课脚本分工及扩展落地方式写入大纲正文；**示例脚本仍在规划中**，可与第 13 课对照阅读，主学习路径仍以第 1～20 课为准。
- 待开始：**第 17** 课（多 Agent 协作）

**DoD 自检（第 1–16 课）**：每课 Python 可运行；第 8 课起建议对照 Java（第 12 课无 Java，第 **13～16** 课有 Java；**14b** 亦有 Java）；第 9 课主图嵌套子图；第 10 课列表合并 + 单点 `aggregate`；第 11 课 `thread_id` 与 `resume`；第 12 课 `thread_id` 与 `get_state` / `history`；第 13 课 `stream` 多 mode + 节点日志关联；第 14 课 `risk_status` 三元路由 + `backoff_then_retry` 环；**14b** 对照支付域语义与 14 课抽象版同构；第 **15** 课 SUT + 黄金套件 + `MIN_PASS_RATIO` 门禁 + 评测编排图与 SUT **双 PNG 导出**；第 **16** 课 RAG 条件边（无命中 / 非法输入）+ `citations` 与 chunk 列表契约 + 图 PNG 导出。
