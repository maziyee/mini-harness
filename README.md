# mini-agent-harness

> 2026 Agent Harness 笔试题 · 从零实现一个最小可用 Agent。
> 后端：**Anthropic Messages API**（不实现 OpenAI-compatible）。
> 状态：P0 可运行（loop / 5 tools / session / context / memory / trace / CLI / tests）。

## 这是什么

一个不依赖 LangGraph / OpenHands / OpenClaw 等 Agent 框架的最小 Agent Runtime：

- **单循环**：模型 → 工具 → 模型 → 最终答案
- **工具注册**：名称 + 描述 + JSON Schema；6 个工具，`todo` 必做
- **Session 隔离**：同一用户的多个窗口互不影响，可持久化、可恢复
- **Context 管理**：最大轮次、工具结果截断、旧轮摘要
- **Memory**：偏好 / 事实 / 任务状态，关键词 + 时间召回
- **可观测**：JSONL trace，记录每次模型/工具调用
- **真实 LLM API**：Anthropic；不提交 API Key

## 快速开始

```bash
# 方式一：编辑 config.json（推荐，已 gitignore）
# 方式二：cp .env.example .env 并填 Key
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# REPL
python -m mini_agent --user alice

# 指定窗口
python -m mini_agent --user alice --session window-1

# 一次性执行
python -m mini_agent --user alice --session window-1 -p "帮我查北京天气，并记一条待办"
```

### 配置文件

`config.json` 是运行配置；`config.example.json` 是模板。两者都可编辑，但 `config.json` 已被 gitignore。

```json
{
  "llm": {
    "api_key": "",
    "auth_token": "",
    "base_url": "",
    "model": "your-model-id",
    "thinking": false,
    "show_thinking": true
  },
  "agent": {
    "max_turns": 20,
    "context_window": 200000
  },
  "storage": {
    "root": ""
  }
}
```

优先级：**CLI 参数 > `config.json` > 环境变量/`.env` > 默认值**。`null` 或空字符串表示“回退到下一层”。

`model` 填你实际可用的模型 ID：官方示例 `claude-sonnet-5-5`，网关示例 `deepseek-flash[1M]`；留空则读 `ANTHROPIC_MODEL`。

依赖 Python **3.10+**，运行时需要 `anthropic` SDK。
不想用 venv 时，只要系统已有 `anthropic` / `pytest`，可以直接：

```bash
PYTHONPATH=src python3 -m mini_agent --user alice
python3 -m pytest -q
```

详细接入、分功能验证和自测命令见 [docs/RUNBOOK.md](docs/RUNBOOK.md)。

## CLI 命令

| 命令 | 作用 |
|---|---|
| `/new [title]` | 新建 session（窗口） |
| `/sessions` | 列出当前用户所有 session |
| `/switch <id>` | 切换 session，恢复历史 |
| `/history [n]` | 查看最近 n 条消息 |
| `/todos` | 查看当前 session 待办 |
| `/memory` | 查看当前用户长期记忆 |
| `/trace` | 查看 trace 路径与最近事件 |
| `/quit` | 退出（自动保存） |

也可以用 `python -m mini_agent --list-sessions` 直接列 session。

## 目录结构

```
src/mini_agent/
├── cli.py                 # REPL、命令、窗口切换
├── loop.py                # 主循环
├── protocol.py            # 内部消息 / tool call / ModelResponse
├── prompt.py              # system prompt（静态 + 动态）
├── context.py             # token 估算、旧轮摘要
├── memory.py              # 长期记忆写入/召回
├── session.py             # 用户/窗口隔离、原子写
├── trace.py               # JSONL trace
├── llm/
│   ├── base.py            # LLMClient 协议
│   └── anthropic.py       # 唯一后端：Anthropic Messages API
└── tools/
    ├── executor.py        # 工具执行：schema 校验、dispatch、错误包装、截断
    ├── todo.py            # todo（必做）
    ├── memory.py          # 模型可调用的记忆 save/search/list
    ├── calculator.py      # 安全 AST 求值
    ├── search.py          # mock 本地语料
    ├── read_docs.py       # data/docs，带路径穿越保护
    └── weather.py         # mock 天气
```

## 运行时数据

默认都在仓库根目录，便于检查和演示：

```
sessions/<user>/<session>.json     # 窗口历史、summary、todos、turn_count
memory/<user>.json                 # 长期记忆
logs/<user>/<session>.jsonl        # trace
artifacts/                         # 被截断的完整工具结果
```

可以用 `MINI_AGENT_HOME` 把数据根目录移到别处。
`.gitignore` 会忽略运行时生成的 JSON/JSONL，只保留 `sessions/.gitkeep` 和 `memory/.gitkeep`。

## Session 设计

- 两级 key：`(user_id, session_id)`；窗口 1 和窗口 2 是两个独立文件。
- 每个 session 保存 `messages / summary / todos / turn_count / status`。
- 写入使用“临时文件 + `os.replace`”原子替换，进程被杀不会写坏历史。
- 落盘时机：压缩后、turn 结束、出错时；不在每个工具调用后重复写（内存态足够支撑下一轮模型调用）。
- 路径安全：`safe_id` 严格校验标识符；所有落盘路径走 `safe_path`（`resolve()` + 目录包含校验，防 `../` 和符号链接逃逸）。
- `--session window-1` 重启后直接恢复；`/switch` 在 REPL 内切换。

## Context 管理

- 单轮最多 8 个工具步；单 session 最多 20 轮（可配置）。
- 工具结果超过各自上限（1k–5k 字符）会截断，完整内容落 `artifacts/`。
- 估算 token 超过窗口的 70% 时，把旧轮次折成结构化摘要，保留最近 6 条消息。
- 摘要放在 system prompt 的 `## Conversation summary`，不插入消息列表，避免破坏 `tool_use` / `tool_result` 的配对。
- 压缩只在用户轮次边界触发，不在工具链中间切。
- 压缩前把旧轮原文归档到 `artifacts/transcripts/<user>/<session>-<ts>.jsonl`；归档失败则不压缩，避免静默丢历史。

## Thinking

- 可选开启 Anthropic 原生 extended thinking：`ANTHROPIC_THINKING=1`，`ANTHROPIC_THINKING_BUDGET=2048`。
- 输出可选：`--show-thinking` / `--no-show-thinking`，或 `ANTHROPIC_SHOW_THINKING=1`（默认打印）。
- 同一轮工具循环内，thinking block 保留在内存 `messages` 中回传给模型，保证 tool_result 连续性。
- 跨用户轮次默认**不回传**：turn 结束即剥离；磁盘也始终不写 thinking。
- 如果希望跨轮在内存里保留：`--keep-thinking-in-memory` 或 `ANTHROPIC_KEEP_THINKING_IN_MEMORY=1`。它仍然不落盘，进程重启后丢失。
- 落盘前由 `strip_thinking_blocks` 剥离 session / transcript / summary；trace 只记 `thought_chars`。
- 默认关闭；OpenAI-compatible 网关不一定支持 `thinking` 参数。

## Memory：召回时机与放置方式

- **存什么**：`preference`（偏好）、`fact`（稳定事实）、`task_state`（任务状态）。
- **谁来写**：模型可以通过 `memory` 工具主动 `save/search/list`；运行时对“记住 / 以后都 / 我喜欢 / 我的…是”做显式规则捕获，作为确定性兜底。
- **何时写**：只在用户明确说“记住 / 以后都 / 我喜欢 / 我的…是”时写入；不做全量自动记忆。
- **何时召回**：
  - session 开始时：偏好 + 活跃任务，top 5；
  - 每轮：与当前 query 关键词命中的记忆，top 3；
  - 写入/召回都记 trace，便于审计。
- **放在哪**：system prompt 的独立小节 `## Long-term memory`，带类型和日期，并注明“可能过时，当前指令优先”。
- **为什么**：记忆是背景，不是用户本轮指令；放 system 保持指令层级，带时间和来源便于纠错，限制 700 字符避免挤占当前任务。
- **存储格式**：`memory/<user>.json` 是 canonical（结构化字段、单文件原子写、去重/冲突）；每次写入同时生成只读 `memory/<user>.md` 镜像，方便人读、`grep` 和 `git diff`。镜像不反向导入，避免“手改 MD 与 JSON 冲突”。
- **为什么不用 MD 作为主存储**：关键词召回不依赖文件格式，JSON 的 `content` 同样可以分词/`grep`；MD 主存储需要 frontmatter 解析 + 索引重建 + 多文件一致性，代码量和边界成本都更高，对本题是过度设计。

## Trace

每个 session 一个 JSONL：

```json
{"event":"llm_request","model":"claude-sonnet-5-5","messages":3,"estimated_tokens":1200}
{"event":"tool_call","tool":"todo","call_id":"toolu_1","arguments":{"action":"add","content":"..."}}
{"event":"tool_result","tool":"todo","call_id":"toolu_1","ok":true,"chars":42}
{"event":"turn_end","turn":1,"tools_used":["todo"]}
```

trace 默认只记摘要：用户输入记 `chars + preview`，记忆写入记 `id/type + preview`，`llm_response` 只记 `tool_names`；完整的工具参数在 `tool_call` 事件里。不记录 API Key，工具结果只记长度/状态。

## 测试

```bash
pytest
```

单测使用 `FakeLLM`，不依赖网络；真实 Messages API 调用由 CLI 冒烟验证。

## 提交材料

- [AI Prompt 与问题解决记录](docs/AI_LOG.md)
- [接入真实 LLM 与自测 Runbook](docs/RUNBOOK.md)
- [5 道架构题回答](docs/ARCH_ANSWERS.md)
- [题目原文整理](docs/REQUIREMENTS.md)

## 设计原则

1. **从零**：核心 Runtime 自己写；只把模型 HTTP 调用委托给 Anthropic SDK。
2. **减法**：6 个工具、2 层压缩、3 类记忆；不做多 Agent / MCP / Web UI。
3. **可解释**：核心代码约 2300 行，每个模块都能在面试里讲清楚。
4. **可测试**：LLM 通过接口注入，单测离线跑。
5. **可观测**：每次模型/工具调用都有 trace。
