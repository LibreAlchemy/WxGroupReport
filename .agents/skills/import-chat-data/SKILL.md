---
name: import-chat-data
description: 处理微信群导出 JSON，拆分为成员文件。用户要求“导入群聊数据”“重建 members 数据”时使用。
---

# 技能：import-chat-data

## 概述

将微信群导出 JSON 处理为按成员拆分的 JSON 文件。支持 ChatLab `0.0.2` 旧格式和新版 `schemaVersion: 1` 导出。

预处理会额外生成 `output/dialogue.json`，保存稳定消息 ID、发送者和结构化引用，供分析阶段构建局部上下文。

## 工作流

### 第一步：预处理

```bash
python3 ".agents/skills/import-chat-data/scripts/preprocessor.py" -i path/to/input.json -o output
```

**参数**：
- `-i, --input`：输入 JSON 文件路径（必填）
- `-o, --output`：输出目录（默认 `output`）
- `--no-extract-join-time`：不提取入群时间（默认开启提取）
- `--no-save-individual`：不保存成员独立文件（默认开启保存）

**说明**：执行后根据控制台输出确认产物文件位置。

## 错误处理

- 缺少输入文件：报错并退出
- JSON 解析失败：报错并退出
- 不支持的导出结构或 schema：报错并退出，不生成空结果

新版导出没有完整成员名单，`totalMembers` 表示实际发言成员数，不包含从未发言的群成员。

## 快速参考

脚本均位于本技能目录下的 `scripts/` 子目录。

执行约定：
- 使用当前 `SKILL.md` 所在路径作为 `SKILL_DIR`
- 使用 `${SKILL_DIR}/scripts/<script-name>.py` 作为脚本路径

| 脚本 | 用途 |
|------|------|
| scripts/preprocessor.py | 预处理群聊数据并按成员拆分 |
| scripts/export_adapter.py | 识别并归一化 ChatLab 与新版导出格式 |
