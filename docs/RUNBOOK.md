# 接入真实 LLM 与自测 Runbook

> 目标：从零配置一个真实模型，跑通文本、工具、session、memory、compaction、trace、thinking，并知道每一步看哪里。
> 不涉及任何真实 API Key；所有 Key 只放本地 `.env`，不提交。

---

## 1. 安装 / 运行方式

### 方式 A：venv（推荐，隔离依赖）

```bash
cd mini-agent-harness
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m mini_agent --help
pytest
```

### 方式 B：直接用系统 Python（不建 venv）

只要系统里已有依赖，就可以直接跑，不需要 venv：

```bash
cd mini-agent-harness

# 检查依赖
python3 -c "import anthropic, pytest; print('ok')"

# 不安装包，用 PYTHONPATH 指向 src
PYTHONPATH=src python3 -m mini_agent --list-sessions

# 单测（conftest 会自己加 src 到 sys.path）
python3 -m pytest -q
```

当前环境实测：

```text
Python 3.10.12
anthropic 0.123.0
pytest 6.2.5
```

如果系统缺依赖：

```bash
pip install --user anthropic pytest
```

如果想让 `mini-agent` 命令全局可用：

```bash
pip install --user -e .
mini-agent --help
```

不安装时，统一用：

```bash
PYTHONPATH=src python3 -m mini_agent ...
```

`PYTHONPATH=src` 只在“没有 pip install -e .”时需要；装了包之后可以省略。

`pytest` 已配置 `-p no:anyio`，单测全部离线，不需要 API Key。

---

## 2. 配置模型

有两种方式，任选其一；也可以混用。

优先级：

```text
CLI 参数 > config.json > 环境变量 / .env > 内置默认值
```

### 2.0 config.json（推荐）

仓库里已经有：

- `config.json`：实际读取的配置，已 gitignore；
- `config.example.json`：模板/参考。

编辑 `config.json`：

```json
{
  "llm": {
    "api_key": "",
    "auth_token": "",
    "base_url": "",
    "model": "claude-sonnet-5-5",
    "max_tokens": 4096,
    "timeout": 60,
    "max_retries": 3,
    "thinking": false,
    "thinking_budget": 2048,
    "show_thinking": true,
    "keep_thinking_in_memory": false
  },
  "agent": {
    "max_steps": 8,
    "max_turns": 20,
    "context_window": 200000
  },
  "storage": {
    "root": ""
  }
}
```

规则：

- `null` 或空字符串 → 回退到环境变量/默认值；
- CLI 参数（如 `--model`、`--max-turns`）覆盖 config；
- `storage.root` 非空时覆盖 `MINI_AGENT_HOME`；
- 指定其他配置文件：`--config /path/to/config.json` 或 `MINI_AGENT_CONFIG=...`；
- `config.json` 可以放 Key，但它已被 gitignore；更稳妥是把 Key 放 `.env`。

### 2.1 官方 Anthropic

```bash
ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_MODEL=claude-sonnet-5-5
# 留空
ANTHROPIC_BASE_URL=
ANTHROPIC_AUTH_TOKEN=
```

如果 shell 里已经存在 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`，先清掉，避免覆盖 `.env`：

```bash
unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN
```

### 2.2 Anthropic-compatible 网关

```bash
ANTHROPIC_BASE_URL=https://your-gateway.example.com/anthropic
ANTHROPIC_AUTH_TOKEN=your-token
ANTHROPIC_MODEL=your-model-id
```

有些网关用 `x-api-key`，有些用 Bearer token；本项目优先使用 `ANTHROPIC_AUTH_TOKEN`，没有时用 `ANTHROPIC_API_KEY`。

检查当前 shell（不要打印 Key 值）：

```bash
env | grep -E '^ANTHROPIC_(BASE_URL|MODEL|THINKING|SHOW_THINKING)=' || true
test -n "$ANTHROPIC_API_KEY" && echo "API key set"
test -n "$ANTHROPIC_AUTH_TOKEN" && echo "auth token set"
```

### 2.3 可选：thinking

```bash
ANTHROPIC_THINKING=1
ANTHROPIC_THINKING_BUDGET=2048
ANTHROPIC_SHOW_THINKING=1
```

要求模型支持 Anthropic 原生 extended thinking；不支持的网关会报 API 错误，默认保持 `0`。

### 2.4 数据目录隔离（推荐测试时用）

```bash
MINI_AGENT_HOME=/tmp/mini-agent-test
```

这样 session/memory/logs 不写进仓库，测试完直接删目录。

---

## 3. 最小冒烟

### 3.1 文本

```bash
MINI_AGENT_HOME=/tmp/mini-agent-test \
python -m mini_agent --user test --session smoke-1 -p "只回复两个字：你好"
```

预期：输出 `你好`。

### 3.2 工具调用

```bash
MINI_AGENT_HOME=/tmp/mini-agent-test \
python -m mini_agent --user test --session smoke-1 -p "请调用 todo 工具添加一条待办：买牛奶。添加后告诉我结果。"
```

预期：

- 模型返回 `tool_use`；
- runtime 执行 `todo`；
- 最终文本包含“买牛奶”；
- `sessions/test/smoke-1.json` 里 `todos` 有记录。

检查：

```bash
python - <<'PY'
import json
d=json.load(open("/tmp/mini-agent-test/sessions/test/smoke-1.json"))
print(d["todos"])
print([m["role"] for m in d["messages"]])
PY
```

### 3.3 Trace

```bash
python scripts/show_trace.py /tmp/mini-agent-test/logs/test/smoke-1.jsonl
```

预期能看到：

```text
[turn] user_message
[turn] llm_request
[turn] llm_response ... tools=[todo]
[turn] tool_call todo(...)
[turn] tool_result todo -> ok
[turn] turn_end
```

---

## 4. 分功能验证

### 4.1 Calculator

```bash
python -m mini_agent --user test --session calc -p "计算 (12 + 8) * 3"
```

预期最终答案包含 `60`；trace 里有 `calculator`。

### 4.2 Search + Read docs

```bash
python -m mini_agent --user test --session docs -p "先搜索 Anthropic 工具调用协议，再读 agent-notes.md 的 Agent Loop 部分。"
```

预期：

- `search` 返回标题/摘要/来源；
- `read_docs` 返回带行号内容；
- trace 里有 `search`、`read_docs`。

### 4.3 Weather（mock）

```bash
python -m mini_agent --user test --session weather -p "北京 2026-10-26 天气怎么样？"
```

预期：`weather` 返回 mock 天气（多云/9-17℃）。

### 4.4 Memory

写入：

```bash
python -m mini_agent --user test --session mem-1 -p "请把项目代号 mini-agent 保存到长期记忆。"
```

检查：

```bash
cat /tmp/mini-agent-test/memory/test.json
cat /tmp/mini-agent-test/memory/test.md
```

跨 session 召回：

```bash
python -m mini_agent --user test --session mem-2 -p "我的项目代号是什么？"
```

预期：回答包含 `mini-agent`；trace 里有 `memory_recall`。

### 4.5 Session 隔离

```bash
# 窗口 1
python -m mini_agent --user test --session window-1 -p "记一条待办：给张三回邮件"

# 窗口 2
python -m mini_agent --user test --session window-2 -p "记一条待办：写周报"

# 查看
python -m mini_agent --user test --list-sessions
```

预期两个 session 的 todos 独立：

```bash
python - <<'PY'
import json
for s in ("window-1","window-2"):
    d=json.load(open(f"/tmp/mini-agent-test/sessions/test/{s}.json"))
    print(s, d["todos"])
PY
```

### 4.6 重启恢复

先跑一轮，再重新启动同一个 session：

```bash
python -m mini_agent --user test --session window-1 -p "刚才的待办是什么？"
```

预期：模型能看到历史待办；不会新建 window-1。

### 4.7 Context 压缩

把窗口调小，制造压缩：

```bash
python -m mini_agent --user test --session compact-demo \
  --context-window 2000 -p "先记住：项目代号是 mini-agent。然后我们聊 10 轮。"
```

检查：

```bash
python - <<'PY'
import json
d=json.load(open("/tmp/mini-agent-test/sessions/test/compact-demo.json"))
print("summary:", d["summary"])
print("messages:", len(d["messages"]))
PY

ls /tmp/mini-agent-test/artifacts/transcripts/test/
```

预期：

- `summary` 非空；
- `messages` 变少；
- transcript 文件存在，包含旧轮原文；
- trace 里有 `compact`。

### 4.8 Thinking（可选）

```bash
ANTHROPIC_THINKING=1 ANTHROPIC_SHOW_THINKING=1 \
python -m mini_agent --user test --session think-1 -p "计算 17*23，并解释步骤。"
```

预期：

- 终端出现 `[thinking]`；
- `sessions/test/think-1.json` 里**没有** `thinking` block；
- trace 只有 `thought_chars`，没有思考正文。

关闭输出：

```bash
python -m mini_agent --user test --session think-1 --no-show-thinking -p "..."
```

---

## 5. 自己写测试

### 5.1 单元测试（推荐，不花钱）

参考 `tests/test_loop.py` 的 `FakeLLM`：

```python
from helpers import FakeLLM, text_response, tool_response
from mini_agent.context import ContextManager
from mini_agent.loop import AgentLoop
from mini_agent.memory import MemoryStore
from mini_agent.protocol import ToolCall
from mini_agent.session import SessionStore
from mini_agent.tools import build_default_tools
from mini_agent.trace import TraceLogger


def test_my_case(tmp_path):
    call = ToolCall("c1", "todo", {"action": "add", "content": "测试"})
    responses = [
        tool_response([call]),
        text_response("已添加"),
    ]
    store = SessionStore(tmp_path / "sessions")
    memory = MemoryStore(tmp_path / "memory")
    loop = AgentLoop(
        llm=FakeLLM(responses),
        tool_executor=build_default_tools(),
        session_store=store,
        memory_store=memory,
        context=ContextManager(context_window=1_000_000),
        trace_factory=lambda u, s: TraceLogger(u, s, root=tmp_path / "logs"),
    )
    session = store.create("alice", "s1")

    assert loop.run_turn(session, "记一条待办") == "已添加"
    assert session.todos[0]["content"] == "测试"
```

运行：

```bash
pytest tests/test_loop.py -q
pytest -k "memory or thinking" -q
```

### 5.2 工具级测试

```python
from mini_agent.protocol import ToolCall
from mini_agent.session import Session
from mini_agent.tools import build_default_tools
from mini_agent.tools.executor import ToolContext

executor = build_default_tools()
ctx = ToolContext("alice", Session(id="s1", user_id="alice"))
result = executor.execute(
    ToolCall("c1", "calculator", {"expression": "1+2*3"}), ctx
)
assert "7" in result.content
```

### 5.3 真实 API 脚本

```python
from mini_agent.llm.anthropic import AnthropicClient
from mini_agent.protocol import ToolCall

client = AnthropicClient()
resp = client.complete(
    system="You are a calculator.",
    messages=[{"role": "user", "content": "计算 17*23，调用 calculator。"}],
    tools=[{
        "name": "calculator",
        "description": "Evaluate arithmetic.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    }],
)
print(resp.text, resp.tool_calls)
```

真实测试不要断言完整字符串；断言：

- `tool_calls` 里出现预期工具名；
- 最终文本包含关键数字/关键词；
- 磁盘状态（todos/memory/session）符合预期。

---

## 6. 常见问题

| 现象 | 原因/处理 |
|---|---|
| `build backend is missing the 'build_editable' hook` | pip/setuptools 太旧，不支持 PEP 660；用 `PYTHONPATH=src` 直接跑，或在 venv 里 `pip install --upgrade pip setuptools wheel` 后再 `pip install -e .` |
| `ANTHROPIC_API_KEY is not set` | `.env` 没被读取；在仓库根目录运行，或直接 export |
| 401/403 | Key 类型与网关不匹配；官方用 API key，网关可能用 auth token |
| 设置了 `.env` 但仍走旧网关 | shell 里已有 `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`；`unset` 后再试 |
| model not found | `ANTHROPIC_MODEL` 与账号/网关支持的模型不一致 |
| 工具没被调用 | 模型不支持 tools，或提示不够明确；先直接说“请调用 todo 工具” |
| memory 没召回 | 没有写入成功，或关键词无重叠；看 `memory/test.json` 和 trace `memory_recall` |
| 压缩没触发 | `--context-window` 太大；调到 2000 左右制造压缩 |
| thinking 报错 | 模型/网关不支持原生 thinking；设 `ANTHROPIC_THINKING=0` |
| thinking 没显示 | `ANTHROPIC_SHOW_THINKING=0` 或用了 `--no-show-thinking` |
| pytest 插件报错 | 已配置 `-p no:anyio`；仍报错时显式加 `pytest -p no:anyio` |
| `Couldn't open that file` | 这是编辑器链接路径问题，不是代码错误；用绝对路径打开 |

---

## 7. 清理测试数据

```bash
rm -rf /tmp/mini-agent-test
```

如果用 `MINI_AGENT_HOME` 指向仓库，清理时只删测试 user：

```bash
rm -rf sessions/test memory/test.json memory/test.md logs/test
```

不要删 `.env` 以外的用户数据。

---

## 8. 安全

- `.env` 已被 `.gitignore` 忽略；
- 不要把 Key 粘到 prompt、trace、issue、聊天记录；
- trace 不记录 Authorization/API Key；
- 测试用独立 `MINI_AGENT_HOME`，避免污染真实 session/memory。

---

## 9. 一句话

> 先 `pip install -e ".[dev]"`，再在 `.env` 配 Key/模型，最后用 `-p` 跑文本、todo、memory、compaction 四条冒烟；单测用 `FakeLLM`，真实测试只看工具名、关键词和磁盘状态，不断言完整输出。
