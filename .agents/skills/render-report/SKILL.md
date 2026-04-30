---
name: render-report
description: 将精修后的 Markdown 报告（output/report_refined.md）渲染为最终 HTML（output/report_final.html）。当用户要求“生成最终 HTML”“将报告套用设计模板”“把 report_refined.md 填入模板”时使用。
---

# 技能：render-report

## 概述

该技能将 `output/report_refined.md` 解析为结构化数据，并填充到技能模板 `references/template_v1.html`，生成最终可展示页面 `output/report_final.html`。
其中 `references/design.pen` 作为模板视觉基准文件，后续调整样式时需优先与该设计稿保持一致。

## 工作流

1. 校验输入文件：
   - 必须存在 `references/template_v1.html`
   - 必须存在 `output/report_refined.md`
2. 解析精修报告：
   - 标题、期号、统计周期、总成员、活跃成员、精彩内容数
   - 本期排行（排名/成员/综合分）
   - 本期看点三个小节：精选分享、开源项目、原创心得
3. 渲染模板：
   - 用脚本处理 `{{变量}}` 与 `{{#列表}}...{{/列表}}`
4. 输出 HTML：
   - 写入 `output/report_final.html`
5. 校验结果：
   - 输出每个小节条目计数，便于核对
   - 必须对照 `references/design.pen` 做视觉还原与自检，确认最终 HTML 样式与设计稿一致。

## 脚本

使用脚本：`scripts/render_report.py`

### 默认命令

```bash
python3 .agents/skills/render-report/scripts/render_report.py
```

### 可选参数

- `--template`：模板路径（默认 `references/template_v1.html`）
- `--input`：输入 Markdown（默认 `output/report_refined.md`）
- `--output`：输出 HTML（默认 `output/report_final.html`）

## 输出

- 最终 HTML：`output/report_final.html`

## 约束

- 不修改模板文件内容。
- 不修改 `report_refined.md` 内容。
- 仅负责“解析 + 渲染 + 输出 HTML”。
