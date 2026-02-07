# whitelist.md 格式（昵称白名单）

本 skill 将 `.opencode/skills/import-chat-data/references/whitelist.md` 视为“昵称白名单数据文件”。

## 解析规则

- 按行读取，每行 `strip()`（去掉首尾空白）
- 空行：跳过
- 标题行：以 `#` 开头则跳过
- 代码块：跳过 fenced code block（``` 与 ``` 之间的所有行）
- 分隔线：跳过 `---` / `***` / `___`
- HTML 注释：跳过 `<!-- ... -->`（支持多行注释块）

## 支持的写法

- 纯文本：`张三`
- Markdown 列表：`- 张三` / `* 张三` / `1. 张三`
- Markdown 勾选框：`- [x] 张三` / `- [ ] 张三`
- Markdown 表格（推荐）：`| 昵称 | wxid |`（第一列昵称，第二列 wxid；如需备注请加第三列）

脚本会优先使用表格第二列 `wxid` 精确命中成员；只有当条目未提供 wxid 时，才会回退使用昵称匹配。

## 匹配与写入规则

- 匹配顺序：
  - 优先：按 `wxid` 精确命中（白名单表格第二列）
  - 回退：对 `member.nickname` 做 `strip()` 后精确相等（字符串完全一致）
- 重名处理：如果多个成员拥有相同昵称，全部都会被标记（统计里记为 ambiguous）
- 命中写入：
- 命中写入：
  - `isWhitelist: true`
  - 字段顺序：若成员对象存在 `avatar` 字段，则输出时将 `isWhitelist` 放在 `avatar` 之后
