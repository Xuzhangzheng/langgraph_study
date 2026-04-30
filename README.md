# LangGraph Study

这是一个从 0 开始学习 `LangGraph` 的本地项目目录。

## 当前学习基线

- Python: `3.11.3`
- `langgraph==1.1.10`
- `langchain==1.2.15`
- `langchain-openai==1.2.1`
- `python-dotenv==1.2.2`
- `ipykernel==7.2.0`

为了尽量保证后续示例接口稳定：

- `requirements.txt` 固定了核心依赖版本
- `requirements.lock.txt` 记录了当前环境的完整安装结果

## 启动方式

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖（新机器复现）：

```powershell
python -m pip install -r requirements.txt
```

如果你要完全复现当前机器的依赖集合：

```powershell
python -m pip install -r requirements.lock.txt
```

## 后续建议

下一步可以创建：

1. `01_hello_langgraph.py`，从最简单的 `StateGraph` 开始。
2. `.env.example`，为后续接入模型 API 做准备。
3. `notebooks/` 目录，用于边学边实验。
