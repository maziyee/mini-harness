# Agent Harness 速记

## Agent Loop

一次用户输入对应一个 turn。一个 turn 内最多执行若干次工具调用：

1. 把用户消息追加到 session；
2. 调用模型；
3. 如果模型返回 tool_use，执行工具并把 tool_result 回填；
4. 重复 2-3，直到模型返回最终文本。

## Session

session 是隔离边界。同一个用户的两个窗口是两个独立的 session，
各自的 messages、summary、todos 互不影响。

## Context

context 预算按 token 估算。优先保留：

- 当前用户消息
- 目标与硬约束
- 当前 todo
- 最近几轮对话
- 旧轮次摘要

优先丢弃：重复的工具输出、寒暄、思考过程、已完成的中间步骤。

## Memory

长期记忆只存稳定的偏好、事实和任务状态。召回时机：

- session 开始：偏好 + 活跃任务
- 每轮：与当前 query 关键词命中的记忆
- 用户明确提及过去：放宽召回

记忆放在 system prompt 的独立小节，带来源和时间，并标注“可能过时”。
