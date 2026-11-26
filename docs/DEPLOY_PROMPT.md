# 一键部署提示词 / Deploy Prompt

把下面整段复制给 Claude Code、Codex CLI 或任何能执行终端命令的 AI 助手，它会按步骤把 Context Gate 装好并接上本机接口。
Copy the whole block below into Claude Code / Codex CLI (or any agent that can run shell commands).

---

```text
你是我的本机部署助手。目标：在这台电脑上部署开源项目 Context Gate（https://github.com/ericz218/context-gate），并把它接到我本机已有的 AI 工具和本地接口上。

## 规则
- 每一步先只读探测、再动手；每步结束给出「命令 → 实际输出 → 结论（成功/跳过/失败+原因）」。不要编造任何输出。
- 所有服务只允许监听 127.0.0.1；不要开放公网端口，不要关闭任何安全校验。
- 需要 API Key 时让我自己填进环境变量或控制台设置页，不要把密钥写进仓库、命令历史或日志。
- 可选模块探测不到就标记「跳过」并继续，不要为了它安装我没要求的软件。
- 修改 shell 配置（~/.zshrc 等）或 AI 工具配置前，先把要加的内容给我看。

## 第 0 步：环境探测（只读）
1. 操作系统与架构：uname -sm（完整功能面向 macOS；Linux 可用控制台和 CLI，没有 LaunchAgent 和桌面壳）。
2. python3 --version，要求 ≥ 3.9。只用标准库，不需要 pip install。
3. 已装的 AI 工具：which claude codex ollama node；ls -d ~/.claude/projects ~/.codex/sessions 2>/dev/null（用量统计会自动读这些本地日志）。
4. 本地模型：curl -s --max-time 2 http://127.0.0.1:11434/api/tags（Ollama，有就记下模型名）。

## 第 1 步：拉代码（放在 ~/Projects 下）
上下文网关默认只允许打包 ~/Projects 和 ~/Documents 下的项目，所以仓库和要用它的项目都放在这两个目录里。
  mkdir -p ~/Projects && cd ~/Projects
  git clone https://github.com/ericz218/context-gate.git && cd context-gate
  python3 -m unittest tests.test_console_app 2>&1 | tail -3   # 冒烟测试，预期最后一行是 OK；失败就原样贴出，不要改测试

## 第 2 步：启动控制台
  python3 console/app.py
它会打印 http://127.0.0.1:<端口>/<随机令牌>/ 并自动打开浏览器。
- 想固定端口、不自动开浏览器：python3 console/app.py --no-browser --port 8765
- 状态目录默认 ~/.local/state/context-gate（权限 0700），可用 --state-dir 或 CONTEXT_GATE_STATE 覆盖。
- 验证：打开链接能看到「总览」页；首次会弹新手引导，语言按系统自动识别，可在设置里切换。
（这一步启动的是前台进程。后续步骤请另开终端，或用后台方式运行。）

## 第 3 步：启动本地上下文网关服务
  python3 manage.py install
  python3 manage.py doctor
预期 doctor 输出 JSON 中 "service": true。没配置 Jev 审核时 "jev": false、退出码为 1，这是正常的：网关会退回到完整上下文，不影响使用。

## 第 4 步：把网关接进 AI 编程工具（MCP，stdio）
仓库绝对路径记为 $CG（例如 ~/Projects/context-gate）。先把将要执行的命令给我看，确认后再执行：
- Claude Code：claude mcp add context-gate -- python3 "$CG/gate_mcp.py"
  验证：claude mcp list 里出现 context-gate，状态为已连接。
- Codex CLI：codex mcp add context-gate -- python3 "$CG/gate_mcp.py"
  如果当前版本没有 mcp add 子命令，就在 ~/.codex/config.toml 里追加：
    [mcp_servers.context-gate]
    command = "python3"
    args = ["<CG 的绝对路径>/gate_mcp.py"]
- 其他支持 MCP 的客户端：同样用 stdio 方式启动 python3 "$CG/gate_mcp.py"，工具名是 context_pack。
接入后，在我的项目根目录放一个 MEMORY.md，把必须原样保留的核心记忆写在
[CORE_MEMORY_START] 和 [CORE_MEMORY_END] 两个标记之间，调用 context_pack 时 memory 参数传这个文件。

## 第 5 步：可选本地接口（逐项探测，有就接，没有就跳过）
各项环境变量的完整说明见仓库 docs/LOCAL_INTERFACES.md。
a. 管家模型（Butler）
   - 有 Ollama：默认连 http://127.0.0.1:11434，自动挑 Qwen 14B 或第一个已装模型；想指定模型就设 CONTEXT_GATE_OLLAMA_MODEL=<模型名>。
   - 没有 Ollama、想用云端 OpenAI 兼容接口：让我在控制台「设置」里填，或设置 CONTEXT_GATE_BUTLER_API_URL / CONTEXT_GATE_BUTLER_API_KEY / CONTEXT_GATE_BUTLER_MODEL。
b. 本地模型路由（Local Model Router）：只有我本机已经在跑兼容的路由服务时才接，设置 LMR_ROUTER_URL（默认 http://127.0.0.1:8787）、LMR_CONSOLE_CONNECTION、ROUTER_DB。
c. 共享记忆（MemoryOS 兼容接口）：只有本机已有该服务时才接，设置 MEMORY_OS_HTTP_URL（必须是回环地址）和 MEMORY_OS_API_TOKEN。没有的话，网关会自动退回到 MEMORY.md 里的核心记忆。
d. 决策审核（Jev / Laya）：需要我提供 JEV_MCP_API_KEY；本地 Laya 服务设置 LAYA_URL（必须是回环地址）。没有就跳过，网关会退回到完整上下文、原文搜索。
e. 用量统计：不需要配置，控制台会直接读 ~/.claude/projects、~/.codex/sessions 等本地日志。想让它在后台定时导入：python3 usage_import.py --install（macOS LaunchAgent）。
设置环境变量时，把要加到 ~/.zshrc 的 export 行列给我确认，再追加，然后重启控制台让它生效。

## 第 6 步：macOS 桌面壳（可选，需要我确认）
- 原生 Swift 窗口：./console/app_bundle/build.sh（需要 Xcode 命令行工具，会安装到 /Applications/Context Gate 控制台.app，全局快捷键 ⇧⌘E）。
- Electron 刘海面板：cd console/notch && npm install && npm start（需要 Node.js）。

## 收尾：给我一张表
| 模块 | 状态（已接入/跳过/失败） | 地址或路径 | 验证证据 |
覆盖：控制台、网关服务、Claude Code MCP、Codex MCP、Ollama 管家、模型路由、MemoryOS、Jev/Laya、用量导入、桌面壳。
最后告诉我：控制台访问链接、停止网关的命令（python3 manage.py stop）、需要我手动补的配置项。
```

---

## 常见问题 / FAQ

- **`manage.py doctor` 退出码为 1**：通常只是 `"jev": false`（没配审核服务），网关本身 `"service": true` 就能用。
- **context_pack 提示项目路径不被允许**：把项目移到 `~/Projects` 或 `~/Documents` 下。
- **控制台打不开**：确认终端里打印的链接带了随机令牌路径；令牌文件在状态目录里，权限是 `0600`。
- **停止服务**：`python3 manage.py stop`；恢复用 `python3 manage.py install`。
