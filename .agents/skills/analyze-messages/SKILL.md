---
name: analyze-messages
description: 使用大模型并发分析已处理的微信群成员消息，输出成员评分与精彩内容汇总。用户要求“分析成员发言”“生成 analyze.json”“重跑消息分析”时使用。
---

# 技能：analyze-messages

## 概述

并行分析成员消息，输出成员级总结、多维质量分和精彩内容。
精彩内容 `highlights` 支持 `news`、`article`、`github`、`insight`、`opportunity` 类型。`news` 仅由模型判断并提取有明确链接的新闻/资讯热点，报告层只按模型给出的类型分组。`github` 的内容使用模型生成的项目用途/推荐说明。`insight` 只保留可脱离上下文理解、对他人有复用价值的方法、经验、判断或结论，不提取生活状态、情绪、玩笑和日常计划。
分析会结合 `dialogue.json` 中的局部群聊上下文，并使用稳定消息 ID 校验 AI 给出的证据。

## 使用场景

- 需要对成员发言做批量 AI 分析
- 需要输出 `output/analyze.json`

## 输入与输出

### 输入（AnalyzeInput）

```ts
interface AnalyzeInput {
  config?: {
    model?: string;            // 模型名称，默认 gemini-2.0-flash
    maxWorkers?: number;        // 并行任务数，默认 10
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
  rawMessageCount: number;
  substantiveCount: number;
  score: number;  // 70% 原始质量分 + 30% 同批百分位分
  rawScore: number;
  dimensions: {
    informationDensity: number;
    originality: number;
    resourceValue: number;
    interactionValue: number;
    continuity: number;
  };
  confidence: "low" | "medium" | "high";
  summary: string;
  status: "normal" | "zero_activity" | "error";
  evidence: Evidence[];
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

- 模型输出信息密度、原创性、资源价值、互动价值四项 0-100 分
- 本地程序计算持续性分，并按 `35% / 25% / 20% / 10% / 10%` 加权得到 `rawScore`
- 至少 3 名中高置信度成员参与时，最终 `score = 70% rawScore + 30% 同批百分位分`
- 少于 5 条有效消息为 low，5-19 条为 medium，20 条以上为 high；low 不参与校准

### 有效消息过滤

- 过滤以 `#接龙` 开头的消息、导出图片路径和图片/表情/视频等纯占位符
- `messageCount` 表示有效分析消息数，`rawMessageCount` 保留原始数量

## 处理步骤

1. **加载成员文件**: 读取 `output/members/*.json`
2. **构建上下文**: 从 `output/dialogue.json` 按 120 秒窗口和消息相关性加入局部上下文；短回复、疑问、引用和指代句保留更多邻居，自包含陈述只保留必要前文
3. **按预算分块**: 每个成员按日期和约 12000 字符切成多个上下文块
4. **并发调用**: 单块成员调用一次；多块成员逐块分析后再调用一次汇总模型
5. **校验与评分**: 校验证据消息 ID、回填链接、计算多维分和置信度
6. **原创心得审查**: 模型逐条判断 `insight` 是否具有脱离上下文后仍可复用的方法、经验或判断；生活状态、情绪、玩笑和日常计划会被剔除
7. **增量写入**: 输出 `output/scores/*.json` 和 `output/errors.json`
8. **批次校准**: 汇总阶段执行分档校准并写入 `output/analyze.json`

提示词中的消息使用 `HH:MM 消息别名 说话人别名: 内容` 的紧凑格式。完整消息 ID 和人物昵称映射保留在本地程序中，AI 只返回短消息别名，以降低 token 消耗并继续支持证据审计。

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
- `REASONING_EFFORT`：思考等级，默认 `high`，可选 `minimal|low|medium|high|xhigh`，留空表示关闭
- `AI_TEMPERATURE`：采样温度，范围 `0.0`-`2.0`，默认 `0.1`

## 缓存失效

评分缓存会同时比较 `promptVersion`、`scoringVersion`、`model` 和成员 `inputHash`。任一字段变化，或旧缓存缺少这些元数据时，都会重新分析。
