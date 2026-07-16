#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for skill-macro-monitor."""

import sys
import os
import json
import time
import numpy as np
import pandas as pd
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor import (
    _trend,
    _indicator_analysis,
    _cross_signal,
    cache_get,
    cache_set,
    CACHE_DIR,
)
import monitor as mm


class TestTrend:
    """Tests for _trend function."""

    def test_trend_up(self):
        """Test upward trend detection."""
        df = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="MS"),
            "val": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        })
        result = _trend(df, "date", "val", periods=3)
        assert result == "↑ 上行"

    def test_trend_down(self):
        """Test downward trend detection."""
        df = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="MS"),
            "val": [19, 18, 17, 16, 15, 14, 13, 12, 11, 10],
        })
        result = _trend(df, "date", "val", periods=3)
        assert result == "↓ 下行"

    def test_trend_mixed(self):
        """Test震荡 (mixed) trend detection."""
        df = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=10, freq="MS"),
            "val": [10, 12, 11, 13, 12, 14, 13, 15, 14, 16],
        })
        result = _trend(df, "date", "val", periods=3)
        assert result == "→ 震荡"

    def test_trend_insufficient_data(self):
        """Test trend with insufficient data."""
        df = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=2, freq="MS"),
            "val": [10, 11],
        })
        result = _trend(df, "date", "val", periods=3)
        assert result == "数据不足"


class TestIndicatorAnalysis:
    """Tests for _indicator_analysis function."""

    def test_indicator_analysis_normal(self):
        """Test indicator analysis with normal data."""
        df = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=24, freq="MS"),
            "val": [50.0 + i * 0.1 for i in range(24)],
        })
        result = _indicator_analysis(df, "date", "val", "测试指标")
        assert result["name"] == "测试指标"
        assert "value" in result
        assert "direction" in result
        assert "percentile" in result

    def test_indicator_analysis_no_data(self):
        """Test indicator analysis with None DataFrame."""
        result = _indicator_analysis(None, "date", "val", "测试指标")
        assert result["status"] == "无数据"

    def test_indicator_analysis_high_percentile(self):
        """Test that high values get appropriate percentile."""
        df = pd.DataFrame({
            "date": pd.date_range("2020-01-01", periods=24, freq="MS"),
            "val": [50.0 + i * 0.1 for i in range(24)],
        })
        result = _indicator_analysis(df, "date", "val", "测试指标")
        # Latest value should be at very high percentile
        assert result["percentile"] > 80.0


class TestCrossSignal:
    """Tests for _cross_signal function."""

    def test_cross_signal_demand_weak(self):
        """Test demand weakness signal when PMI and PPI both down."""
        analyses = [
            {"name": "官方制造业PMI", "direction": "↓ 下行", "value": 49.5},
            {"name": "PPI同比", "direction": "↓ 下行", "value": -2.0},
            {"name": "CPI同比", "direction": "→ 震荡", "value": 1.5},
            {"name": "进出口贸易差额", "direction": "→ 震荡", "value": 500},
            {"name": "社会融资规模", "direction": "→ 震荡", "value": 2000},
        ]
        signals = _cross_signal(analyses)
        assert any("需求不足" in s for s in signals)

    def test_cross_signal_deflation(self):
        """Test deflation signal when CPI is negative."""
        analyses = [
            {"name": "官方制造业PMI", "direction": "→ 震荡", "value": 50.5},
            {"name": "PPI同比", "direction": "→ 震荡", "value": 0.5},
            {"name": "CPI同比", "direction": "→ 震荡", "value": -0.5},
            {"name": "进出口贸易差额", "direction": "→ 震荡", "value": 500},
            {"name": "社会融资规模", "direction": "→ 震荡", "value": 2000},
        ]
        signals = _cross_signal(analyses)
        assert any("通缩" in s for s in signals)

    def test_cross_signal_no_signals(self):
        """Test that no signals are generated when everything is stable."""
        analyses = [
            {"name": "官方制造业PMI", "direction": "→ 震荡", "value": 50.5},
            {"name": "PPI同比", "direction": "→ 震荡", "value": 1.0},
            {"name": "CPI同比", "direction": "→ 震荡", "value": 2.0},
            {"name": "进出口贸易差额", "direction": "→ 震荡", "value": 500},
            {"name": "社会融资规模", "direction": "→ 震荡", "value": 2000},
        ]
        signals = _cross_signal(analyses)
        assert len(signals) == 0


class TestCache:
    """Tests for cache_get and cache_set functions."""

    def test_cache_set_and_get(self):
        """Test basic cache set and get."""
        key = "test_key_001"
        data = {"value": 42, "name": "test"}
        cache_set(key, data)
        result = cache_get(key)
        assert result is not None
        assert "value" in result
        assert result["value"] == 42
        assert result["name"] == "test"

    def test_cache_miss(self):
        """Test cache miss returns None."""
        result = cache_get("nonexistent_key_xyz_123")
        assert result is None

    def test_cache_expired(self):
        """Test that expired cache returns None."""
        key = "test_key_expired"
        data = {"value": 42}
        cache_set(key, data)
        # Manually set _ts to 2 days ago to simulate expiration
        cache_path = mm._cache_path(key)
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        cached["_ts"] = time.time() - 100000  # more than 24h ago
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached, f)
        result = cache_get(key)
        assert result is None
