# 群聊记录分析工具 (WxGroupReport)

基于 AI 的微信群聊分析工具，自动分析群成员消息质量，生成 Markdown 周期报告。

## 功能特性

- 📥 **数据导入**: 解析微信导出的 JSON 格式聊天记录
- 🤖 **AI 分析**: 使用 Google Gemini API 进行成员评分与内容分类
- 📊 **报告生成**: 输出 Markdown 格式的群聊周期报告
- 🏆 **活跃排行**: 自动识别高活跃度成员
- ⚠️ **低质检测**: 自动识别低质量/低活跃成员

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/LibreAlchemy/WxGroupReport.git
cd WxGroupReport
```

### 2. 配置环境变量

复制配置模板并填写：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下必需项：

#### 必需配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `INPUT_PATH` | 微信导出的 JSON 文件路径 | `./group/chat.json` |
| `GOOGLE_API_KEY` | Google API 密钥 | `AIzaSy...` |
| `OUTPUT_DIR` | 输出目录 | `output` |

#### 可选配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL` | `gemini-2.5-flash` | 使用的 AI 模型 |
| `PERIOD_START` | - | 统计开始日期 (ISO 8601) |
| `PERIOD_END` | - | 统计结束日期 (ISO 8601) |
| `REPORT_NUMBER` | `1` | 报告期号 |

#### 获取 Google API Key

1. 访问 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 创建新的 API Key
3. 复制到 `.env` 文件的 `GOOGLE_API_KEY`

### 3. 准备输入数据

将微信聊天记录导出为 JSON 格式，放到项目目录：

```
WxGroupReport/
└── group/
    └── chat.json    # 你的微信导出文件
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

---

## 使用 Skills

项目包含 3 个独立的 Skills，按顺序执行即可完成完整分析流程。

### Skill 1: import-chat-data (数据导入)

**作用**: 解析 JSON 聊天记录，按成员拆分文件

**执行方式**:

```bash
python .opencode/skills/import-chat-data/scripts/preprocessor.py
python .opencode/skills/import-chat-data/scripts/apply_whitelist.py
```

**输出**: 
- `output/members/` 目录下每个成员的 JSON 文件
- `output/group_info.json` 群组信息

---

### Skill 2: analyze-messages (AI 分析)

**作用**: 使用 Gemini API 分析成员消息，进行评分和内容分类

**执行方式**:

```bash
python .opencode/skills/analyze-messages/scripts/analyze.py
```

**输出**:
- `output/analyze-messages.json` 包含：
  - 成员评分 (memberScores)
  - 精彩内容 (highlights)
  - 低质成员名单 (lowQualityMembers)

**评分维度**:
| 维度 | 说明 |
|------|------|
| technical_share | 技术分享 |
| resource_share | 资源分享 |
| answer_question | 解答问题 |
| deep_discussion | 深度讨论 |
| original_viewpoint | 原创观点 |
| opportunity_share | 机会分享 |
| interactive_reply | 互动回复 |

---

### Skill 3: generate-report (报告生成)

**作用**: 基于分析结果生成 Markdown 报告

**执行方式**:

```bash
python .opencode/skills/generate-report/scripts/generate_report.py
```

**输出**:
- `output/report.md` 群聊分析报告

---

## 完整流程示例

```bash
# 1. 配置环境
cp .env.example .env
# 编辑 .env 填写 GOOGLE_API_KEY 等配置

# 2. 导入数据
python .opencode/skills/import-chat-data/scripts/preprocessor.py
python .opencode/skills/import-chat-data/scripts/apply_whitelist.py

# 3. AI 分析
python .opencode/skills/analyze-messages/scripts/analyze.py

# 4. 生成报告
python .opencode/skills/generate-report/scripts/generate_report.py

# 5. 查看报告
cat output/report.md
```

---

## 配置详解

### .env 完整配置项

```bash
# ========== 输入输出 ==========
INPUT_PATH=group/chat.json         # 微信导出的 JSON 文件
OUTPUT_DIR=output                  # 输出目录

# ========== 导入选项 ==========
INCLUDE_JOIN_TIME=false            # 是否包含入群时间
NO_INDIVIDUAL=false                # 是否不生成个人文件

# ========== API 配置 (必需) ==========
API_PROVIDER=google                # API 提供商 (google)
GOOGLE_API_KEY=YOUR_API_KEY_HERE   # ← 必须填写！

# ========== 模型配置 ==========
MODEL=gemini-2.5-flash             # AI 模型

# ========== 代理配置 (可选) ==========
HTTP_PROXY=                        # HTTP 代理
HTTPS_PROXY=                       # HTTPS 代理

# ========== 报告选项 ==========
PERIOD_START=                      # 统计开始日期 (如: 2026-01-01)
PERIOD_END=                        # 统计结束日期 (如: 2026-01-31)
REPORT_NUMBER=1                    # 报告期号
```

### 白名单配置 (可选)

在 `output/` 目录下创建 `whitelist.txt`:

```
# 活跃成员 (不参与低质判定)
张三
李四
王五

# 贡献成员
赵六
```

---

## 项目结构

```
WxGroupReport/
├── .env.example              # 环境变量模板
├── .gitignore
├── requirements.txt          # Python 依赖
│
├── .opencode/
│   └── skills/
│       ├── import-chat-data/    # Skill 1: 数据导入
│       │   └── scripts/
│       │       ├── preprocessor.py
│       │       └── apply_whitelist.py
│       │
│       ├── analyze-messages/    # Skill 2: AI 分析
│       │   └── scripts/
│       │       ├── analyze.py
│       │       ├── api_client.py
│       │       └── batcher.py
│       │
│       └── generate-report/    # Skill 3: 报告生成
│           ├── template.md
│           └── scripts/
│               └── generate_report.py
│
├── data/                    # 输入数据
│   └── chat.json
│
└── output/                  # 输出结果
    ├── members/            # 成员文件
    ├── group_info.json
    ├── analyze-messages.json
    └── report.md           # 最终报告
```

---

## 常见问题

### Q: 提示 "GOOGLE_API_KEY" 未设置

A: 确保 `.env` 文件中填写了有效的 Google API Key

### Q: API 调用失败

A: 
1. 检查网络是否需要代理
2. 如需代理，在 `.env` 中配置 `HTTP_PROXY` 和 `HTTPS_PROXY`
3. 确认 API Key 有足够配额

### Q: 报告生成失败

A: 确保 `output/analyze-messages.json` 存在且格式正确

### Q: 如何处理大文件？

A: `analyze-messages` 会自动分批处理，每批 100 条消息，支持并行调用

---

## 技术栈

- **AI 模型**: Google Gemini API
- **脚本**: Python 3.10+
- **模板**: Jinja2
- **Agent**: OpenCode / Claude Code

---

## License

MIT
