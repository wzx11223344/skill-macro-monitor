#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观经济监测 (Macro Economy Monitor)
=====================================
自动抓取中国宏观经济核心指标，生成结构化监测简报。

子命令:
    brief    日报模式 - 当日核心指标 + 一句话总结
    weekly   周报模式 - 一周变化 + 趋势图 + 预警信号
    monthly  月报模式 - 全面解读 + 图表 + HTML 报告
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# 缓存层 (24h TTL)
# ---------------------------------------------------------------------------

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def _cache_path(key: str) -> str:
    h = hashlib.md5(key.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.json")


def cache_get(key: str) -> Optional[Dict]:
    p = _cache_path(key)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data["_ts"] > 86400:  # 24h TTL
            os.remove(p)
            return None
        return data
    except Exception:
        return None


def cache_set(key: str, payload: Dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload["_ts"] = time.time()
    with open(_cache_path(key), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# 数据获取 (akshare)
# ---------------------------------------------------------------------------

def _safe_fetch(func, cache_key: str, **kwargs) -> Optional[pd.DataFrame]:
    """通用安全抓取：先读缓存 -> 调 akshare -> 写缓存。"""
    cached = cache_get(cache_key)
    if cached and "df" in cached:
        try:
            return pd.read_json(cached["df"], orient="records")
        except (ValueError, KeyError) as e:
            try:
                return pd.read_json(cached["df"], orient="table")
            except (ValueError, KeyError):
                try:
                    return pd.DataFrame(cached["df"])
                except Exception:
                    return None

    try:
        df = func(**kwargs)
    except Exception as exc:
        print(f"[WARN] 数据获取失败 ({cache_key}): {exc}", file=sys.stderr)
        return None

    if df is None or df.empty:
        return None

    try:
        cache_set(cache_key, {"df": df.to_json(orient="records", force_ascii=False, date_format="iso")})
    except Exception as exc:
        print(f"[WARN] 缓存写入失败 ({cache_key}): {exc}", file=sys.stderr)
    return df


def fetch_pmi() -> Optional[pd.DataFrame]:
    """官方制造业 PMI (macro_china_pmi)。"""
    import akshare as ak
    return _safe_fetch(ak.macro_china_pmi, "pmi")


def fetch_cpi() -> Optional[pd.DataFrame]:
    """CPI 同比 (macro_china_cpi_yearly)。"""
    import akshare as ak
    return _safe_fetch(ak.macro_china_cpi_yearly, "cpi")


def fetch_ppi() -> Optional[pd.DataFrame]:
    """PPI 同比 (macro_china_ppi_yearly)。"""
    import akshare as ak
    return _safe_fetch(ak.macro_china_ppi_yearly, "ppi")


def fetch_social_financing() -> Optional[pd.DataFrame]:
    """社会融资规模增量 (macro_china_shrzgm)。"""
    import akshare as ak
    return _safe_fetch(ak.macro_china_shrzgm, "shrzgm")


def fetch_trade_balance() -> Optional[pd.DataFrame]:
    """进出口贸易差额 (macro_china_trade_balance)。"""
    import akshare as ak
    return _safe_fetch(ak.macro_china_trade_balance, "trade")


# ---------------------------------------------------------------------------
# 指标解析
# ---------------------------------------------------------------------------

def _latest_value(df: pd.DataFrame, date_col: str, val_col: str) -> Tuple[Optional[str], Optional[float]]:
    """提取最新一条记录的日期和数值。"""
    if df is None or df.empty:
        return None, None
    df2 = df.sort_values(date_col, ascending=False).reset_index(drop=True)
    row = df2.iloc[0]
    return str(row[date_col]), float(row[val_col])


def _trend(df: pd.DataFrame, date_col: str, val_col: str, periods: int = 3) -> str:
    """最近 periods 期的趋势判断。"""
    if df is None or df.shape[0] < periods:
        return "数据不足"
    recent = df.sort_values(date_col, ascending=False).head(periods)[val_col].values
    if all(recent[i] >= recent[i + 1] for i in range(len(recent) - 1)):
        return "↑ 上行"
    if all(recent[i] <= recent[i + 1] for i in range(len(recent) - 1)):
        return "↓ 下行"
    return "→ 震荡"


def _percentile(df: pd.DataFrame, val_col: str, value: float) -> float:
    """计算当前值在历史数据中的分位数。"""
    if df is None or df.empty:
        return 0.0
    series = df[val_col].dropna()
    if series.empty:
        return 0.0
    return round((series < value).sum() / len(series) * 100, 1)


def _indicator_analysis(df: pd.DataFrame, date_col: str, val_col: str, name: str) -> Dict[str, Any]:
    """对单个指标做综合分析。"""
    date, value = _latest_value(df, date_col, val_col)
    if value is None:
        return {"name": name, "status": "无数据"}
    direction = _trend(df, date_col, val_col)
    pct = _percentile(df, val_col, value)
    alert = ""
    if pct >= 90:
        alert = " [高位预警]"
    elif pct <= 10:
        alert = " [低位预警]"
    return {
        "name": name,
        "date": date,
        "value": value,
        "direction": direction,
        "percentile": pct,
        "alert": alert,
    }


def _cross_signal(analyses: List[Dict]) -> List[str]:
    """多指标联动分析，生成交叉信号。"""
    signals = []
    items = {a.get("name", ""): a for a in analyses}

    pmi = items.get("官方制造业PMI", {})
    ppi = items.get("PPI同比", {})
    if pmi.get("direction") == "↓ 下行" and ppi.get("direction") == "↓ 下行":
        signals.append("PMI下行 + PPI负增长/下行 => 需求不足信号，关注政策宽松预期")

    cpi = items.get("CPI同比", {})
    if cpi.get("value", 0) is not None and cpi.get("value", 0) < 0:
        signals.append("CPI同比为负 => 通缩压力，内需有待提振")

    trade = items.get("进出口贸易差额", {})
    if trade.get("value", 0) is not None and trade.get("direction") == "↓ 下行":
        signals.append("贸易顺差收窄 => 外需走弱，关注出口拉动减弱风险")

    sf = items.get("社会融资规模", {})
    if sf.get("direction") == "↓ 下行":
        signals.append("社融增速放缓 => 实体经济融资需求不足")
    elif sf.get("direction") == "↑ 上行":
        signals.append("社融增速上行 => 宽信用效果显现，实体经济活跃度提升")

    return signals


# ---------------------------------------------------------------------------
# 输出生成
# ---------------------------------------------------------------------------

def _print_markdown_header(title: str, date_str: str = "") -> None:
    print(f"# {title}")
    if date_str:
        print(f"**生成时间**: {date_str}")
    print()


def _print_indicator_table(analyses: List[Dict]) -> None:
    """打印指标表格（Markdown）。"""
    print("| 指标 | 最新日期 | 最新值 | 趋势 | 历史分位 | 预警 |")
    print("|------|----------|--------|------|----------|------|")
    for a in analyses:
        if a.get("status") == "无数据":
            print(f"| {a['name']} | - | - | - | - | - |")
        else:
            print(f"| {a['name']} | {a['date']} | {a['value']:.2f} | {a['direction']} | {a['percentile']}% | {a['alert']} |")
    print()


def _print_signals(signals: List[str]) -> None:
    if not signals:
        return
    print("## 交叉信号与预警")
    print()
    for s in signals:
        print(f"- {s}")
    print()


def _generate_html_report(analyses: List[Dict], signals: List[str], output_path: str) -> None:
    """生成 plotly 图表的 HTML 月报。"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("[ERROR] plotly 未安装，请运行: pip install plotly", file=sys.stderr)
        sys.exit(1)

    # 准备数据和图表
    items = {a["name"]: a for a in analyses}
    figs = []

    def _add_line_chart(name: str, df_func, date_col: str, val_col: str, title: str):
        df = df_func()
        if df is None or df.empty:
            return
        df2 = df.sort_values(date_col).tail(24)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df2[date_col], y=df2[val_col],
            mode="lines+markers", name=title,
            line=dict(width=2),
        ))
        fig.update_layout(
            title=title, template="plotly_white",
            height=300, margin=dict(l=40, r=20, t=40, b=40),
        )
        figs.append((title, fig))

    _add_line_chart("PMI", fetch_pmi, "日期", "制造业", "官方制造业PMI")
    _add_line_chart("CPI", fetch_cpi, "日期", "全国", "CPI 同比 (%)")
    _add_line_chart("PPI", fetch_ppi, "日期", "全国", "PPI 同比 (%)")
    _add_line_chart("社融", fetch_social_financing, "月份", "社会融资规模增量", "社会融资规模增量 (亿元)")
    _add_line_chart("贸易", fetch_trade_balance, "日期", "贸易差额", "进出口贸易差额 (千美元)")

    # 构建 HTML
    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>宏观经济月度深度报告</title>",
        "<style>",
        "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; max-width: 1100px; margin: 0 auto; padding: 40px 20px; background: #f5f7fa; color: #333; }",
        "  h1 { color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }",
        "  h2 { color: #16213e; margin-top: 30px; }",
        "  table { width: 100%; border-collapse: collapse; margin: 20px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }",
        "  th { background: #16213e; color: white; padding: 12px 16px; text-align: left; }",
        "  td { padding: 10px 16px; border-bottom: 1px solid #eee; }",
        "  tr:hover { background: #f0f4ff; }",
        "  .alert-high { color: #e94560; font-weight: bold; }",
        "  .alert-low { color: #0f3460; font-weight: bold; }",
        "  .signal-box { background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px 16px; margin: 8px 0; border-radius: 0 8px 8px 0; }",
        "  .chart-container { background: white; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }",
        "  .timestamp { color: #999; font-size: 0.9em; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>宏观经济月度深度报告</h1>",
        f'<p class="timestamp">生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>',
        "<h2>核心指标一览</h2>",
        "<table>",
        "<tr><th>指标</th><th>最新日期</th><th>最新值</th><th>趋势</th><th>历史分位</th><th>预警</th></tr>",
    ]

    for a in analyses:
        if a.get("status") == "无数据":
            html_parts.append(f"<tr><td>{a['name']}</td><td colspan='5'>暂无数据</td></tr>")
        else:
            alert_cls = ""
            if "高位" in a.get("alert", ""):
                alert_cls = ' class="alert-high"'
            elif "低位" in a.get("alert", ""):
                alert_cls = ' class="alert-low"'
            html_parts.append(
                f"<tr><td>{a['name']}</td><td>{a['date']}</td>"
                f"<td>{a['value']:.2f}</td><td>{a['direction']}</td>"
                f"<td>{a['percentile']}%</td>"
                f"<td{alert_cls}>{a['alert']}</td></tr>"
            )

    html_parts.append("</table>")

    if signals:
        html_parts.append("<h2>交叉信号与预警</h2>")
        for s in signals:
            html_parts.append(f'<div class="signal-box">{s}</div>')

    html_parts.append("<h2>趋势图表</h2>")
    for i, (title, fig) in enumerate(figs):
        chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False)
        html_parts.append(f'<div class="chart-container">{chart_html}</div>')

    html_parts.append("<hr>")
    html_parts.append('<p style="text-align:center;color:#999;">Powered by macro-econ-monitor | 数据来源: akshare</p>')
    html_parts.append("</body></html>")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))
    print(f"[OK] 月报已生成: {output_path}")


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

FETCHERS = [
    ("官方制造业PMI", fetch_pmi, "日期", "制造业"),
    ("CPI同比", fetch_cpi, "日期", "全国"),
    ("PPI同比", fetch_ppi, "日期", "全国"),
    ("社会融资规模", fetch_social_financing, "月份", "社会融资规模增量"),
    ("进出口贸易差额", fetch_trade_balance, "日期", "贸易差额"),
]


def _collect_analyses() -> List[Dict]:
    """拉取全部指标并返回分析结果列表。"""
    results = []
    for name, func, dc, vc in FETCHERS:
        df = func()
        a = _indicator_analysis(df, dc, vc, name)
        results.append(a)
    return results


def cmd_brief() -> None:
    """日报模式：核心指标 + 一句话总结。"""
    today = datetime.now().strftime("%Y-%m-%d")
    _print_markdown_header("宏观日报", today)
    analyses = _collect_analyses()
    _print_indicator_table(analyses)

    signals = _cross_signal(analyses)
    _print_signals(signals)

    # 一句话总结
    pmi_item = next((a for a in analyses if "PMI" in a["name"]), None)
    if pmi_item and pmi_item.get("value") is not None:
        if pmi_item["value"] >= 50:
            print(f"> 制造业PMI为 {pmi_item['value']:.1f}，位于荣枯线以上，经济扩张态势。")
        else:
            print(f"> 制造业PMI为 {pmi_item['value']:.1f}，跌破荣枯线，经济收缩压力显现。")
    print()


def cmd_weekly() -> None:
    """周报模式：指标一览 + 趋势分析 + 预警。"""
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    _print_markdown_header("宏观周报", f"{week_ago} ~ {today}")
    analyses = _collect_analyses()
    _print_indicator_table(analyses)

    print("## 趋势分析")
    print()
    for a in analyses:
        if a.get("status") == "无数据":
            continue
        print(f"- **{a['name']}**: 最新值 {a['value']:.2f}，趋势 {a['direction']}，历史分位 {a['percentile']}%{a.get('alert','')}")

    print()
    signals = _cross_signal(analyses)
    _print_signals(signals)

    if not signals:
        print("> 本周未触发明显交叉预警信号，主要指标运行平稳。")
    print()


def cmd_monthly(args: argparse.Namespace) -> None:
    """月报模式：全面解读 + HTML 报告。"""
    analyses = _collect_analyses()
    signals = _cross_signal(analyses)

    output = getattr(args, "output", "macro_monthly_report.html")
    _generate_html_report(analyses, signals, output)

    # 同时打印摘要
    print()
    today = datetime.now().strftime("%Y-%m-%d")
    _print_markdown_header("宏观月报摘要", today)
    _print_indicator_table(analyses)
    _print_signals(signals)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="宏观经济监测 (Macro Economy Monitor) - 自动抓取中国宏观数据并生成简报",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    sub.add_parser("brief", help="日报模式 - 当日核心指标 + 一句话总结")
    sub.add_parser("weekly", help="周报模式 - 一周变化 + 趋势分析 + 预警")

    monthly_parser = sub.add_parser("monthly", help="月报模式 - 全面解读 + HTML 图表报告")
    monthly_parser.add_argument("--output", "-o", default="macro_monthly_report.html", help="HTML 输出路径 (默认: macro_monthly_report.html)")

    args = parser.parse_args()

    if args.command == "brief":
        cmd_brief()
    elif args.command == "weekly":
        cmd_weekly()
    elif args.command == "monthly":
        cmd_monthly(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
