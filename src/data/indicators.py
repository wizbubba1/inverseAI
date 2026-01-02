"""Technical indicator calculations."""

from typing import Any

import numpy as np
import pandas as pd

from src.data.price_feeds import PriceData


class TechnicalIndicators:
    """Calculator for all technical indicators used by TA agents."""

    def __init__(self, price_data: PriceData):
        self.df = price_data.df.copy()
        self._calculate_all()

    def _calculate_all(self) -> None:
        """Calculate all indicators."""
        self._calculate_rsi()
        self._calculate_ema()
        self._calculate_sma()
        self._calculate_macd()
        self._calculate_bollinger_bands()
        self._calculate_atr()
        self._calculate_volume_profile()
        self._calculate_ichimoku()
        self._calculate_swing_points()

    # RSI
    def _calculate_rsi(self, period: int = 14) -> None:
        """Calculate RSI."""
        delta = self.df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        self.df[f"rsi_{period}"] = 100 - (100 / (1 + rs))

    # Moving Averages
    def _calculate_ema(self) -> None:
        """Calculate EMAs."""
        for period in [9, 21, 50, 200]:
            self.df[f"ema_{period}"] = self.df["close"].ewm(span=period, adjust=False).mean()

    def _calculate_sma(self) -> None:
        """Calculate SMAs."""
        for period in [20, 50, 200]:
            self.df[f"sma_{period}"] = self.df["close"].rolling(window=period).mean()

    # MACD
    def _calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        """Calculate MACD."""
        ema_fast = self.df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = self.df["close"].ewm(span=slow, adjust=False).mean()

        self.df["macd_line"] = ema_fast - ema_slow
        self.df["macd_signal"] = self.df["macd_line"].ewm(span=signal, adjust=False).mean()
        self.df["macd_histogram"] = self.df["macd_line"] - self.df["macd_signal"]

    # Bollinger Bands
    def _calculate_bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> None:
        """Calculate Bollinger Bands."""
        sma = self.df["close"].rolling(window=period).mean()
        std = self.df["close"].rolling(window=period).std()

        self.df["bb_upper"] = sma + (std * std_dev)
        self.df["bb_middle"] = sma
        self.df["bb_lower"] = sma - (std * std_dev)
        self.df["bb_width"] = (self.df["bb_upper"] - self.df["bb_lower"]) / self.df["bb_middle"]
        self.df["bb_percent"] = (self.df["close"] - self.df["bb_lower"]) / (self.df["bb_upper"] - self.df["bb_lower"])

    # ATR
    def _calculate_atr(self, period: int = 14) -> None:
        """Calculate Average True Range."""
        high = self.df["high"]
        low = self.df["low"]
        close = self.df["close"].shift(1)

        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        self.df["atr"] = tr.rolling(window=period).mean()

    # Volume Profile (simplified)
    def _calculate_volume_profile(self) -> None:
        """Calculate volume-weighted average price and volume metrics."""
        self.df["vwap"] = (
            (self.df["volume"] * (self.df["high"] + self.df["low"] + self.df["close"]) / 3).cumsum()
            / self.df["volume"].cumsum()
        )

        # Volume SMA
        self.df["volume_sma_20"] = self.df["volume"].rolling(window=20).mean()
        self.df["volume_ratio"] = self.df["volume"] / self.df["volume_sma_20"]

    # Ichimoku Cloud
    def _calculate_ichimoku(self) -> None:
        """Calculate Ichimoku Cloud indicators."""
        # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
        period9_high = self.df["high"].rolling(window=9).max()
        period9_low = self.df["low"].rolling(window=9).min()
        self.df["tenkan_sen"] = (period9_high + period9_low) / 2

        # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
        period26_high = self.df["high"].rolling(window=26).max()
        period26_low = self.df["low"].rolling(window=26).min()
        self.df["kijun_sen"] = (period26_high + period26_low) / 2

        # Senkou Span A (Leading Span A): (Conversion Line + Base Line) / 2, shifted 26 periods ahead
        self.df["senkou_span_a"] = ((self.df["tenkan_sen"] + self.df["kijun_sen"]) / 2).shift(26)

        # Senkou Span B (Leading Span B): (52-period high + 52-period low) / 2, shifted 26 periods ahead
        period52_high = self.df["high"].rolling(window=52).max()
        period52_low = self.df["low"].rolling(window=52).min()
        self.df["senkou_span_b"] = ((period52_high + period52_low) / 2).shift(26)

        # Chikou Span (Lagging Span): Close shifted 26 periods back
        self.df["chikou_span"] = self.df["close"].shift(-26)

        # Cloud direction
        self.df["cloud_top"] = self.df[["senkou_span_a", "senkou_span_b"]].max(axis=1)
        self.df["cloud_bottom"] = self.df[["senkou_span_a", "senkou_span_b"]].min(axis=1)
        self.df["cloud_thickness"] = self.df["cloud_top"] - self.df["cloud_bottom"]

    # Swing Points for Fibonacci and Trend Lines
    def _calculate_swing_points(self, lookback: int = 5) -> None:
        """Identify swing highs and lows."""
        highs = self.df["high"].values
        lows = self.df["low"].values

        swing_highs = []
        swing_lows = []

        for i in range(lookback, len(highs) - lookback):
            # Check for swing high
            if highs[i] == max(highs[i - lookback : i + lookback + 1]):
                swing_highs.append((i, highs[i]))

            # Check for swing low
            if lows[i] == min(lows[i - lookback : i + lookback + 1]):
                swing_lows.append((i, lows[i]))

        self._swing_highs = swing_highs
        self._swing_lows = swing_lows

    # Getters for current values
    def get_current(self) -> dict[str, Any]:
        """Get current (latest) indicator values."""
        latest = self.df.iloc[-1]
        prev = self.df.iloc[-2] if len(self.df) > 1 else latest

        return {
            # Price
            "current_price": float(latest["close"]),
            "prev_close": float(prev["close"]),

            # RSI
            "rsi_14": float(latest["rsi_14"]) if pd.notna(latest["rsi_14"]) else None,

            # Moving Averages
            "ema_9": float(latest["ema_9"]) if pd.notna(latest["ema_9"]) else None,
            "ema_21": float(latest["ema_21"]) if pd.notna(latest["ema_21"]) else None,
            "ema_50": float(latest["ema_50"]) if pd.notna(latest["ema_50"]) else None,
            "ema_200": float(latest["ema_200"]) if pd.notna(latest["ema_200"]) else None,
            "sma_20": float(latest["sma_20"]) if pd.notna(latest["sma_20"]) else None,
            "sma_50": float(latest["sma_50"]) if pd.notna(latest["sma_50"]) else None,

            # Previous EMAs for crossover detection
            "prev_ema_9": float(prev["ema_9"]) if pd.notna(prev["ema_9"]) else None,
            "prev_ema_21": float(prev["ema_21"]) if pd.notna(prev["ema_21"]) else None,

            # MACD
            "macd_line": float(latest["macd_line"]) if pd.notna(latest["macd_line"]) else None,
            "macd_signal": float(latest["macd_signal"]) if pd.notna(latest["macd_signal"]) else None,
            "macd_histogram": float(latest["macd_histogram"]) if pd.notna(latest["macd_histogram"]) else None,
            "prev_macd_line": float(prev["macd_line"]) if pd.notna(prev["macd_line"]) else None,
            "prev_macd_signal": float(prev["macd_signal"]) if pd.notna(prev["macd_signal"]) else None,

            # Bollinger Bands
            "bb_upper": float(latest["bb_upper"]) if pd.notna(latest["bb_upper"]) else None,
            "bb_middle": float(latest["bb_middle"]) if pd.notna(latest["bb_middle"]) else None,
            "bb_lower": float(latest["bb_lower"]) if pd.notna(latest["bb_lower"]) else None,
            "bb_width": float(latest["bb_width"]) if pd.notna(latest["bb_width"]) else None,
            "bb_percent": float(latest["bb_percent"]) if pd.notna(latest["bb_percent"]) else None,

            # ATR
            "atr": float(latest["atr"]) if pd.notna(latest["atr"]) else None,

            # Volume
            "volume": float(latest["volume"]),
            "volume_sma_20": float(latest["volume_sma_20"]) if pd.notna(latest["volume_sma_20"]) else None,
            "volume_ratio": float(latest["volume_ratio"]) if pd.notna(latest["volume_ratio"]) else None,
            "vwap": float(latest["vwap"]) if pd.notna(latest["vwap"]) else None,

            # Ichimoku
            "tenkan_sen": float(latest["tenkan_sen"]) if pd.notna(latest["tenkan_sen"]) else None,
            "kijun_sen": float(latest["kijun_sen"]) if pd.notna(latest["kijun_sen"]) else None,
            "senkou_span_a": float(latest["senkou_span_a"]) if pd.notna(latest["senkou_span_a"]) else None,
            "senkou_span_b": float(latest["senkou_span_b"]) if pd.notna(latest["senkou_span_b"]) else None,
            "cloud_top": float(latest["cloud_top"]) if pd.notna(latest["cloud_top"]) else None,
            "cloud_bottom": float(latest["cloud_bottom"]) if pd.notna(latest["cloud_bottom"]) else None,
            "cloud_thickness": float(latest["cloud_thickness"]) if pd.notna(latest["cloud_thickness"]) else None,
        }

    def get_support_resistance_levels(self, num_levels: int = 5) -> dict[str, list[float]]:
        """Identify support and resistance levels from price action."""
        # Use recent swing highs and lows
        recent_highs = [h[1] for h in self._swing_highs[-num_levels:]]
        recent_lows = [l[1] for l in self._swing_lows[-num_levels:]]

        # Also consider VWAP and moving averages as dynamic S/R
        current = self.get_current()
        dynamic_levels = []
        for key in ["vwap", "ema_50", "ema_200", "sma_50"]:
            if current.get(key):
                dynamic_levels.append(current[key])

        return {
            "resistance": sorted(recent_highs, reverse=True),
            "support": sorted(recent_lows),
            "dynamic": dynamic_levels,
        }

    def get_fibonacci_levels(self) -> dict[str, float]:
        """Calculate Fibonacci retracement levels from recent swing high/low."""
        if not self._swing_highs or not self._swing_lows:
            return {}

        # Find the most recent significant high and low
        recent_high = max(self._swing_highs[-5:], key=lambda x: x[1])[1]
        recent_low = min(self._swing_lows[-5:], key=lambda x: x[1])[1]

        diff = recent_high - recent_low
        current_price = float(self.df["close"].iloc[-1])

        # Determine trend direction
        if current_price > (recent_high + recent_low) / 2:
            # Uptrend - retracement from high
            return {
                "swing_high": recent_high,
                "swing_low": recent_low,
                "fib_0": recent_high,
                "fib_236": recent_high - (diff * 0.236),
                "fib_382": recent_high - (diff * 0.382),
                "fib_500": recent_high - (diff * 0.500),
                "fib_618": recent_high - (diff * 0.618),
                "fib_786": recent_high - (diff * 0.786),
                "fib_100": recent_low,
                "fib_1272": recent_high + (diff * 0.272),  # Extension
                "fib_1618": recent_high + (diff * 0.618),  # Extension
            }
        else:
            # Downtrend - retracement from low
            return {
                "swing_high": recent_high,
                "swing_low": recent_low,
                "fib_0": recent_low,
                "fib_236": recent_low + (diff * 0.236),
                "fib_382": recent_low + (diff * 0.382),
                "fib_500": recent_low + (diff * 0.500),
                "fib_618": recent_low + (diff * 0.618),
                "fib_786": recent_low + (diff * 0.786),
                "fib_100": recent_high,
                "fib_1272": recent_low - (diff * 0.272),  # Extension
                "fib_1618": recent_low - (diff * 0.618),  # Extension
            }

    def get_trend_lines(self) -> dict[str, Any]:
        """Calculate trend line slopes from swing points."""
        result = {
            "uptrend_valid": False,
            "downtrend_valid": False,
            "uptrend_support": None,
            "downtrend_resistance": None,
        }

        if len(self._swing_lows) >= 2:
            # Calculate uptrend line from swing lows
            lows = self._swing_lows[-3:]
            if len(lows) >= 2:
                x1, y1 = lows[-2]
                x2, y2 = lows[-1]
                if y2 > y1:  # Valid uptrend (higher lows)
                    slope = (y2 - y1) / (x2 - x1) if x2 != x1 else 0
                    # Project to current bar
                    current_idx = len(self.df) - 1
                    projected = y2 + slope * (current_idx - x2)
                    result["uptrend_valid"] = True
                    result["uptrend_support"] = projected
                    result["uptrend_slope"] = slope

        if len(self._swing_highs) >= 2:
            # Calculate downtrend line from swing highs
            highs = self._swing_highs[-3:]
            if len(highs) >= 2:
                x1, y1 = highs[-2]
                x2, y2 = highs[-1]
                if y2 < y1:  # Valid downtrend (lower highs)
                    slope = (y2 - y1) / (x2 - x1) if x2 != x1 else 0
                    # Project to current bar
                    current_idx = len(self.df) - 1
                    projected = y2 + slope * (current_idx - x2)
                    result["downtrend_valid"] = True
                    result["downtrend_resistance"] = projected
                    result["downtrend_slope"] = slope

        return result

    def get_chart_patterns(self) -> dict[str, Any]:
        """Detect common chart patterns."""
        patterns = {
            "double_top": False,
            "double_bottom": False,
            "head_and_shoulders": False,
            "inverse_head_and_shoulders": False,
            "ascending_triangle": False,
            "descending_triangle": False,
            "bullish_flag": False,
            "bearish_flag": False,
        }

        # Double top detection (two similar highs)
        if len(self._swing_highs) >= 2:
            h1 = self._swing_highs[-2][1]
            h2 = self._swing_highs[-1][1]
            tolerance = h1 * 0.02  # 2% tolerance
            if abs(h1 - h2) < tolerance:
                patterns["double_top"] = True
                patterns["double_top_level"] = (h1 + h2) / 2

        # Double bottom detection (two similar lows)
        if len(self._swing_lows) >= 2:
            l1 = self._swing_lows[-2][1]
            l2 = self._swing_lows[-1][1]
            tolerance = l1 * 0.02
            if abs(l1 - l2) < tolerance:
                patterns["double_bottom"] = True
                patterns["double_bottom_level"] = (l1 + l2) / 2

        # Head and shoulders (middle high is highest)
        if len(self._swing_highs) >= 3:
            h1 = self._swing_highs[-3][1]
            h2 = self._swing_highs[-2][1]  # Head
            h3 = self._swing_highs[-1][1]
            if h2 > h1 and h2 > h3 and abs(h1 - h3) < h1 * 0.03:
                patterns["head_and_shoulders"] = True
                patterns["neckline"] = min(self._swing_lows[-2][1], self._swing_lows[-1][1])

        # Inverse head and shoulders
        if len(self._swing_lows) >= 3:
            l1 = self._swing_lows[-3][1]
            l2 = self._swing_lows[-2][1]  # Head
            l3 = self._swing_lows[-1][1]
            if l2 < l1 and l2 < l3 and abs(l1 - l3) < l1 * 0.03:
                patterns["inverse_head_and_shoulders"] = True
                patterns["neckline"] = max(self._swing_highs[-2][1], self._swing_highs[-1][1])

        return patterns

    def get_volume_profile_zones(self) -> dict[str, Any]:
        """Identify high-volume price zones."""
        # Group price into bins and sum volume
        price_range = self.df["high"].max() - self.df["low"].min()
        bin_size = price_range / 20  # 20 price levels

        volume_profile = {}
        for _, row in self.df.iterrows():
            mid_price = (row["high"] + row["low"]) / 2
            bin_key = int(mid_price / bin_size) * bin_size
            volume_profile[bin_key] = volume_profile.get(bin_key, 0) + row["volume"]

        # Sort by volume
        sorted_zones = sorted(volume_profile.items(), key=lambda x: x[1], reverse=True)

        # Get high volume zones (top 5)
        high_volume_zones = [z[0] for z in sorted_zones[:5]]

        current_price = float(self.df["close"].iloc[-1])

        return {
            "high_volume_zones": high_volume_zones,
            "nearest_hv_support": max([z for z in high_volume_zones if z < current_price], default=None),
            "nearest_hv_resistance": min([z for z in high_volume_zones if z > current_price], default=None),
            "poc": sorted_zones[0][0] if sorted_zones else None,  # Point of Control
        }

    def to_context_string(self) -> str:
        """Convert indicators to a string suitable for LLM context."""
        current = self.get_current()
        sr_levels = self.get_support_resistance_levels()
        fib_levels = self.get_fibonacci_levels()
        trend_lines = self.get_trend_lines()

        lines = [
            "## Current Indicator Values",
            f"Current Price: {current['current_price']:.2f}",
            "",
            "### RSI (14-period)",
            f"RSI: {current['rsi_14']:.2f}" if current['rsi_14'] else "RSI: N/A",
            "",
            "### Moving Averages",
            f"EMA 9: {current['ema_9']:.2f}" if current['ema_9'] else "EMA 9: N/A",
            f"EMA 21: {current['ema_21']:.2f}" if current['ema_21'] else "EMA 21: N/A",
            f"EMA 50: {current['ema_50']:.2f}" if current['ema_50'] else "EMA 50: N/A",
            f"SMA 20: {current['sma_20']:.2f}" if current['sma_20'] else "SMA 20: N/A",
            "",
            "### MACD (12, 26, 9)",
            f"MACD Line: {current['macd_line']:.4f}" if current['macd_line'] else "MACD Line: N/A",
            f"Signal Line: {current['macd_signal']:.4f}" if current['macd_signal'] else "Signal Line: N/A",
            f"Histogram: {current['macd_histogram']:.4f}" if current['macd_histogram'] else "Histogram: N/A",
            "",
            "### Bollinger Bands (20, 2)",
            f"Upper Band: {current['bb_upper']:.2f}" if current['bb_upper'] else "Upper Band: N/A",
            f"Middle Band: {current['bb_middle']:.2f}" if current['bb_middle'] else "Middle Band: N/A",
            f"Lower Band: {current['bb_lower']:.2f}" if current['bb_lower'] else "Lower Band: N/A",
            f"Band Width: {current['bb_width']:.4f}" if current['bb_width'] else "Band Width: N/A",
            f"%B: {current['bb_percent']:.2f}" if current['bb_percent'] else "%B: N/A",
            "",
            "### Volume",
            f"Current Volume: {current['volume']:.2f}",
            f"Volume SMA 20: {current['volume_sma_20']:.2f}" if current['volume_sma_20'] else "Volume SMA 20: N/A",
            f"Volume Ratio: {current['volume_ratio']:.2f}x" if current['volume_ratio'] else "Volume Ratio: N/A",
            f"VWAP: {current['vwap']:.2f}" if current['vwap'] else "VWAP: N/A",
            "",
            "### Ichimoku Cloud",
            f"Tenkan-sen: {current['tenkan_sen']:.2f}" if current['tenkan_sen'] else "Tenkan-sen: N/A",
            f"Kijun-sen: {current['kijun_sen']:.2f}" if current['kijun_sen'] else "Kijun-sen: N/A",
            f"Cloud Top: {current['cloud_top']:.2f}" if current['cloud_top'] else "Cloud Top: N/A",
            f"Cloud Bottom: {current['cloud_bottom']:.2f}" if current['cloud_bottom'] else "Cloud Bottom: N/A",
            "",
            "### Support & Resistance Levels",
            f"Resistance: {sr_levels['resistance'][:3]}",
            f"Support: {sr_levels['support'][:3]}",
            "",
            "### Fibonacci Levels",
        ]

        if fib_levels:
            lines.extend([
                f"0.618 Retracement: {fib_levels.get('fib_618', 'N/A'):.2f}" if fib_levels.get('fib_618') else "",
                f"0.786 Retracement: {fib_levels.get('fib_786', 'N/A'):.2f}" if fib_levels.get('fib_786') else "",
            ])

        lines.extend([
            "",
            "### Trend Lines",
            f"Uptrend Support: {trend_lines['uptrend_support']:.2f}" if trend_lines['uptrend_support'] else "Uptrend Support: Not established",
            f"Downtrend Resistance: {trend_lines['downtrend_resistance']:.2f}" if trend_lines['downtrend_resistance'] else "Downtrend Resistance: Not established",
            "",
            f"### ATR (14-period): {current['atr']:.2f}" if current['atr'] else "ATR: N/A",
        ])

        return "\n".join(lines)
