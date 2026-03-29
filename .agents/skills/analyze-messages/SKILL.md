---
name: analyze-messages
description: 使用大模型并发分析已处理的微信群成员消息，输出成员评分与精彩内容汇总。用户要求“分析成员发言”“生成 analyze.json”“重跑消息分析”时使用。
---

# 技能：analyze-messages

## 概述

并行分析成员消息，输出成员级总结、质量分和精彩内容。

## 使用场景

- 需要对成员发言做批量 AI 分析
- 需要输出 `output/analyze.json`

## 输入与输出

### 输入（AnalyzeInput）

```ts
interface AnalyzeInput {
  config?: {
    model?: string;            // 模型名称，默认 gemini-2.0-flash
    batchSize?: number;        // 每批消息数，默认 100
    maxWorkers?: number;        // 并行任务数，默认 5
    lowQualityThreshold?: number; // 低质判定阈值，默认 60
    minMessageCount?: number;  // 低频次阈值，默认 5
  };
}
```

### 输出（AnalyzeOutput）

```ts
interface AnalyzeOutput {
  success: boolean;
  data?: {
    memberScores: MemberScore[];
    highlights: Highlight[];
  };
  error?: {
    code: string;
    message: string;
  };
}

interface MemberScore {
  wxid: string;
  nickname: string;
  messageCount: number;
  qualityScore: number;  // 0-100，成员发言质量分
  summary: string;
  status: "normal" | "zero_activity" | "error";
  stats: {
    resource: number;
    technical: number;
    qa: number;
    discussion: number;
    insight: number;
    opportunity: number;
    reply: number;
  };
  highlights: Highlight[];
}
```

## 错误处理与重试

脚本使用增量重试：

1. **增量写入**: 只有分析成功的成员结果会写入 `output/scores/` 目录。
2. **错误记录**: 分析失败的成员会被记录在 `output/errors.json` 中，包含错误原因和消息计数。
3. **自动重试**: 脚本会自动循环读取 `errors.json` 并重试其中的成员，直到所有成员成功分析或手动中断。
4. **清理机制**: 成员成功后自动从 `errors.json` 移除；若已有成功 score，也会在扫描阶段清理残留错误项。
5. **汇总延迟**: 全部处理完成后生成 `output/analyze.json`。

## 评分规则

### 质量分

- 模型输出 `quality_score`（0-100）
- 系统写入 `qualityScore`

### 有效消息过滤

- 过滤掉以 `#接龙` 开头的消息

### 统计维度（stats）

- `resource` 资源分享
- `technical` 技术探讨
- `qa` 问答/求助
- `discussion` 一般讨论
- `insight` 深度见解
- `opportunity` 合作机会
- `reply` 回复他人

## 处理步骤

1. **加载成员文件**: 读取 `output/members/*.json`
2. **并发调用**: 按成员并发调用模型
3. **增量写入**: 输出 `output/scores/*.json` 和 `output/errors.json`
4. **汇总结果**: 生成 `output/analyze.json`

## 文件结构

```
.agents/skills/analyze-messages/
├── SKILL.md                 # 本文件
└── scripts/
    └── analyze.py          # 主分析脚本
```

## 脚本用法

使用 `.agents/skills/analyze-messages/scripts/analyze.py` 执行分析。
脚本支持命令行参数与环境变量。

### 命令行参数

- `-o, --output`：输出目录（默认 `output`）

### 环境变量

- `AI_PROVIDER` / `AI_MODEL` / `AI_API_KEY` / `AI_BASE_URL`
- `MAX_ANALYZE_WORKERS` (default `10`)
