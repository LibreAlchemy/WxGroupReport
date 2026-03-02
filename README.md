# 群聊记录分析工具 (WxGroupReport)

基于 AI 的群聊分析工具，自动分析群成员消息质量，生成 Markdown 周期报告，并可渲染为 HTML 页面。

## 功能特性

- 📥 **数据导入**: 解析 ChatLab JSON 格式聊天记录（来自 WeFlow 导出）
- 🤖 **AI 分析**: 使用 LiteLLM 调用大模型进行成员质量评分与内容分类
- 📊 **报告生成**: 输出 Markdown 格式的群聊周期报告
- 🖼️ **HTML 生成**: 将精修后的 Markdown 套用模板渲染为可分享的 HTML
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
├── .env.example              # 环境变量模板
├── .gitignore
├── requirements.txt          # Python 依赖
├── .agents/
│   └── skills/               # Agent Skills
├── data/                     # 输入数据（建议位置）
└── output/                   # 输出结果
    ├── imported.json         # 预处理数据
    ├── members/              # 成员消息文件
    ├── scores/               # 成员打分结果
    ├── analyze.json          # 全量分析结果（含成员分数和精彩内容）
    ├── report.md             # 产出报告
    ├── report_refined.md     # 精修后的报告（精彩内容优化）
    ├── report_final.html     # 最终 HTML 页面
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


| 变量          | 说明                                                                | 示例               |
| ------------- | ------------------------------------------------------------------- | ------------------ |
| `AI_PROVIDER` | AI 厂商 (如`openai`, `anthropic`, `gemini`, `deepseek` 等)          | `gemini`           |
| `AI_MODEL`    | 模型名称 (如`gemini-2.0-flash` 或完整路径 `deepseek/deepseek-chat`) | `gemini-2.0-flash` |
| `AI_API_KEY`  | 对应厂商的 API Key                                                  | `AIzaSy...`        |

常用可选项：


| 变量                       | 说明                        | 默认值   |
| -------------------------- | --------------------------- | -------- |
| `AI_BASE_URL`              | OpenAI 兼容网关地址（按需） | -        |
| `MAX_ANALYZE_WORKERS`      | 分析并发数                  | `10`     |
| `ANALYZE_SLOW_API_SECONDS` | 慢请求日志阈值(秒)          | `8`      |
| `OUTPUT_DIR`               | 输出目录                    | `output` |

### 5. 准备输入数据

本项目使用 [WeFlow](https://github.com/hicccc77/WeFlow) 导出的 ChatLab JSON 格式。

ChatLab JSON 示例：

```json
{
  "chatlab": {
    "version": "0.0.2",
    "exportedAt": 1703001600
  },
  "meta": {
    "name": "我的群聊",
    "platform": "qq",
    "type": "group"
  },
  "members": [
    {
      "platformId": "123456",
      "accountName": "张三"
    }
  ],
  "messages": [
    {
      "sender": "123456",
      "accountName": "张三",
      "timestamp": 1703001600,
      "type": 0,
      "content": "大家好！"
    }
  ]
}
```

### 6. 运行全流程（OpenCode）

在 OpenCode 中打开项目，然后发送：

- `/start path/to/chat.json`

它会自动完成：导入数据 -> 分析 -> 生成报告 -> 精修报告 -> 渲染 HTML。

主要输出在 `output/`：

- `output/imported.json`：预处理后的输入数据
- `output/members/`：按成员拆分的消息文件
- `output/scores/`：成员打分明细
- `output/analyze.json`：全量分析结果（成员分数 + 精彩内容）
- `output/report.md`：全量 Markdown 报告
- `output/report_refined.md`：精修后的 Markdown 报告（优化“本期看点”）
- `output/report_final.html`：最终可分享 HTML 页面
- `output/low_quality_members.md`：低质/低活跃成员名单

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

确保 `output/analyze.json` 存在且格式正确

## License

MIT
