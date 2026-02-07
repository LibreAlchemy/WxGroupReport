---
name: import-chat-data
description: 将 whitelist.md（昵称/可选 wxid）匹配到 processed JSON（group/members/ 每人一个 JSON），并在命中成员上设置 isWhitelist=true；输出落盘到 output。
---

# Skill: import-chat-data（白名单标记）

## 什么时候自动使用

当前仓库的 import-chat-data 只做一件事：把 `whitelist.md` 中的白名单条目（昵称/可选 wxid）匹配到 processed JSON 的成员（按 wxid 主键）上，并设置 `isWhitelist: true`。

匹配顺序：如果白名单条目提供了 wxid，则优先按 wxid 精确命中；否则回退到按昵称精确匹配。

只要用户表达了下面任意意图，就应该触发本技能：

- “按 whitelist.md 给成员打白名单标记 / isWhitelist=true”
- “用 group/members 下的成员 json，把 whitelist.md 里的昵称匹配到 wxid 上”
- “导出带白名单标记的新 JSON 到 output”

## 工作流（必须执行）

1. 抽取/确定参数（能推断就推断，尽量不问）：
   - `filePath`：输入路径（推荐用 `group/` 或 `group/members/` 目录；也支持单个 processed 群 JSON 文件）
   - `whitelistPath`：昵称白名单 Markdown（默认 `.opencode/skills/import-chat-data/references/whitelist.md`）
   - `outputPath`：输出路径
     - 当 `filePath` 为目录：输出目录（默认 `output/whitelist_applied_<dir>/`，保留每个成员的文件名）
     - 当 `filePath` 为文件：输出 JSON（默认 `output/whitelist_applied_<群名>.json` 或 `output/<成员文件名>.json`）

2. 执行匹配并落盘：

```bash
python "scripts/apply_whitelist_nickname.py" "<filePath>" \
  --whitelist "<whitelistPath>" \
  --out "<outputPath>"
```

3. 给用户返回：
   - 默认只返回两行（节省 token，不在对话中输出 JSON 内容）：
     - `白名单标记完成`
     - 输出文件路径（可点击）
   - 仅当用户明确要求或需要排查时，才返回匹配统计（matched/unmatched_wxids/unmatched_nicknames/ambiguous）

## 输入/输出契约

### 输入（ApplyWhitelistInput）

```ts
interface ApplyWhitelistInput {
  filePath: string; // 输入路径：processed 群 JSON 文件 / 成员 JSON 文件 / 目录（group/ 或 group/members/）
  whitelistPath?: string; // whitelist.md 路径（可选）
  outputPath?: string; // 输出路径：输入为目录时输出目录；输入为文件时输出 JSON 文件路径（可选）
}
```

### 输入文件结构（约定）

本技能支持两种输入：

1) 每人一个成员 JSON（推荐，位于 `group/members/*.json`）

```ts
interface MemberJson {
  wxid: string;
  nickname?: string;
  avatar?: string;
  isWhitelist?: boolean;
}
```

2) 旧版 processed 群 JSON（根对象含 `members` 映射）

```ts
interface ProcessedJson {
  group_info?: { name?: string };
  members: Record<string, { wxid?: string; nickname?: string; isWhitelist?: boolean }>;
}
```

### 输出（ApplyWhitelistOutput）

- 当输入为成员目录：在输出目录下落盘每个成员 JSON，仅在命中成员对象上写入 `isWhitelist: true`。
- 当输入为 processed 群 JSON：输出仍是 JSON（与输入同结构），仅在命中成员对象上写入 `isWhitelist: true`。

字段顺序约定（仅影响输出 JSON 的 key 顺序，不影响语义）：如果成员对象中存在 `avatar` 字段，则将 `isWhitelist` 放在 `avatar` 字段之后。

## 白名单文件规则

- 使用 `.opencode/skills/import-chat-data/references/whitelist.md` 维护昵称（推荐每行一个昵称；也支持 Markdown 列表/勾选框/表格第一列）。
- 解析规则说明见：`.opencode/skills/import-chat-data/references/whitelist_format.md`

## 隐私与安全

- 导出 JSON 结果包含完整消息 content，默认视为隐私数据。
- 不要建议用户把 `output/*.json` 提交到 git。
