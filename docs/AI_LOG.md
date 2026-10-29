# AI Prompt 与问题解决记录

> 项目：`mini-agent-harness`（2026 Agent Harness 笔试）
> 时间：2026-10-25 ～ 2026-10-29

---

## 1. 使用原则

1. **先有自己的方案，再让 AI 挑毛病。** Prompt 里带上判断，要求它给反例、风险和替代方案。
2. **核心 runtime 人工 review。** AI 可以生成初版、测试和文档草稿，但 loop、工具协议、持久化、安全边界必须逐行检查。
3. **记录拒绝的理由。** 被拒绝的建议比被采纳的更能体现判断。
4. **不泄露敏感信息。** Prompt 里不放 API Key、用户数据、公司内部资料；日志里也不放。
5. **可复现。** 记录日期、阶段、关键 prompt 摘要、采纳结论和落地位置。

---

## 2. AI 在项目中的角色

| AI 做了什么 | 人做了什么 |
|---|---|
| 读题、拆分验收项、整理需求 | 确认题目边界和优先级 |
| 对比参考设计，给出最小实现方案 | 决定保留/裁剪哪些能力 |
| 生成代码初版、测试用例、文档草稿 | 逐模块 review、修复边界、删过度设计 |
| 以“面试官/攻击者”视角找风险 | 决定最终架构、取舍和验收标准 |
| 生成 mock 数据、示例 trace | 检查是否泄露、是否符合题意 |

**未使用 AI 的地方：**

- 不在 prompt 中放真实 API Key；
- 不让 AI 直接决定最终架构；
- 不让 AI 代写架构题的最终判断；
- 不把“AI 说可以”当作验收依据，必须跑测试/真实 API。

---

## 3. 关键决策时间线

> 按实际推进顺序排列；同一天内按讨论顺序，不按自然时间戳。
> 说明：P0 已经包含基础 memory；6–10 是后续对安全、存储、规则和接口的深入决策，因此 memory 讨论在 context 之前。

| # | 时间 | 阶段 | 我给 AI 的 prompt（摘要） | AI 的建议 | 结论 | 理由 | 落地 |
|---|---|---|---|---|---|---|---|
| 1 | 10-25 | 读题 | 提取题目要求，按 vibe coding / 架构设计 / 交付物拆分 | 两部分；70 分门槛；5 模块选 1 | 采纳 | 作为计划输入 | `docs/REQUIREMENTS.md` |
| 2 | 10-25 | 范围 | 对比参考实现，列出本题最小能力 | 保留 loop/tools/session/context/memory/trace；砍 MCP/多 Agent/skills/流式 | 部分采纳 | 保留骨架；压缩和 memory 重写为最小版 | `README.md` |
| 3 | 10-26 | 后端 | 只实现 Anthropic 还是同时做 OpenAI-compatible | 两套适配会翻倍工作量，先做一套 | 采纳 | 题目只要求真实 LLM API；Anthropic 原生 tool_use 更直接 | `llm/anthropic.py` |
| 4 | 10-26 | P0 | 生成 loop / tools / session / context / memory / trace / CLI | 给出完整最小实现 | 部分采纳 | 核心代码逐行 review；删掉不必要的抽象 | `src/mini_agent/` |
| 5 | 10-26 | 验证 | 跑单测 + 真实 API 冒烟 | 文本、todo 工具、memory 写入可通过 | 采纳 | 确认闭环可用 | `tests/`、`logs/` |
| 6 | 10-27 | 路径安全 | `safe_id` 只防文件名穿越，是否足够 | 拆成 `safe_id`（标识符）+ `safe_path`（目录包含/符号链接） | 采纳 | 两者防不同问题；symlink 逃逸需要 resolve + containment | `util.py`、`session.py`、`memory.py`、`trace.py` |
| 7 | 10-27 | Memory 存储 | JSON、Markdown 还是模型自己写记忆 | JSON canonical + 只读 Markdown 镜像 | 采纳 | 关键词召回不依赖格式；Markdown 主存储要 frontmatter/索引/一致性 | `memory.py` |
| 8 | 10-27 | Memory 写入规则 | 自动抽取还是显式规则触发 | 只对“记住 / 以后都 / 我喜欢 / 我的…是”做高精度捕获 | 采纳 | 宁可少记，不要记错；自动抽取容易污染 | `memory.py` |
| 9 | 10-27 | Memory 数据结构 | 参考 `MemoryEntry` 和我们的 `MemoryRecord` 是否要一致 | 按存储/写入路径差异做字段映射，不强行同构 | 采纳 | 参考是 Markdown 文件视图，我们是 JSON 记录；按需扩展 id/时间/置信度/status | `memory.py` |
| 10 | 10-27 | Memory 接口 | 参考让模型写记忆，是否保留 | 加受限 `memory` 工具（save/search/list）+ `MemoryBackend` 协议；规则捕获兜底 | 采纳 | 保留模型自主权，避免暴露通用 `write_file` | `tools/memory.py`、`memory.py` |
| 11 | 10-27 | Context | 压缩会替换 session 的 messages，旧原文会不会丢 | 压缩前归档到 `artifacts/transcripts/`；归档失败则不压缩 | 采纳 | 对齐参考的 `write_transcript`；session 保存压缩后的工作状态 | `context.py` |
| 12 | 10-27 | Prompt / 工具提示词 | 工具 schema、静态 prompt、动态工具列表三处不一致，怎么收敛 | schema 只写“是什么”；静态 prompt 写“何时用”；删除 dynamic 重复列表 | 采纳 | 参考实现也是两层；避免三处漂移 | `prompt.py`、`tools/*.py` |
| 13 | 10-28 | 运行时校验 | 参考的 `execute_tool` 没有运行时 schema 校验，要不要补 | 加 JSON Schema 子集校验；错误作为 `tool_result` 回给模型 | 采纳 | 模型参数可能错；集中校验比每个 handler 各自处理更一致 | `tools/executor.py` |
| 14 | 10-28 | Trace | `llm_response` 重复记录 tool 参数、user_message 记全文，是否过多 | 删除重复参数；用户输入/记忆写入改为 chars + preview | 采纳 | 减少重复和 PII；完整参数仍在 `tool_call` 事件 | `loop.py` |
| 15 | 10-28 | 落盘频率 | 一次带工具的 turn 写 3 次 session，是否过度 | 去掉 per-action save 和工具批次后的 save，只保留 turn 边界/压缩/错误 | 采纳 | 内存态足够下一轮模型调用；中途落盘不能安全恢复 | `loop.py`、`tools/todo.py` |
| 16 | 10-29 | Thinking | 自定义 `<thought>` 标签 vs Anthropic 原生 thinking | 改为原生 `thinking` block；输出到 CLI；落盘前剥离；跨轮默认不回传 | 采纳 | 原生带签名/计费/协议语义；自定义标签不可信 | `protocol.py`、`llm/anthropic.py`、`session.py`、`loop.py` |
| 17 | 10-29 | Thinking 输出 | 思考输出是否可选；跨轮是否回传 | `--show-thinking` / `--no-show-thinking`；同轮保留；跨轮默认剥离；`--keep-thinking-in-memory` 仅内存 | 采纳 | 输出可配；同轮保连续性；跨轮不污染上下文且永不落盘 | `cli.py`、`loop.py` |
| 18 | 10-29 | 命名/调用 | `ToolRegistry` 名字体现不出执行职责；`ToolContext` 每个工具都重建 | 改 `ToolExecutor`；`ToolContext` 每轮构造一次复用 | 采纳 | 名字贴职责；减少无意义对象创建 | `tools/executor.py`、`loop.py` |
| 19 | 10-29 | 配置 | 环境变量太分散，希望一个文件改所有设置 | 增加 `config.json` + `config.example.json`；CLI > config > env > defaults | 采纳 | 单文件可改；config.json 已 gitignore | `config.py`、`cli.py`、`llm/anthropic.py` |
| 20 | 10-29 | 架构题 | 5 个模块各选 1 题，写在一个文件里 | 提供 M1-Q2 / M2-Q1 / M3-Q1 / M4-Q2 / M5-Q1 的提纲和取舍 | 采纳 | 用实现和边界做证据，不堆名词 | `docs/ARCH_ANSWERS.md` |

---

## 4. 关键问题与解决

> 本节按主题排列，不严格按时间线；时间顺序见第 3 节。

### 问题 1：工具提示词三处不一致

**现象**

- 工具 schema 的描述写了 “Use it when...”；
- 静态 prompt 只提了 todo/memory；
- 动态 prompt 又把 6 个工具描述列了一遍。

**原因**

同一件事（工具怎么用）被写在三个地方，没有单一事实来源。

**方案**

- 工具 schema 只回答“是什么、参数是什么”；
- 静态 prompt 增加 `## Tool selection`，回答“什么时候用哪个工具”；
- 删除 dynamic prompt 里的 `## Available tools` 重复列表；
- 模型仍然通过 API 的 `tools` 字段拿到完整 schema。

**验证**

- `test_prompt.py` 断言存在 `## Tool selection`、不存在 `## Available tools`；
- 6 个工具名都出现在 tool selection 里。

**取舍**

- 不在 prompt 里重复参数 schema：省 token、避免漂移；
- 代价是模型需要同时看 system 和 tools 两个字段，但这正是 Anthropic 的设计。

---

### 问题 2：运行时 schema 校验

**现象**

模型可能传错参数：缺必填、类型错、enum 非法、范围超限。参考实现主要靠 handler 自己 try/except。

**方案**

在 `ToolExecutor.execute()` 执行 handler 之前，用 `validate_value()` 做 JSON Schema 子集校验：

- type / required / properties / enum / items；
- minItems / maxItems、minLength / maxLength；
- integer 的 minimum / maximum；
- 拒绝 bool 冒充 integer/number。

错误不抛异常，而是作为 `tool_result` 回给模型，模型下一轮可以自己改。

**验证**

```text
calculator {}
→ Invalid arguments: $: missing required field 'expression'

calculator {"expression": 123}
→ Invalid arguments: $.expression: expected string

todo {"action": "explode"}
→ Invalid arguments: $.action: must be one of [...]

search {"query": "x", "top_k": 99}
→ Invalid arguments: $.top_k: must be <= 5
```

**取舍**

- 只做子集，不引入 `jsonschema` 依赖；
- 业务校验仍由 handler 负责（例如 todo id 是否存在），runtime 校验不替代业务逻辑。

---

### 问题 3：路径穿越与符号链接逃逸

**现象**

`session_id`、`user_id` 会变成文件名；`read_docs` 的 path 来自模型。只做字符串检查不够。

**方案**

拆成两层：

1. `safe_id`：1–64 字符、首字符字母/数字、拒绝路径分隔符/前导点/结尾点空格/Windows 保留名；
2. `safe_path`：`resolve()` 后 `relative_to(root)`，拒绝 `../` 和符号链接逃逸。

落地点：

- `sessions/<user>/<session>.json`；
- `memory/<user>.json`；
- `logs/<user>/<session>.jsonl`；
- `read_docs` 的 `data/docs`。

**验证**

- 路径穿越测试；
- symlink 逃逸测试；
- Windows 保留名测试。

**取舍**

- 单机单人 demo 够用；
- 仍存在 TOCTOU（检查后到写入前换 symlink）的理论窗口；要彻底解决需要 `O_NOFOLLOW` + dirfd，本题不做。

---

### 问题 4：Context 压缩会丢旧原文

**现象**

`maybe_compact` 会把旧 messages 折叠成 summary，然后替换 `session.messages`。如果没有额外落盘，旧原文就丢了。

**方案**

压缩前归档：

```text
artifacts/transcripts/<user>/<session>-<timestamp>.jsonl
```

顺序：

1. 生成 summary；
2. 归档 old messages；
3. 归档成功才替换 `session.messages`；
4. 归档失败则不压缩，保留完整历史。

摘要放在 system prompt 的 `## Conversation summary`，不插入 messages，避免破坏 `tool_use/tool_result` 配对。

**验证**

- 归档文件存在且包含旧消息；
- 压缩后 session 只保留最近消息 + summary；
- 按 token 和消息数两种触发都有测试。

**取舍**

- transcript 是平铺 JSONL，没有轮转/索引；长期运行需要保留期策略；
- session 保存的是压缩后的工作状态，不是完整历史；完整历史在 transcript。

---

### 问题 5：Memory 的存储与写入路径

**争论**

- JSON：结构化字段、原子写、去重/冲突容易，但人读性一般；
- Markdown：人读/grep/diff 友好，但需要 frontmatter 解析、索引重建、多文件一致性；
- 模型写记忆：保留自主权，但需要受限工具或通用 `write_file`。

**最终方案**

- `memory/<user>.json` 作为 canonical：`id/type/content/created_at/last_used_at/source_session/confidence/status`；
- 每次写入同时生成只读 `memory/<user>.md` 镜像，供人读/grep/diff；
- 模型可以调用 `memory` 工具 `save/search/list`；
- 运行时对“记住 / 以后都 / 我喜欢 / 我的…是”做显式规则捕获，作为确定性兜底；
- 召回：关键词 + 时间衰减 + 类型权重；注入 system prompt，带“可能过时”提示。

**为什么不做**

- Markdown 主存储 + `MEMORY.md` 索引 + sideQuery 语义预取，代码量和不确定性都明显更高；
- 本题要的是“能记住、能召回、能解释”，不是完整 memory OS。

**验证**

- JSON 去重、召回、冲突状态、MD 镜像、工具写入都有测试；
- `test_readonly_markdown_mirror` 验证镜像随 JSON 更新。

---

### 问题 6：Trace 过度记录

**现象**

`llm_response` 记录了完整 `tool_calls`（含 arguments），下一步 `tool_call` 又记录一遍；`user_message` 记全文；`memory_write` 记完整内容。

**方案**

- `llm_response` 只记 `tool_names`；
- `user_message` 记 `chars + preview`；
- `memory_write` 记 `id/type + chars + preview`；
- 完整工具参数只出现在 `tool_call` 事件；
- 工具结果只记 `ok + chars`，不记全文。

**结果**

一次模型步 2–4 行 trace；一个 8 步工具轮约 15–25 行；足够回放，不泄露全文。

---

### 问题 7：Thinking 的重复、原生性和落盘

**现象 1：重复**

早期实现里 `ModelResponse.thought` 存一份思考，`raw_content` 里还保留 `<thought>` 标签；loop 把 `raw_content` 写进 session，导致思考被持久化/回放。

**现象 2：自定义标签**

`<thought>` 是自定义文本约定，没有 API 语义、没有签名，可能被伪造。

**最终方案**

- 改为 Anthropic 原生 `thinking` / `redacted_thinking` block；
- `_block_to_dict` 保留 `thinking`、`signature`、`redacted_thinking.data`；
- `ModelResponse.thought` 从原生 thinking block 汇总；
- CLI 通过 `on_thought` 输出；
- `Session.to_dict`、transcript、summary 输入都走 `strip_thinking_blocks`，**磁盘永远没有 thinking**；
- 同一轮工具循环保留 thinking block，保证 API 连续性；
- 跨轮默认剥离；`--keep-thinking-in-memory` 可跨轮保留，但仅内存。

**验证**

- `test_thinking_text_from_content`；
- `test_strip_thinking_blocks_preserves_text_and_tool_use`；
- `test_save_strips_thinking_blocks`；
- `test_thinking_is_output_but_not_persisted`；
- `test_keep_thinking_in_memory_across_turns`。

**取舍**

- 跨轮不持久化 thinking，进程重启后推理链丢失；
- 这是“不落盘”的代价；需要持久化时应该单独做加密/受控存储，而不是混进 session。

---

### 问题 8：Session 过度落盘

**现象**

一次带 todo 的 turn 可能写 3 次 session：

1. todo 工具 `ctx.save()`；
2. 工具批次结束；
3. `_finish_turn`。

**方案**

- 删除 `ToolContext.save_session` / `ctx.save()`；
- 删除工具批次后的 save；
- 只在压缩后、turn 结束、出错时落盘；
- `_finish_turn`/`_fail_turn` 负责持久化最终状态。

**取舍**

- 中途崩溃会丢整个 turn；
- 这是有意的 turn 级持久化，不是工具级 checkpoint。要支持中途恢复，需要 pending tool 状态 + 可恢复上下文，不是简单多写几次盘。

---

### 问题 9：max_steps 后历史停在 tool_result

**现象**

模型连续调用工具达到 8 步后，loop 退出，返回一条本地 “Stopped after 8...” 消息，但没有写进 `session.messages`。session 最后停在一条 `tool_result` user 消息上；下一轮再追加 user 消息可能不合法。

**方案**

达到 max_steps 时：

- 追加一条 assistant 文本消息（“Stopped after ...”），关闭 turn；
- 再 `_finish_turn` 保存。

**验证**

`test_max_steps_stops` 断言 session 最后一条是 assistant，且包含停止提示。

---

### 问题 10：ToolContext 每个工具调用都重建

**现象**

`for call in tool_calls` 里每次都 `ToolContext(...)`，但 session、trace、memory、artifacts 在一轮内都是固定的。

**方案**

- 在每轮开始构造一次 `tool_ctx`；
- 所有工具调用复用。

**结果**

调用点更接近参考实现的简单形态，也少了一轮内重复对象创建。

---

## 5. 被拒绝 / 修改的 AI 建议

| AI 建议 | 最终决定 | 理由 |
|---|---|---|
| 完整 4 档压缩（snip/micro/budget/summary） | 2 档：工具预算 + 旧轮摘要 + transcript | 本题说“基础压缩即可”；4 档代码和测试成本高，收益有限 |
| Markdown 主存储 + `MEMORY.md` 索引 + sideQuery 召回 | JSON canonical + MD 镜像 + 关键词召回 + memory 工具 | 一周内可控；关键词召回不依赖文件格式；sideQuery 多一次调用且不确定 |
| 完整 6 种权限模式 + 规则文件 | 只做风险分级/路径校验/参数校验 | 本题没有 shell/任意写/网络/共享状态；完整权限系统是无风险收益的复杂度 |
| thinking 跨轮持久化，保证推理连续 | 默认剥离；`--keep-thinking-in-memory` 仅内存 | 用户要求“不落盘”；持久化会带来成本、隐私、签名/版本问题 |
| 保留自定义 `<thought>` 标签 | 改为原生 thinking block | 自定义标签无签名/无 API 语义，容易伪造 |
| `llm_response` 里保留完整 tool_calls | 只保留 tool_names，参数放 `tool_call` | 避免重复和日志膨胀 |
| 每次工具调用后保存 session | 只在 turn 边界/压缩/错误保存 | 内存态足够；中途落盘不能安全恢复 |
| 使用完整 JSON Schema 库 | 手写子集校验 | 6 个工具够用；少一个依赖，边界更可控 |

---

## 6. 验证与结果

### 6.1 单元测试

- 62 个测试通过（`pytest`）；
- 覆盖：
  - loop：直接回答、一次工具、多步工具、最大步数、LLM 错误回滚、追问、双 session 隔离、memory 工具、thinking 输出/不落盘；
  - tools：calculator、todo、search、read_docs、weather、memory、参数校验、路径穿越；
  - parser/protocol：text/tool 提取、thinking 提取、thinking 剥离、tool_use 保留；
  - session：创建/加载/列表/隔离、原子写、符号链接逃逸、thinking 不落盘；
  - context：token 触发、消息数触发、transcript 归档；
  - prompt：summary/todos/memory 注入、tool selection、无重复工具描述；
  - llm：API key 缺失、thinking 预算、block 转换。

### 6.2 真实 API 冒烟

- 文本回复：通过；
- todo 工具调用：模型返回 `tool_use` → 执行 → `tool_result` → 最终文本，通过；
- memory 写入：模型调用 `memory.save`，JSON + MD 镜像生成，通过；
- 测试数据已清理，不提交运行时会话。

### 6.3 未验证/已知边界

- 原生 thinking 默认关闭；当前测试网关不保证支持 `thinking` 参数，官方 Anthropic 需实际验证；
- 未做 200 轮长会话的真实压测；
- 未做多进程并发写同一 session；
- 未做完整 Markdown 主存储/sideQuery 召回；
- 未做完整权限模式和沙箱。

