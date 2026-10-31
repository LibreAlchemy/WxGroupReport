# 群聊记录分析工具 (WxGroupReport)

基于 AI 的微信群聊分析工具，自动分析群成员消息质量，生成 Markdown/HTML 周期报告。

## 功能特性

- 🤖 **AI 分析**: 发言质量智能评分
- 📊 **报告生成**: 输出 Markdown/HTML 格式的群聊周期报告
- 🏆 **活跃排行**: 自动识别高活跃度成员
- ⚠️ **低质检测**: 自动识别低质量/低活跃成员

## 技术栈

- **AI 模型**: 支持主流模型厂商 (通过 [LiteLLM](https://github.com/BerriAI/litellm))
- **脚本**: Python 3.10+
- **模板**: Jinja2

## 项目结构

```text
WxGroupReport/
├── .env.example              # 环境变量模板
├── .gitignore
├── requirements.txt          # Python 依赖
├── .agents/
│   └── skills/               # Agent Skills
└── output/                   # 输出结果
    ├── members/              # 成员消息文件
    ├── scores/               # 成员打分结果
    ├── imported.json         # 预处理数据
    ├── dialogue.json         # 带结构化引用的完整对话索引
    ├── analyze.json          # 分析结果
    ├── report.md             # 产出报告
    ├── report_refined.md     # 精修后的报告
    └── scores.md             # 成员综合分排名
```

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/LibreAlchemy/WxGroupReport.git
cd WxGroupReport
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

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

可选配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AI_BASE_URL` | OpenAI 兼容网关地址（按需） | - |
| `MAX_ANALYZE_WORKERS` | 分析并发数 | `10` |
| `AI_TEMPERATURE` | 采样温度，有效范围 `0.0`-`2.0`；留空或非法值回退默认 | `0.1` |
| `REASONING_EFFORT` | 思考等级，取值 `minimal`/`low`/`medium`/`high`/`xhigh`；留空表示关闭 | `high` |

### 4. 准备输入数据

将微信聊天记录导出为 ChatLab JSON 或新版微信导出格式（`schemaVersion: 1`），放到任意位置，如 `data/20260101-20260131.json`。

新版导出不包含完整成员名单，因此报告中的“总成员数”按实际发言成员统计，不包含从未发言的群成员。

分析阶段会读取 `output/dialogue.json`，自动补充局部群聊上下文并按预算分块。质量分由信息密度、原创性、资源价值、互动价值和持续性组成；最终分数会进行同批次温和校准。

### 5. 开始执行

在任意 TUI Agent 窗口中，提供数据文件的路径后回车：

```
path/to/data.json
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
