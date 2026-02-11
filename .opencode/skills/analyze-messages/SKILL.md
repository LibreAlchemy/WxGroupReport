---
name: analyze-messages
description: Use when scoring processed WeChat member messages, extracting highlights, and identifying low-quality members based on 系分文档 rules.
---

# Skill: analyze-messages

## Overview

Score each message with base 60 and bonus/penalty rules, aggregate per member, extract highlights, and output low-quality lists. Input is processed member JSON under `output/members/` with `messages` arrays and optional `isWhitelist`.

## When to Use

- user asks to analyze member JSON or score messages
- need highlights (article/github/insight/opportunity)
- need low-quality member list based on thresholds

## Workflow (must follow)

1. Load member JSON files from `output/members/` (or user-provided path).
2. For each member message:
   - base score 60
   - apply bonus/penalty per 系分文档 §2.2
   - classify highlight type if applicable
3. Aggregate per member: messageCount, totalScore, averageScore.
4. Determine member status using thresholds (lowQualityThreshold=60, minMessageCount=5 unless overridden).
5. Build outputs: `memberScores`, `highlights`, `lowQualityMembers`.
6. Exclude whitelisted members from low-quality lists but keep them in ranking/score stats.

## Scoring Rules (from 系分文档 §2.2)

**Base score**: 60 per message.

**Bonus categories** (additive ranges):
- 技术分享 +15~25
- 资源分享 +10~20
- 解答问题 +10~15
- 深度讨论 +10~20
- 原创观点 +10~15
- 机会分享 +10~15
- 互动回复 +5~10

**Deduction** (can drop to 0):
- 纯表情包 0
- 单字回复 0
- 刷屏重复 0
- 水群无意义 0~20

## Low-Quality Criteria

- zero_activity: no valid messages (severity high)
- low_quality: averageScore < 60 (severity medium)
- low_frequency: messageCount < 5 (severity low)

Sort by severity: zero_activity → low_quality → low_frequency.

## Input / Output

### Input (AnalyzeInput)

```ts
interface AnalyzeInput {
  messages: ParsedMessage[];
  whitelist: string[];
  config?: {
    lowQualityThreshold?: number; // default 60
    minMessageCount?: number;     // default 5
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
  };
  error?: {
    code: string;
    message: string;
  };
}
```

## Highlight Extraction

- article: tech article/tutorial links or explicit "教程/文章" share
- github: GitHub URLs
- insight: original观点/总结
- opportunity: 招聘/合作/实习/内推等

## Quick Reference

| Step | Action |
| --- | --- |
| Load input | `output/members/*.json` |
| Score | base 60 + bonus/penalty |
| Aggregate | per member totals/averages |
| Low quality | <60 avg or <5 msgs |

## Example

Input message:

```json
{"content":"分享一个Python爬虫教程","timestamp":"2026-02-01T08:00:00Z"}
```

Score: base 60 + 技术分享 (e.g., +20) → final 80.

## Common Mistakes

- Counting system/invalid messages as valid.
- Forgetting whitelist exemption for low-quality lists.
- Mixing nickname/wxid when aggregating.

## Rationalization Traps

| Excuse | Reality |
| --- | --- |
| "No time, just average raw counts" | Must follow scoring rules for accuracy. |
| "Handle all formats" | Support only processed member JSON shape. |
| "Skip highlights" | Highlights are required output. |

## Red Flags

- Output missing `memberScores` or `lowQualityMembers`.
- Scoring without base 60 rule.
- Ignoring whitelist exclusion for low-quality lists.
