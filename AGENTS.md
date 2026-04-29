# Overview

这个仓库用于处理微信群导出数据，并生成群聊分析报告。

# Features

技能文件夹 `.agents/skills/`，技能列表：

- `import-chat-data`：处理群聊导出 JSON，拆分成员数据并应用 `whitelist.md`
- `analyze-messages`：分析成员发言并生成 `output/analyze.json`
- `generate-report`：生成 `output/report.md` 与 `output/scores.md`
- `refine-report`：保留全量报告，额外生成 `output/report_refined.md`
- `render-report`，生成 HTML 报告 `output/report_refined.html`

# Workflow

1. 询问用户执行特定技能还是完整流程。
2. 如果是完整流程，则依次执行 `import-chat-data`、`analyze-messages`、`generate-report`、`refine-report`。
3. 等待用户审查输出结果 `output/`，询问用户是否继续执行 `render-report` 技能。

# Execution Rules

- 执行完整流程时，严格串行执行：前一阶段成功后再进入下一阶段
- 关键错误即停止：出现阻塞性失败时终止后续阶段，并向用户说明卡点
- 进度同步：开始每个阶段前，都用一句简短的话同步当前进度
- 保持产物约定：不要随意更改各阶段既定输出路径和文件名
- 不要读取 `.env` 文件内容，脚本会自动加载
- 总是请求在沙箱外运行 `python` / `python3` 命令（Codex）
- 优先复用技能内已有脚本、模板和规则文件，不要自定义脚本执行
- 遇到耗时较长的脚本，检查产物是否持续增量；只要有更新，就继续等待，不要因为短时间无终端输出而中断
