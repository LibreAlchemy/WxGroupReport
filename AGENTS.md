# AGENTS.md

本仓库当前以「文档中心」为主（tracked files 基本都在 `docs/`）。代码实现（如 Python/FastAPI/pytest 等）在文档里有规划，但尚未提交到仓库。

## 1) 先读这些（Agent 导航）

- 入口与目录：`docs/README.md`
- 文档体系与元数据规范：`docs/通用文档格式规范.md`
- 技术方案/规划：`docs/技术/系分/系分文档.md`、`docs/技术选型报告.md`

工作顺序（强约定）：

1. 读 `docs/开发/需求清单/`（任务、验收标准、优先级）
2. 读 `docs/开发/问题排查/`（历史坑与规避方案）
3. 读 `docs/技术/系分/`（设计决策与边界）
4. 实现/改文档
5. 更新需求清单状态 + 记录已实现功能/问题排查

## 2) Build / Lint / Test 命令

### 2.1 当前仓库现状

- 仓库里没有可执行的构建系统/测试套件（无 `pyproject.toml`/`requirements.txt`/`src/` 等 tracked 代码）。
- 因此：`build/lint/test` 以“可选的文档校验” + “未来代码落地后的建议命令”为主。

### 2.2 文档检查（可选，但推荐）

说明：仓库未内置 Node/Python 工具链配置；以下命令依赖本机已安装 Node.js。

```bash
# Markdown 语法/风格检查（一次性运行，不写入 repo）
npx -y markdownlint-cli2 "docs/**/*.md"

# Markdown 格式化（谨慎：会改动很多行；先跑在小范围文件上）
npx -y prettier@latest --write "docs/**/*.md"
```

### 2.3 未来（当 Python 代码落地到仓库后）

如果后续按文档规划引入 Python 项目结构（例如 `src/`、`requirements.txt`、`pytest`），建议命令如下：

```bash
# 创建并启用虚拟环境（Windows PowerShell/或使用你习惯的方式）
python -m venv .venv

# 安装依赖（若存在 requirements.txt）
python -m pip install -r requirements.txt

# 运行测试
pytest
```

单测精确运行（重点）：

```bash
# 运行单个测试文件
pytest tests/test_parser.py

# 运行单个测试用例（函数）
pytest tests/test_parser.py::test_parse_json

# 运行 class 内单测
pytest tests/test_parser.py::TestParser::test_parse_json

# 按关键字筛选
pytest -k "parse and json"
```

（可选）若引入 lint/format：

```bash
# 代码规范（建议：ruff + black + mypy；以实际配置为准）
ruff check .
black .
mypy .
```

## 3) 仓库约定与安全边界

- `data/`、`group/`、`.env*`、数据库文件（`.db`/`.sqlite*`）都可能包含隐私或敏感信息；默认不提交。
- 以 `.gitignore` 为准：`group/`、`.env*`、`.pytest_cache/`、`.venv/` 等已被忽略。
- 新增任何会“外传数据”的功能前，先在 `docs/技术/系分/` 写清楚隐私策略与脱敏点（尤其涉及 LLM API）。

## 4) 文档风格与规范（本仓库最重要的“代码风格”）

### 4.1 文档必须可被 Agent 解析

- 新增/大改文档：优先从 `docs/templates/` 复制模板开始。
- 元数据：遵循 `docs/通用文档格式规范.md` 的 YAML front-matter。
- 验收标准：使用 checkbox 形式（`- [ ] AC-001: ...`）。
- 引用：可用 `#[[file:docs/技术/系分/xxx.md]]` 形式做精确指向。

### 4.2 Markdown 书写约定

- 标题层级：从 `#` 开始，逐级递进，不跳级。
- 列表：同一层级保持统一风格（全用 `-` 或全用 `1.`）。
- 表格：对齐不强制，但列含义必须清晰；字段名尽量稳定（便于后续自动解析）。
- 代码块：总是标注语言（```python/```json/```bash 等）。
- 变更记录：重要文档在文末维护 `最后更新`/`updated` 字段，并说明变更原因。

### 4.3 命名与路径

- 目录归属：按 `docs/README.md` 的目录结构放置（产品/技术/开发/测试/归档）。
- 文件名：优先中文语义化命名；模板文件保持 `*_模板.md`。
- 避免“同名不同义”：同目录下不要出现多个含义相近的文档（会干扰检索与 Agent 选择）。

### 4.4 文档中的“接口/数据结构”写法

- 类型定义：可用 TypeScript interface 形式描述（如 `docs/技术/系分/系分文档.md`），但字段含义要配说明表。
- 示例数据：尽量脱敏；真实样本放在本地忽略目录（如 `data/`/`group/`），文档只放结构片段。

## 5) 代码风格（当仓库开始提交代码时遵循）

> 说明：以下为“预先约定”。一旦仓库出现实际 lint/formatter 配置（如 ruff/black/mypy），以配置为准并更新本文件。

### 5.1 语言与目录

- Python：按 `docs/技术选型报告.md`/`docs/技术/系分/系分文档.md` 的结构建议组织（`src/`、`tests/`、`templates/`、`output/`、`data/`）。
- Web（若引入 FastAPI）：路由/模板/静态资源分层清晰，避免把业务逻辑写进路由函数。

### 5.2 Imports

- 分组顺序：标准库 / 第三方 / 本地模块；组间空一行。
- 禁止循环依赖：遇到时优先抽公共模块或延迟导入（但要解释原因）。
- 只导入需要的符号；避免 `from x import *`。

### 5.3 格式化与可读性

- 单行长度：建议 88~100 字符（与 black 习惯一致）。
- 函数保持短小、单一职责；复杂逻辑拆分为纯函数并可测试。
- 对外接口（CLI/Skill API/HTTP API）要有稳定输入输出结构。

### 5.4 Types 与数据模型

- 全部对外边界做类型校验：文件路径、时间范围、批大小、阈值等。
- 优先使用 `dataclasses`/`TypedDict`/`pydantic`（以实际依赖为准）表达结构化数据。
- 解析 JSON/JSONL 时：对缺失字段/类型错误给出可定位的错误码与上下文。

### 5.5 命名规范

- Python：模块/函数/变量用 `snake_case`；类用 `PascalCase`；常量用 `UPPER_SNAKE_CASE`。
- 测试：文件 `test_*.py`；用例名表达行为（`test_parse_json_missing_members_returns_error`）。

### 5.6 错误处理与重试

- 业务异常：定义项目级基类异常 + `code` 字段（参考 `docs/技术/系分/系分文档.md` 示例）。
- 捕获范围：只捕获可处理的异常；不要用裸 `except:` 吞错。
- 外部 API：必须有超时；对超时/限流做指数退避重试；失败要有降级策略（例如默认分）。
- 日志：INFO 记录关键里程碑，WARNING 记录可恢复问题，ERROR 记录不可恢复问题；避免打印敏感内容。

## 6) Cursor/Copilot 规则

- 未在仓库中发现 `.cursor/rules/`、`.cursorrules` 或 `.github/copilot-instructions.md`。
- 若后续添加，请把核心约束同步到本文件并保持一致（避免 Agent 行为冲突）。
