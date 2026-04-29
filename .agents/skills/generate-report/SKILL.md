---
name: generate-report
description: 基于分析结果生成 Markdown 报告（`report.md` 与 `scores.md`）。用户要求“生成报告”“更新 report.md”“重出成员评分名单”时使用。
---
# 技能：generate-report

## 概述

使用 Jinja2 模板生成两份 Markdown：
- 主报告：`output/report.md`
- 成员评分报告：`output/scores.md`

## 使用场景

- 用户要求生成或刷新报告
- 需要将 `analyze.json` 渲染为 Markdown

## 工作流（必须按顺序）

1. 加载技能模板文件：
   - `references/report_template.md`
   - `references/scores_template.md`
2. 组装模板上下文：
   - 周期、生成时间、期数；周期始终从 `output/imported.json` 的消息时间按 UTC+8 推断
   - 汇总字段：`total_members`、`active_members`、`score_flagged_count`、`highlights_count`
   - `top_members`：按综合分计算后的前 10
   - `highlights` 按类型分组
   - `score_members` 与 `score_groups`
3. 使用上下文渲染模板。
4. 写入两份输出文件。

## 输入与输出

### 输入（ReportInput）

```ts
interface ReportInput {
  memberScores: MemberScore[];
  highlights: Highlight[];
  config?: {
    reportNumber?: number;
  };
}
```

### 输出（ReportOutput）

```ts
interface ReportOutput {
  success: boolean;
  data?: {
    reportPath: string;
    scoresPath: string;
  };
  error?: {
    code: string;
    message: string;
  };
}
```

## 模板

使用 `references/` 目录下的模板文件。

## 脚本

使用 `.agents/skills/generate-report/scripts/generate_report.py` 从 JSON 输入生成报告。
脚本支持命令行参数与环境变量。

### 命令行参数

- `-o, --output`：输出目录（默认 `output`）

### 环境变量

- `REPORT_NUMBER`（默认 `1`）

## 说明

- 主模板路径固定为脚本同级 `references/report_template.md`。
- 成员评分模板路径固定为脚本同级 `references/scores_template.md`。
- 成员评分报告固定输出到 `output/scores.md`。
- 对外回复时不要输出大段 JSON 原文。
