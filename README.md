# Market Agent Desktop

基于完整 DeepSeek Harness 源码与 LangGraph 的本地市场监控项目。仓库目前私有，公开需要项目所有者明确决定。

## 当前里程碑

前四步的开发底座：独立仓库、源码构建 dsh Desktop、Bitget 自选行情、持久化采集流程。通过可重放源码补丁将行情终端设为 dsh Desktop 主页面，提供自选列表、真实 K 线与成交量、行情详情和持久事件；通过菜单和对话按钮切换原 dsh 会话界面。模型研究、休息触发脚本、持续思考、对话 agent、托盘和 Windows 安装包属于后续里程碑。不要把采集事件理解为投资信号或已完成的研究。

监控读取公开市场数据，不需要 Bitget API Key，不调用账户和交易接口，也不会调用模型。默认自选列表为空。

## Windows 开发环境

- Windows x64；Python 3.12；Node.js 24；Git；pnpm 11（当前验证环境 11.19.0，上游 manifest 为 11.7.0）。
- 首次安装需要联网下载 Python、Node 依赖和 Electron，源码构建需要数分钟和较多内存。

```powershell
git clone --recurse-submodules https://github.com/W0nderShy/market-agent-desktop.git
cd market-agent-desktop
powershell -NoProfile -File scripts/setup.ps1
powershell -NoProfile -File scripts/start.ps1
```

私有仓库克隆需要你自己的 GitHub 登录。不要向项目配置文件填写 GitHub 令牌。已完成构建后，`start.ps1` 启动后台和整合行情首页的 dsh Desktop。`-MonitorOnly` 仅用于开发调试独立行情窗口。这阶段交付的是源码开发环境，不是免依赖安装包。

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
node --test desktop/policy.test.cjs desktop/chart.test.cjs
python scripts/check-privacy.py
```

CI 运行无密钥后端回归、桌面 IPC 白名单测试和已跟踪文件隐私检查。CI 尚不构建庞大的上游 Desktop；真实网络冒烟单独执行。基础正则扫描不等于完整密钥检测或历史审计。

见 [数据隐私要求](docs/DATA_PRIVACY.md)。真实密钥、监控列表、日志和会话禁止提交；忽略规则不提供磁盘加密。后端禁用 LangSmith 自动追踪；上游 dsh 的遥测与工具权限仍需按该文档做完整审计。当前原版 dsh 的通用工具权限尚未收紧为最终市场研究隔离配置。

## 常见问题

- **嵌套项目 React 类型冲突**：安装脚本为 dsh 显式配置 React 依赖提升，避免向上读取其他项目的 React。直接 pnpm 构建时保留脚本中的 `pnpm_config_public_hoist_pattern`。
- **Electron 二进制缺失**：运行 `node apps/desktop/node_modules/electron/install.js`（在 dsh 目录）；安装脚本已包含。
- **服务启动失败**：查看 `runtime/service.err.log`，确认端口 8765 未被占用。同一目录不能同时运行 `serve` 和 `once`。
- **dsh 窗口未出现**：查看私有 `runtime/dsh.err.log`；不要直接上传未经脱敏的上游开发日志。
- **市场接口不可达**：显示错误并保留旧行情及过期标记，不制造价格数据。

上游文档：[dsh Desktop](https://github.com/deepseek-ai/deepseek-harness/tree/master/apps/desktop)、[Bitget 市场接口](https://www.bitget.com/docs/catalog/market/market-data)、[LangGraph 持久化](https://docs.langchain.com/oss/python/langgraph/persistence)。
