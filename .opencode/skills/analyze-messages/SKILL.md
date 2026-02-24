---
name: analyze-messages
description: Use when scoring processed WeChat member messages, extracting highlights, and identifying low-quality members based on new scoring rules.
---

# Skill: analyze-messages

## Overview

使用 Google Gemini API 并行分析成员消息，实现成员级总结+评分，提取精彩内容，识别低质成员。

## When to Use

- 用户要求分析成员消息
- 需要使用外部 API (非 Claude Code 内置模型)
- 需要并行处理提升效率

## 核心变化

| 项目 | 旧设计 | 新设计 |
|------|--------|--------|
| 评分方式 | 7维度×1-5分逐条评分 | 成员级总结 + 评分 |
| API | Claude Code 内置 | Google Gemini API |
| 并行粒度 | 30条/批 | 按成员分组，100条/批 |
| 输出 | 每条消息评分 | 成员级总结+评分 |

## Input / Output

### Input (AnalyzeInput)

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

### Output (AnalyzeOutput)

```ts
interface AnalyzeOutput {
  success: boolean;
  data?: {
    memberScores: MemberScore[];
    highlights: Highlight[];
    lowQualityMembers: LowQualityMember[];
    summary: {
      totalMembers: number;
      analyzedMembers: number;
      totalMessages: number;
      highlightsCount: number;
      lowQualityCount: number;
    };
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
  totalScore: number;
  averageScore: number;
  summary: string;           // 成员发言总结
  isWhitelisted: boolean;
  status: "normal" | "low_quality" | "zero_activity" | "low_frequency";
  reason?: string;
}
```

## 评分规则

### 评分维度 (7维度，1-5分)

| 维度 | 说明 |
|------|------|
| technical_share | 技术分享 |
| resource_share | 资源分享 |
| answer_question | 解答问题 |
| deep_discussion | 深度讨论 |
| original_viewpoint | 原创观点 |
| opportunity_share | 机会分享 |
| interactive_reply | 互动回复 |

### 评分流程

1. **消息分组**: 按成员 wxid 分组
2. **负载均衡**: 按消息数量将成员分配到并行任务
3. **API 调用**: 每批消息 (≤100条) 调用 Gemini API
4. **总结+评分**: API 返回成员总结 + 每条消息评分
5. **聚合**: 合并所有成员评分结果

### 低质判定

- zero_activity: messageCount == 0 (严重程度: 高)
- low_quality: averageScore < 60 (严重程度: 中)
- low_frequency: messageCount < 5 (严重程度: 低)

## API Prompt 模板

```
## 任务
请分析以下群成员的消息，进行总结并评分。

## 成员信息
- wxid: {wxid}
- 昵称: {nickname}
- 消息数: {message_count}

## 消息列表
{messages}

## 输出格式 (JSON)
{
  "summary": "成员发言总结（50-200字）",
  "scores": [
    {
      "message_index": 0,
      "technical_share": 3,
      "resource_share": 0,
      "answer_question": 0,
      "deep_discussion": 0,
      "original_viewpoint": 0,
      "opportunity_share": 0,
      "interactive_reply": 2,
      "total_score": 5
    }
  ],
  "highlights": [
    {
      "type": "article|github|insight|opportunity",
      "content": "内容摘要",
      "url": "链接（如果有）",
      "message_index": 0
    }
  ]
}
```

## 并行策略

1. 按成员 wxid 分组消息
2. 按消息数量降序排序成员
3. 轮询分配成员到 N 个并行任务，保证每任务消息数均衡
4. 每任务使用 concurrent.futures.ThreadPoolExecutor 并行调用 API

## 处理步骤

1. **加载成员文件**: 读取 `output/members/*.json`
2. **分组消息**: 按 wxid 聚合消息
3. **负载均衡**: 分配到 N 个并行任务
4. **API 评分**: 并行调用 Gemini API
5. **聚合结果**: 合并所有成员评分
6. **判定低质**: 按阈值判定低质成员
7. **输出结果**: 写入 `output/analyze-messages.json`

## 环境配置

需要以下环境变量 (从 .env 读取):
- `GOOGLE_API_KEY`: Google API 密钥
- `MODEL`: 模型名称 (默认 gemini-2.0-flash)
- `API_PROVIDER`: google

## 文件结构

```
.opencode/skills/analyze-messages/
├── SKILL.md                 # 本文件
└── scripts/
    ├── __init__.py
    ├── api_client.py        # Gemini API 调用
    ├── batcher.py          # 负载均衡分批
    └── analyze.py          # 主分析脚本
```