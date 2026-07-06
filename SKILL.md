---
name: "macro-econ-monitor"
description: "Automated China macro data monitoring & briefing generation. Invoke when user asks for macro reports, economic briefings, PMI data, or daily/weekly economic snapshots."
---

# 宏观经济监测 (Macro Economy Monitor)

自动抓取中国宏观经济核心指标，生成结构化监测简报。覆盖 PMI、CPI/PPI、社融、进出口、工业增加值、固定资产投资等核心指标。

## 触发条件

当用户提到以下任一关键词时自动调用：
- "宏观经济" / "经济数据" / "经济简报" / "宏观日报" / "宏观周报"
- "PMI" / "CPI" / "PPI" / "社融" / "M2" / "进出口"
- "今天经济怎么样" / "最近经济形势"
- "macro economy" / "economic briefing" / "China macro"

## 核心能力

### 1. 数据获取
- 通过 akshare 自动抓取：PMI（官方+财新）、CPI/PPI、社会融资规模、进出口贸易、工业增加值、固定资产投资、社会消费品零售总额
- 数据自动缓存（24h TTL），避免重复请求
- 异常值自动标记

### 2. 指标解读
- 每个指标自动生成：数值 → 历史分位 → 趋势方向 → 一句话解读
- 多指标联动分析（如 PMI 下行 + PPI 负增长 = 需求不足信号）
- 阈值预警（突破历史极值自动高亮）

### 3. 输出格式
- **日报模式**：当日核心指标 + 一句话总结
- **周报模式**：一周变化 + 趋势图 + 预警信号
- **月报模式**：全面解读 + 图表 + 政策建议
- 输出 Markdown 或 HTML 格式

## 使用方法

```
# 获取今日宏观简报
python monitor.py brief

# 生成周报（含图表）
python monitor.py weekly

# 生成月度深度报告
python monitor.py monthly --output report.html
```

## 技术栈
- 数据：akshare (中国宏观数据API)
- 可视化：plotly (交互图表)
- 报告：jinja2 HTML模板

## 依赖
- akshare >= 1.10.0
- pandas >= 2.0.0
- plotly >= 5.0.0
- jinja2 >= 3.0
