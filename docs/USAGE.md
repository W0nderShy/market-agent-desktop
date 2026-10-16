# 安装与使用指南

完整操作与开发说明。项目概览见 [README](../README.md)。

## Windows 开发环境

- Windows x64；Python 3.12；Node.js 24；Git；pnpm 11（当前验证环境 11.19.0，上游 manifest 为 11.7.0）。
- 首次安装需要联网下载 Python、Node 依赖和 Electron，源码构建需要数分钟和较多内存。

```powershell
git clone --recurse-submodules https://github.com/W0nderShy/market-agent-desktop.git
cd market-agent-desktop
powershell -NoProfile -File scripts/setup.ps1
powershell -NoProfile -File scripts/start.ps1
```

已完成构建后，`start.ps1` 启动后台和整合行情首页的 dsh Desktop。`-MonitorOnly` 仅用于开发调试独立行情窗口。这是源码开发环境，不是免依赖安装包。GitHub 自动生成的 Source code 压缩包不含 submodule 源码；需要完整 dsh 源码时请按上面的命令递归克隆。

完成首次安装后，可运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-launcher.ps1` 生成项目根目录的 `Trading_Terminal.exe`，以后双击即可启动。它只是便捷入口，不包含 Python、Electron 或密钥。可加 `-CopyToParent` 将入口复制到工程的上一级目录；这种布局要求工程目录名为 `AI_back`。

在行情窗口选择 SPOT 或合约类别，输入交易品种代码后点击“验证并添加”。同名现货和合约分别保存。股票相关产品必须使用 Bitget 实际返回的交易代码和类别，不自动推断传统股票代码。添加后点击“立即采集”，或等下一次 60 秒轮询。无数据、过期数据和接口错误会显示状态。

图表使用真实 Bitget K 线，支持 1m、5m、15m、1H、4H、1D。最新 K 线可能尚未收盘，会随行情更新。界面借鉴常见行情终端布局，不使用 TradingView 商标或声称其官方集成。

关闭行情窗口不会停止独立监控进程；停止服务：

```powershell
powershell -NoProfile -File scripts/stop.ps1
```

dsh 窗口单独关闭。当前没有托盘、开机自启或服务进程崩溃自动重启；重新运行启动脚本恢复。电脑休眠或关机期间不会采集数据。

## 命令行与配置

```powershell
.venv/Scripts/python.exe -m market_monitor.cli --help
.venv/Scripts/python.exe -m market_monitor.cli serve --port 8765 --interval 60
```

也可复制 `config/watchlist.example.json` 到忽略目录 `config/private/watchlist.json`，填入 `{"items":[{"symbol":"BTCUSDT","category":"SPOT"}]}`（仅示例）。服务未运行时：

```powershell
.venv/Scripts/python.exe -m market_monitor.cli configure --config config/private/watchlist.json
.venv/Scripts/python.exe -m market_monitor.cli once
.venv/Scripts/python.exe -m market_monitor.cli status
```

同一 runtime 只允许一个进程打开；运行中通过桌面查看状态。独立测试目录可用 `--runtime runtime/smoke`，该参数放在子命令之前。真实配置在更新前验证所有品种，失败不会覆盖原列表。

## 结构与恢复

- `vendor/deepseek-harness`：完整上游源码 submodule，固定到 `5dda764ed3aa172535a7967b06ff95d9cbfe536a`，保持上游许可证。`patches/dsh-market-home.patch` 保存本项目 Desktop 整合改动，安装时幂等应用，不把无法从远程获取的本地提交用作 submodule 版本。
- `desktop/`：行情主页面静态资源、图表及独立调试壳；隔离渲染器，通过有限 IPC 调用本地 API。
- `src/market_monitor/`：Bitget v3 适配、配置验证、SQLite 存储、LangGraph 采集流程、API 与 CLI。
- `runtime/`：私有数据库、检查点、服务令牌、日志、dsh home 和 Electron 状态。
- `tests/`：模拟网络和故障恢复测试；`scripts/`：安装、启动、停止与基础隐私检查。

流程为“定时轮询 → 读取每个自选品种 → 获取 ticker/K 线 → 校验 ticker → 持久化观察和事件”。每轮图执行使用 SQLite 检查点，未完成图在启动后恢复；观察事件按市场、品种和行情时间去重。SQLite WAL 和单实例锁保护进程重启恢复。行情最新价格和 24 小时基础币成交量来自 Bitget，行情时间与本地采集时间分别保存；保存的 K 线是原始接口快照，当前不做异动策略计算。

API 仅绑定 `127.0.0.1:8765`，要求 `runtime/api-token` 中的令牌，拒绝带 Origin 的请求。令牌由 Electron 主进程读取，不向渲染器暴露。接口包括 `GET /api/status`、`GET /api/instruments`、`GET /api/candles`、`PUT /api/watchlist`、`POST /api/poll`、`POST /api/shutdown`。

## 验证与隐私

```powershell
.venv/Scripts/python.exe -m pytest -q
npm ci --prefix desktop --ignore-scripts
npm test --prefix desktop
python scripts/check-privacy.py
```

CI 运行无密钥后端回归、桌面 IPC 白名单测试和已跟踪文件隐私检查。CI 尚不构建庞大的上游 Desktop；真实网络冒烟单独执行。基础正则扫描不等于完整密钥检测或历史审计。

见 [数据隐私要求](DATA_PRIVACY.md)。真实密钥、监控列表、日志和会话禁止提交；忽略规则不提供磁盘加密。后端禁用 LangSmith 自动追踪；上游 dsh 的遥测与工具权限仍需按该文档做完整审计。当前原版 dsh 的通用工具权限尚未收紧为最终市场研究隔离配置。

## 常见问题

- **嵌套项目 React 类型冲突**：安装脚本为 dsh 显式配置 React 依赖提升，避免向上读取其他项目的 React。直接 pnpm 构建时保留脚本中的 `pnpm_config_public_hoist_pattern`。
- **Electron 二进制缺失**：运行 `node apps/desktop/node_modules/electron/install.js`（在 dsh 目录）；安装脚本已包含。
- **服务启动失败**：查看 `runtime/service.err.log`，确认端口 8765 未被占用。同一目录不能同时运行 `serve` 和 `once`。
- **dsh 窗口未出现**：查看私有 `runtime/dsh.err.log`；不要直接上传未经脱敏的上游开发日志。
- **市场接口不可达**：显示错误并保留旧行情及过期标记，不制造价格数据。

上游文档：[dsh Desktop](https://github.com/deepseek-ai/deepseek-harness/tree/master/apps/desktop)、[Bitget 市场接口](https://www.bitget.com/docs/catalog/market/market-data)、[LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)。


### Terminal Agent (DeepSeek)
Open **Agent** in the market terminal. Enter the official DeepSeek API key in the password field and save it; select a model from the running dsh catalog and create a session. Messages automatically include all loaded OHLCV candles for the selected symbol and interval (up to 300), timestamp and unfinished-candle flag. The current chart is also atomically mirrored to runtime/market-context.json for the dsh read tool. Changing the chart invalidates its previous snapshot until new data loads. Stop cancels the active dsh turn; New session starts a separate conversation. The latest session is restored from `runtime/agent-session.json` and dsh stores its history under the private runtime home.

Credentials are written through dsh's write-only credentials interface to its local `.credentials.yaml`; this is local file storage, not encrypted credential-vault storage. The key is never returned to the panel. Runtime files must not be uploaded. Sending a message sends that message and attached market context to DeepSeek. Replies update from dsh snapshots every 1.5 seconds while the panel is open. Long-running autonomous research is managed by the separate tracking window described below. The compact panel displays tool calls/results, explicit allow-once/reject approvals and structured user questions through the dsh event stream. Existing dsh web_search/web_fetch capabilities remain available; external service availability depends on their provider configuration.

Validation: desktop build, bounded IPC operation tests, live dsh model catalog, session creation/history and missing-credential failure path verified without a real API key. A successful official-model response still requires a user-supplied key.

Chart-context integration verified on 2026-09-11: official DeepSeek returned the correct symbol, interval, all 300 candle count and endpoint timestamps; a separate test turn successfully called read on market-context.json and web_search. Switching ZEC 1m to BTC 15m cleared the old snapshot and updated both the panel context and local file to 300 BTC candles. Original user session restored after isolated live tests.


### Five financial analysis skills

Project-scoped dsh skills in `.agents/skills`: market-volume, market-trend, market-s-r, market-breakout, market-exhaustion. These use the pinned MIT math subset under `vendor/market-skills`, not an external data provider. Run `.venv/Scripts/python.exe scripts/run_market_skill.py all` from the project root to analyze the current Bitget chart. The script needs no additional dependencies or API keys. Defaults to closed bars and rejects snapshots older than three minutes. dsh discovers these skills from the project root; restart Desktop if its skill catalog has not refreshed. Agent Settings displays the number enabled.

## 持续跟踪

启动 `Trading_Terminal.exe`，点击顶部“持续跟踪”。支持独立任务开关、红黄绿状态、量价触发、研究记忆、暂停与重启恢复。当前规则见 [长期资产追踪](architecture/LONG_TERM_TRACKING.md)；[第一版记录](architecture/TRACKING_V1.md)供回溯。

每轮研究把五项量价 skill、多周期 Bitget K 线、已接入的外部证据和历史判断交给长期追踪角色，保存 BUY / HOLD / SELL / 证据不足的结构化判断与理由，并在独立窗口显示历次修订。现有外部数据尚不能覆盖基本面、客户资本开支及估值叙事；量价证据明确时仍可给出 BUY / SELL，并标为“量价战术判断”，长期阶段继续单独标示证据缺口。判断需要具体依据与失效条件。此功能不读取用户仓位，也不执行交易。

“动态胜率”由已收盘 Bitget K 线计算未来观察窗口的涨、跌、震荡三类历史条件占比，分别对应 BUY / SELL / HOLD，三项总和固定为 100%。采集到新的收盘 K 线时更新，无需等待模型研究；界面同时显示窗口和样本量。它不是策略交易胜率或已校准的未来概率，历史数据不足时不显示数值。

行情页顶部的“监控”状态片显示本地采集状态，并提供即时采集入口；持续追踪的 BUY / HOLD / SELL 比例固定在行情页右下角。多个标的同时追踪时优先展示当前选中的标的，点击右下角卡片的箭头可打开完整追踪记录。

长期研究的多周期采样、宏观与跨资产证据、状态修订及当前数据缺口见上述文档；分析框架见 [SVG 图与解读](architecture/LONG_TERM_FRAMEWORK_ANALYSIS.md)。

### 个人微信挂载（腾讯官方 ClawBot）

在“持续跟踪”独立窗口展开“微信挂载”，点击“扫码连接”，用自己的微信扫码并按提示完成确认。连接后先向 ClawBot 发一条消息，再开启通知。发送“状态”可查看当前标的的 BUY / HOLD / SELL 比例与结论；发送“研究 ZECUSDT 核验量能能否延续”会把这句话写入该标的下一轮研究方向，研究完成后会推送更新。推送仅包含标的、Bitget 数据源、简短结论、建议和三项历史条件占比，不包含完整 K 线、API 密钥或模型内部提示。

通知由服务进程持久排队，仅在初次建档、研究判断改变或三项比例明显变化时汇报；比例变化还受可选间隔限制，所有自动消息最短间隔 30 分钟。重复结论不会按时间机械重发。为避免微信会话限制，自动通知最多发送 8 条/24 小时。桌面与服务必须保持运行；电脑休眠或关机时不能发消息，恢复后继续处理队列。腾讯官方 iLink 的主动消息依赖最近入站消息的 `context_token`，长时间没有微信互动时可能返回 `ret=-2`；此时消息保持待发送，界面显示 `context_expired`，你再次给 ClawBot 发消息后才会重试。对于其他拒收或不确定结果，系统停止自动重试，避免同一内容重复送达。`sent` 只表示官方 API 返回成功，不代表手机通知已被阅读。此边界来自 [腾讯协议说明](https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol_zh_CN.md)；主动发送时效的实际问题见 [腾讯仓库 issue](https://github.com/Tencent/openclaw-weixin/issues/309)。

微信 Bot 凭证保存在忽略的 `runtime/wechat-ilink.dpapi`，Windows 上使用当前账户的 DPAPI 加密；SQLite 消息队列与用户发来的研究方向保存在 `runtime/wechat.sqlite3`。请不要把 runtime 目录同步到公开仓库。该挂载直接使用腾讯公开的 iLink 协议，不安装 OpenClaw；目前只支持文本消息与上述命令，微信内任意问题的完整 DeepSeek 对话尚未接通。
