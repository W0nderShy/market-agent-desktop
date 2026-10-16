---
name: market-trend
description: "分析当前 Bitget 图表的趋势结构。用户询问量价、技术分析或行情判断时，自动使用当前标的和周期，无需用户重复指定。"
---

# 趋势结构

EMA21/50/100/200 排列、价格高低点结构与趋势强度。分数是启发式，不是收益概率。

## 数据和调用

这是 krzysu/market-skills 的项目适配版；MIT 来源及固定提交见项目 vendor/market-skills/UPSTREAM.json。数学计算由原项目 lib.py 完成，数据仅来自本终端的 Bitget market-context.json。禁止切换到 Yahoo、Kraken 或其他行情源来填补数据。

使用 dsh 的终端执行工具运行本 Skill 目录下的 `scripts/run.py`：

```powershell
python "<本 SKILL.md 所在目录>/scripts/run.py"
```

请将占位路径替换成加载此 Skill 时返回的真实目录。程序自行定位项目根目录，无需指定标的、周期或密钥；无需 pip/uv 安装依赖。

需要综合分析时，在项目根目录执行 `python scripts/run_market_skill.py all`；若工作目录是 runtime，执行 `python ../scripts/run_market_skill.py all`，一次计算五类能力，避免重复调用。

## 工作步骤

1. 执行脚本，确认输出的 symbol、interval 与当前图表一致，并检查 captured_at_ms、analyzed_bars。脚本默认排除未收盘蜡烛；若 stale/unavailable/insufficient 错误，明确说明并等待图表恢复，不编造指标。
2. 使用 results.market-trend 的实际计算值回答。计算窗口以当前周期的“根数”为单位，不把 15 分钟的 30 根称为 30 天；支持阻力的低价币价位应以原始 OHLCV 精度复核。
3. 先给简洁结论，再给关键数据、反例和失效条件。过程交给界面折叠，不在最终回答粘贴整份 JSON。区分事实、启发式规则和推断。
4. 如需新闻解释，可使用 dsh 的 web_search/web_fetch，注明发布时间与链接；新闻结果不能覆盖或伪造 Bitget 指标数据。
5. 此 Skill 只做分析，不执行交易、不申请 Bitget 私有密钥、不修改自选或凭据。用户切换标的后重新运行，不沿用旧结果。
