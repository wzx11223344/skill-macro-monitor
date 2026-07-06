# 宏观经济监测 (Macro Economy Monitor)

AI 代理技能 —— 自动抓取中国宏观经济核心指标，生成结构化监测简报。

## 功能概述

`macro-econ-monitor` 是一个面向 AI 代理的宏观经济监测工具，基于 [akshare](https://github.com/akfamily/akshare) 提供的中国宏观数据 API，自动拉取 PMI、CPI、PPI、社会融资规模、进出口贸易差额等核心指标，并生成结构化报告。

### 覆盖指标

| 指标 | akshare 函数 | 数据源 |
|------|-------------|--------|
| 官方制造业 PMI | `macro_china_pmi` | 国家统计局 |
| CPI 同比 | `macro_china_cpi_yearly` | 国家统计局 |
| PPI 同比 | `macro_china_ppi_yearly` | 国家统计局 |
| 社会融资规模增量 | `macro_china_shrzgm` | 中国人民银行 |
| 进出口贸易差额 | `macro_china_trade_balance` | 海关总署 |

### 三种报告模式

| 模式 | 命令 | 输出 | 适用场景 |
|------|------|------|----------|
| 日报 (brief) | `python monitor.py brief` | Markdown 终端输出 | 每日快速浏览 |
| 周报 (weekly) | `python monitor.py weekly` | Markdown 终端输出 | 每周趋势回顾 |
| 月报 (monthly) | `python monitor.py monthly -o report.html` | HTML 交互报告 | 深度分析存档 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行

```bash
# 日报
python monitor.py brief

# 周报
python monitor.py weekly

# 月报 (生成 HTML)
python monitor.py monthly --output report.html
```

### 3. 作为 Skill 注册到 AI 代理

将本目录放置于代理的 skills 目录下，并在代理配置中引用 `SKILL.md`。

当用户提问包含"宏观经济""PMI""CPI""经济简报"等关键词时，代理自动调用本技能抓取最新数据并生成回复。

## 架构设计

```
monitor.py
├── 缓存层 (.cache/)          ← 24h TTL JSON 缓存，避免重复 API 请求
├── 数据获取层 (akshare)       ← 调用 akshare 宏观接口
├── 指标解析层                 ← 趋势判断、分位计算、交叉信号
└── 输出层                     ← Markdown 终端 / Plotly HTML
```

### 缓存策略

- 每个 akshare API 调用结果缓存为 JSON 文件
- TTL 设为 24 小时，超时自动清除
- 缓存目录：`<skill_dir>/.cache/`

### 信号规则

| 信号 | 触发条件 |
|------|----------|
| 需求不足 | PMI 下行 + PPI 下行 |
| 通缩压力 | CPI 同比 < 0 |
| 外需走弱 | 贸易顺差收窄 |
| 宽信用 | 社融增速上行 |
| 融资需求不足 | 社融增速放缓 |

## 依赖

- Python >= 3.8
- akshare >= 1.10.0
- pandas >= 2.0.0
- plotly >= 5.0.0
- jinja2 >= 3.0

## 许可证

MIT
