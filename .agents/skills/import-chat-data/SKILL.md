---
name: import-chat-data
description: 处理微信群导出 JSON，拆分为成员文件并应用 `whitelist.md` 匹配（wxid 优先）。用户要求“导入群聊数据”“重建 members 数据”时使用。
---

# 技能：import-chat-data

## 概述

将微信群导出 JSON 处理为按成员拆分的 JSON 文件，并应用白名单标记。

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

### 第二步：应用白名单

```bash
python3 ".agents/skills/import-chat-data/scripts/apply_whitelist.py" -o output
```

**参数**：
- `-o, --output`：输出目录（默认 `output`）
- `-w, --whitelist`：白名单文件路径（默认 `whitelist.md`）

**说明**：执行后根据控制台输出确认产物文件位置。

## 错误处理

- 缺少输入文件：报错并退出
- 缺少白名单文件：跳过白名单步骤
- JSON 解析失败：跳过该文件并继续

## 快速参考

脚本均位于本技能目录下的 `scripts/` 子目录。

执行约定：
- 使用当前 `SKILL.md` 所在路径作为 `SKILL_DIR`
- 使用 `${SKILL_DIR}/scripts/<script-name>.py` 作为脚本路径

| 脚本 | 用途 |
|------|------|
| scripts/preprocessor.py | 预处理群聊数据并按成员拆分 |
| scripts/apply_whitelist.py | 为成员应用白名单标记 |
