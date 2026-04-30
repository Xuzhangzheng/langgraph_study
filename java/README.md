# Java 对照课（LangGraph4j）

本目录与仓库根目录的 Python 示例**按课号对照**，使用 **[LangGraph4j](https://github.com/langgraph4j/langgraph4j)**（`org.bsc.langgraph4j`，Maven Central），**不是** LangChain 官方 Java SDK；与 Python `langgraph==1.1.10` 仅作概念对齐。

## 环境要求

- **JDK 17+**（Temurin / Liberica 等）。本机若仍是 JDK 8，请安装 17 并令 `java -version` 指向新 JDK。
- **Apache Maven 3.9+**（或 IDE 自带 Maven）。可将 Maven 解压到任意目录并把 `bin` 加入 `PATH`。
- 可选：**winget** 安装（若网络/证书正常）  
  `winget install EclipseAdoptium.Temurin.17.JDK -e --source winget`  
  再自行安装 Maven。

## 配置 LLM（第 6～7 课）

与 Python 相同，可在**仓库根目录**放置 `.env`（与 `06_llm_integration_graph.py` 同级），`CourseEnv` 会在从 `java/` 目录运行时自动尝试读取上级目录的 `.env`。

常用变量：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`LLM_PROVIDER`（`openai` / `ark`）、`ARK_*` 等（与 Python 大纲一致）。

**说明**：Java 侧未集成火山 Ark 官方 SDK，`LLM_PROVIDER=ark` 时为占位/摘要行为；真实 Ark 调用请在本机扩展 HTTP 或 SDK。

## 构建

```text
cd java
mvn -q compile
```

## 运行某一课（exec-maven-plugin）

默认主类为第 1 课。其他课示例：

```text
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l01_hello_langgraph.Lesson01App
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l02_branching_graph.Lesson02App
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l03_loop_graph.Lesson03App
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l04_mini_agent_graph.Lesson04App
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l04b_reducer_graph.Lesson04bApp
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l04c_static_fanout_graph.Lesson04cApp
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l04d_reducer_strategies.Lesson04dApp
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l05_tool_call_graph.Lesson05App
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l06_llm_integration_graph.Lesson06App
mvn -q exec:java -Dexec.mainClass=study.langgraph.lessons.l07_messages_context_graph.Lesson07App
```

## 与 Python 脚本的对应关系

| 包路径 | Python |
|--------|--------|
| `lessons.l01_hello_langgraph` | `01_hello_langgraph.py` |
| `lessons.l02_branching_graph` | `02_branching_graph.py` |
| `lessons.l03_loop_graph` | `03_loop_graph.py` |
| `lessons.l04_mini_agent_graph` | `04_mini_agent_graph.py` |
| `lessons.l04b_reducer_graph` | `04b_reducer_graph.py`（Java 用静态三分支代替 `Send` 动态 fan-out，见类注释） |
| `lessons.l04c_static_fanout_graph` | `04c_static_fanout_graph.py` |
| `lessons.l04d_reducer_strategies` | `04d_reducer_strategies.py` |
| `lessons.l05_tool_call_graph` | `05_tool_call_graph.py`（计算器：白名单校验 + Nashorn 脚本引擎） |
| `lessons.l06_llm_integration_graph` | `06_llm_integration_graph.py` |
| `lessons.l07_messages_context_graph` | `07_messages_context_graph.py` |

## 依赖版本（本 `pom.xml`）

- `langgraph4j-bom`：**1.8.14**
- `langchain4j-open-ai`：**1.13.0**（与 LangGraph4j 父工程常用线一致）
- `dotenv-java`：**3.0.0**
- `nashorn-core`：**15.4**（JDK 17 无内置 JS 引擎时的 `eval` 计算演示）
