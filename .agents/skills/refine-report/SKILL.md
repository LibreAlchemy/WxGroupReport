---
name: refine-report
description: 对已生成的群聊报告进行“本期看点”小节精修，输出精修版 Markdown。用户提出“精修版报告”“二次筛选精彩内容”或要求同时保留全量版和精修版时使用。
---

# 技能：refine-report

## 概述

该技能在保留全量报告不变的前提下，额外生成一份精修报告。
它读取 `output/report.md`，按 `references/refine_rules.md` 执行规则，并输出 `output/report_refined.md`。

## 工作流

1. 校验输入：
   - 必须存在 `output/report.md`。
   - 加载 `references/refine_rules.md`。
2. 使用 subagent 执行精修（强制）：
   - 必须通过 subagent 生成精修报告，不允许在主代理直接改写报告正文。
   - subagent 任务输入需包含：`output/report.md`。
3. 创建精修目标：
   - 先复制全量报告到 `output/report_refined.md`。
4. 精修 `# 本期看点`：
   - 严格执行 `references/refine_rules.md` 中的硬规则。
   - 最终结构固定为：`## 🤩 精选分享`、`## 💻 开源项目`、`## 💡 原创心得`。
5. 同步数据统计中的“精彩内容数”：
   - 将 `**精彩内容数**` 更新为精修后“本期看点”实际展示条目数。
   - 统计口径必须与页面中 `- ` 列表项数量一致。
6. 校验最终 Markdown：
   - 保持必需标题与标题间空行。
   - 确认无占位词和小程序噪音条目。
   - 确认“精彩内容数”与本期看点条目总数一致。

## 输出

- 全量报告：`output/report.md`（保持不变）
- 精修报告：`output/report_refined.md`

## 规则来源

始终使用：
- `references/refine_rules.md`

当规则与原报告内容冲突时，仅在精修输出中以规则文件为准。

## 约束

- 不修改分析产物 JSON 文件。
- 仅允许修改 `# 本期看点` 与 `**精彩内容数**` 两处相关内容。
- 除非违反 `references/refine_rules.md`，否则不删除有效条目。
