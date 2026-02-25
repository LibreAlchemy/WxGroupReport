# 群聊记录分析工具 (WxGroupReport)

基于 AI 的微信群聊分析工具，自动分析群成员消息质量，生成 Markdown 周期报告。

## 功能特性

- 📥 **数据导入**: 解析微信导出的 JSON 格式聊天记录
- 🤖 **AI 分析**: 使用 Google Gemini API 进行成员评分与内容分类
- 📊 **报告生成**: 输出 Markdown 格式的群聊周期报告
- 🏆 **活跃排行**: 自动识别高活跃度成员
- ⚠️ **低质检测**: 自动识别低质量/低活跃成员

## 技术栈

- **AI 模型**: Google Gemini API
- **脚本**: Python 3.10+
- **模板**: Jinja2
- **Agent**: OpenCode

## 快速开始

### 项目结构

```
WxGroupReport/
├── .env.example              # 环境变量模板
├── .gitignore
├── requirements.txt          # Python 依赖
│
├── .opencode/
│   └── skills/
│       ├── start/               # Skill 0: 流程启动
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

### 1. 克隆项目

```bash
git clone https://github.com/LibreAlchemy/WxGroupReport.git
cd WxGroupReport
```

### 2. 安装 OpenCode (推荐)

本工具推荐配合 [OpenCode](https://opencode.ai/) 使用以获得最佳体验。

```bash
curl -fsSL https://opencode.ai/install | bash
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

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

Tips：获取 Google API Key

1. 访问 [Google AI Studio](https://aistudio.google.com/app/apikey)
2. 创建新的 API Key
3. 复制到 `.env` 文件的 `GOOGLE_API_KEY`

#### 可选配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODEL` | `gemini-2.5-flash` | 使用的 AI 模型 |
| `PERIOD_START` | - | 统计开始日期 (ISO 8601) |
| `PERIOD_END` | - | 统计结束日期 (ISO 8601) |
| `REPORT_NUMBER` | `1` | 报告期号 |

### 5. 准备输入数据

将微信聊天记录导出为 JSON 格式，放到项目目录：

```
WxGroupReport/
└── group/
    └── chat.json    # 你的微信导出文件
```

### 6. 生成报告

在 `OpenCode` 中输入下面的提示生成报告：

```
生成报告
```

## 白名单配置 (可选)

在 `output/` 目录下创建 `whitelist.txt`:

```
# 活跃成员 (不参与低质判定)
张三
李四
王五

# 贡献成员
赵六
```

## 常见问题

### Q: 提示 "GOOGLE_API_KEY" 未设置

确保 `.env` 文件中填写了有效的 Google API Key

### Q: API 调用失败

1. 检查网络是否需要代理
2. 如需代理，在 `.env` 中配置 `HTTP_PROXY` 和 `HTTPS_PROXY`
3. 确认 API Key 有足够配额

### Q: 报告生成失败

确保 `output/analyze-messages.json` 存在且格式正确

### Q: 如何处理大文件？

`analyze-messages` 会自动分批处理，每批 100 条消息，支持并行调用

## License

MIT
