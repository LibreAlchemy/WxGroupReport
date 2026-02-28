# 群聊记录分析工具 (WxGroupReport)

基于 AI 的微信群聊分析工具，自动分析群成员消息质量，生成 Markdown 周期报告。

## 功能特性

- 📥 **数据导入**: 解析微信导出的 JSON 格式聊天记录
- 🤖 **AI 分析**: 使用 LiteLLM 调用大模型进行成员质量评分与内容分类
- 📊 **报告生成**: 输出 Markdown 格式的群聊周期报告
- 🏆 **活跃排行**: 自动识别高活跃度成员
- ⚠️ **低质检测**: 自动识别低质量/低活跃成员

## 技术栈

- **AI 模型**: 支持主流模型厂商 (通过 [LiteLLM](https://github.com/BerriAI/litellm))
- **脚本**: Python 3.10+
- **模板**: Jinja2
- **Agent**: OpenCode

## 快速开始

### 项目结构

```text
WxGroupReport/
├── .env.example
├── requirements.txt
├── .agents/
│   └── skills/
│       ├── start/
│       ├── import-chat-data/
│       │   └── scripts/
│       │       ├── preprocessor.py
│       │       └── apply_whitelist.py
│       ├── analyze-messages/
│       │   └── scripts/
│       │       └── analyze.py
│       └── generate-report/
│           ├── references/
│           │   ├── template.md
│           │   └── low_quality_template.md
│           └── scripts/
│               └── generate_report.py
└── output/
    ├── members/
    ├── scores/
    ├── analyze-messages.json
    ├── report.md
    └── low_quality_members.md
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

| 变量 | 说明 | 示例 |
|------|------|------|
| `AI_PROVIDER` | AI 厂商 (如 `openai`, `anthropic`, `gemini`, `deepseek` 等) | `gemini` |
| `AI_MODEL` | 模型名称 (如 `gemini-2.0-flash` 或完整路径 `deepseek/deepseek-chat`) | `gemini-2.0-flash` |
| `AI_API_KEY` | 对应厂商的 API Key | `AIzaSy...` |

常用可选项：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AI_BASE_URL` | OpenAI 兼容网关地址（按需） | - |
| `MAX_ANALYZE_WORKERS` | 分析并发数 | `10` |
| `ANALYZE_SLOW_API_SECONDS` | 慢请求日志阈值(秒) | `8` |
| `OUTPUT_DIR` | 输出目录 | `output` |

### 5. 准备输入数据

将微信聊天记录导出为 JSON 格式，放到任意位置。

### 6. 运行全流程（CLI）

```bash
# 1) 导入数据
python .agents/skills/import-chat-data/scripts/preprocessor.py -i data/your-chat.json -o output
python .agents/skills/import-chat-data/scripts/apply_whitelist.py -o output

# 2) 分析成员消息
python .agents/skills/analyze-messages/scripts/analyze.py -o output

# 3) 生成报告
python .agents/skills/generate-report/scripts/generate_report.py -o output
```

如果使用 OpenCode，也可以通过 `/start path/to/chat.json` 执行同等流程。

## 白名单配置 (可选)

在项目根目录下创建 `whitelist.md`，使用 Markdown 表格格式列出成员的 **微信 ID (wxid)** 或 **群昵称**：

```markdown
|昵称|wxid|
|----|----|
|张三|wxid_123456|
|李四|wxid_789012|
```

## 常见问题

### Q: 提示 "AI API Key" 未设置

确保 `.env` 文件中填写了有效的 `AI_API_KEY`，且 `AI_PROVIDER` 配置正确。

### Q: API 调用失败

1. 检查 API Key 是否正确。
2. 确认 API Key 有足够配额，且模型名称 (`AI_MODEL`) 填写正确。
3. 如果在特定网络环境下，请确保网络连接正常。

### Q: 报告生成失败

确保 `output/analyze-messages.json` 存在且格式正确。

## License

MIT
