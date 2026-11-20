# Context Gate

**Context Gate** 是一个本地优先的 AI 上下文中间件与多 Agent 控制台（含 macOS 原生 Swift 壳 & Electron 顶部刘海面板壳）。  
核心后端完全基于 **Python 3.9+ 标准库**，零第三方 Python 依赖，开箱即用。

A local-first AI context middleware, usage ledger, multi-agent console, and desktop app shell (native macOS Swift shell + Electron notch panel shell). Zero third-party Python dependencies (Python 3.9+ stdlib only).

---

## 核心功能 / Features

- **控制台 Web App (`console/app.py`)**：
  - **总览 / 计费明细 / 请求账本**：SQLite 本地只读仪表盘，展示请求数、实际输入/输出/缓存读/缓存写 token、按付费设置与按官方标价双模式对比（`prices.py`）。
  - **输出速度（TPS）**：输出 tokens ÷ 请求总耗时（含等待首个 token），只统计有耗时记录的成功请求；总览「平均响应时间」方块显示整体平均与中位数，计费里点开模型可看平均、中位数、P10–P90、测速请求数与逐条速度。未记录耗时的平台显示「–」，不推算。
  - **订阅额度守卫 (`console_quota.py`)**：集中监控 Claude Code / Codex 的 5 小时与周额度、提醒门槛与可选本地任务暂停（详见 [docs/QUOTA_GUARD.md](docs/QUOTA_GUARD.md)）。
  - **模型钱包 (`console_wallet.py`)**：多供应商余额、预留、流水与自定义模型定价目录（`console/wallet_catalog.json`）。
  - **任务中心 / 预约 / 管家 (`control_center.py`, `console_butler.py`, `console_schedule.py`)**：统一派发、查看 diff、验收/回滚、定时执行。
  - **多 Agent 群聊 (`group_chat.py`)**：在单一会话中编排 Claude Code / Codex / ZCode 成员，支持 `/mod` 角色分工与上下文压缩自动交接、附件与成果归档。
  - **待办 & 置顶浮窗 (`console_todo.py`)**、**文档/PDF/Office 本地处理 (`console_import.py`, `console_pdf.py`, `console_office.py`)**、**全文搜索 (`console_search.py`)**。
- **上下文网关与证据链 (`context_gate.py`, `gate_service.py`, `gate_run.py`, `gate_proxy.py`, `evidence.py`)**：
  - 支持 Claude Code、Codex CLI、ZCode 及 OpenAI Responses / Chat Completions / Anthropic Messages 协议逐轮裁剪与打包。
  - 保留 `[CORE_MEMORY_START] ... [CORE_MEMORY_END]` 核心记忆原文，支持 append-only SHA-256 哈希链任务证据（`evidence.py`）。
  - 支持本地用量哨兵代理（`passthrough_proxy.py`）与无拦截本地日志导入（`usage_import.py`）。
- **双桌面壳 / Desktop App Shells**：
  - **macOS 原生 Swift 壳**（`console/app_bundle/`）：WKWebView 独立窗口、全局快捷键 `⇧⌘E`、菜单栏待办浮窗、系统通知。
  - **Electron 刘海面板壳**（`console/notch/`）：贴顶自动收起、快捷键 `⇧⌘E` 展开、多屏跟随、托盘自启。

---

## 快速开始 / Quick Start

### 1. 启动控制台（零依赖）

```sh
git clone https://github.com/ericz218/context-gate.git
cd context-gate
python3 console/app.py
```

启动后会自动打开本地浏览器（仅监听 `127.0.0.1` + 随机路径令牌）。常用参数：

```sh
python3 console/app.py --no-browser --port 8765 --state-dir ~/.local/state/context-gate
```

### 2. 构建 macOS 原生壳 App（推荐 macOS 13+）

```sh
./console/app_bundle/build.sh
```

脚本会自动识别本机架构（Apple Silicon / Intel）和当前仓库路径，编译并安装 `/Applications/Context Gate 控制台.app`，默认绑定全局快捷键 `Shift + Cmd + E`（可通过环境变量 `CONTEXT_GATE_ROOT` 覆盖项目路径）。

### 3. 运行或打包 Electron 刘海面板壳（可选）

```sh
cd console/notch
npm install
npm start          # 开发模式运行
# npm run build    # 打包 macOS DMG（输出在 dist.noindex/）
```

### 4. CLI 与上下文网关服务（可选）

```sh
# 安装并检查本地 Context Gate 服务
python3 manage.py install
python3 manage.py doctor

# 生成单个 Context Pack
python3 context_gate.py --root /path/to/your-project \
  --memory /path/to/your-project/MEMORY.md \
  --request "你的任务描述" --output /tmp/context.json

# 经逐轮网关运行任务（claude / codex / gpt / zcode）
python3 gate_run.py --platform claude --root /path/to/your-project \
  --memory /path/to/your-project/MEMORY.md \
  --request "你的任务描述" --output /tmp/task.json

# 本地日志用量导入与统计
python3 usage_import.py
python3 token_stats.py
```

---

## 开源模型与外部工具链接 / Open-Source Models & Tools

本仓库**不包含任何模型权重文件**。你可以按需安装以下开源模型或 CLI 工具配合使用：

- **本地开源模型运行环境**：
  - [Ollama](https://ollama.com/) — 本地一键运行开源模型（默认监听 `http://127.0.0.1:11434`）
  - [Qwen2.5](https://ollama.com/library/qwen2.5) / [Qwen3](https://ollama.com/library/qwen3) / [Qwen2.5-Coder](https://ollama.com/library/qwen2.5-coder)（例如 `ollama pull qwen2.5:14b`）
  - [DeepSeek-R1](https://ollama.com/library/deepseek-r1) / [Llama 3.3](https://ollama.com/library/llama3.3) / [Gemma 3](https://ollama.com/library/gemma3)
- **兼容云端 API 聚合 / 免费额度入口**：
  - [OpenRouter](https://openrouter.ai/)（含众多开源模型与 `:free` 端点）
  - [NVIDIA NIM](https://build.nvidia.com/)（OpenAI 兼容接口）
- **原生 Coding Agent CLI**：
  - [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
  - [OpenAI Codex CLI](https://github.com/openai/codex)
- **可选决策审核服务（Jev / Laya 接口）**：
  - [TypeSafe / Jev](https://typesafe.ai/) 或任何遵循 `docs/LOCAL_INTERFACES.md` 协议的自建本地回环决策服务。

---

## 可选本地服务与接口适配 / Optional Local Services

Context Gate 中的以下模块均为**可选本地服务**——未安装或未配置时自动降级，不影响其余核心功能：

| 模块 | 说明 | 配置方式 |
| :--- | :--- | :--- |
| **模型路由（Local Model Router）** | 连接你自己的本地模型路由器管理桥与只读 SQLite 统计 | `LMR_CONSOLE_CONNECTION`、`LMR_ROUTER_URL`、`ROUTER_DB` |
| **共享记忆（MemoryOS 接口）** | 通过标准本地 HTTP 回环接口读取加权项目记忆与阅读文档；未配置时自动回退到本地 `[CORE_MEMORY_START]` 文件记忆 | `MEMORY_OS_HTTP_URL`、`MEMORY_OS_API_TOKEN`、`MEMORY_OS_DIR`、`MEMORY_OS_HUMAN_DIR` |
| **决策审核（Jev / Laya）** | 上下文裁剪首审/二审与模糊搜索排序；未配置时回退完整上下文/原文搜索 | `JEV_MCP_API_KEY`、`JEV_MCP_BASE_URL`、`LAYA_URL`、`config.example.json` |
| **管家模型（Butler）** | 支持 Ollama 本地开源模型、NVIDIA NIM、OpenRouter 或自定义 OpenAI 兼容接口 | 控制台设置页或 `CONTEXT_GATE_OLLAMA_URL` / `CONTEXT_GATE_OLLAMA_MODEL` |
| **单机 Git 同步 (`tools/git_sync_engine.py`)** | 本地 Git 仓库与 GitHub 同步管理（多机状态同步暂不包含在当前开源版本中） | `GITSYNC_HOME`、`GITSYNC_GITHUB_OWNER` |

完整环境变量、HTTP 协议与文件格式说明见 [docs/LOCAL_INTERFACES.md](docs/LOCAL_INTERFACES.md)。  
参考价格口径说明见 [docs/PRICE_REFERENCES.md](docs/PRICE_REFERENCES.md)，实现规格见 [SPEC.md](SPEC.md)。

---

## 安全模型 / Security Model

- 所有本地 HTTP 服务严格绑定 `127.0.0.1`，拒绝带跨站 `Origin` 头的请求。
- 本地连接文件与令牌均以 `0600` 权限写入状态目录（`~/.local/state/context-gate/`），不进入代码仓库。
- 上游及本地回环调用均禁用自动 HTTP 重定向，避免凭据被重定向泄露。
- 控制台日志与搜索展示自动经过敏感字段脱敏（`console_data.redact_text`）。

---

## 运行测试 / Tests

```sh
python3 -m unittest discover -s tests -v
```

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see the [LICENSE](LICENSE) file for details.
