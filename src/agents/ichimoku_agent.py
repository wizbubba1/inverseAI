"""Ichimoku Cloud Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class IchimokuAgent(BaseAgent):
    """Agent that trades based on the Ichimoku Cloud system."""

    @property
    def agent_id(self) -> str:
        return "ichimoku_agent"

    @property
    def methodology_name(self) -> str:
        return "Ichimoku Cloud (Ichimoku Kinko Hyo)"

    @property
    def methodology_description(self) -> str:
        return """Ichimoku Cloud is a comprehensive indicator system showing support, resistance, and momentum.

Key Components:
- Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
- Kijun-sen (Base Line): (26-period high + 26-period low) / 2
- Senkou Span A: (Tenkan + Kijun) / 2, plotted 26 periods ahead
- Senkou Span B: (52-period high + 52-period low) / 2, plotted 26 periods ahead
- Chikou Span: Current close plotted 26 periods back
- The Cloud (Kumo): Area between Senkou Span A and B

Trading Rules:
1. BUY (LONG) when:
   - Price is ABOVE the cloud
   - Tenkan-sen crosses above Kijun-sen (bullish TK cross)
   - Chikou Span is above price from 26 periods ago

2. SELL (SHORT) when:
   - Price is BELOW the cloud
   - Tenkan-sen crosses below Kijun-sen (bearish TK cross)
   - Chikou Span is below price from 26 periods ago

Cloud Analysis:
- Green cloud (Span A > Span B): Bullish
- Red cloud (Span B > Span A): Bearish
- Thick cloud: Strong support/resistance
- Thin cloud: Weak support/resistance

Confidence Levels:
- All 5 signals aligned: Very high confidence
- 4 signals aligned: High confidence
- 3 signals aligned: Moderate confidence
- Mixed signals: Low confidence (wait for clarity)"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get Ichimoku-specific indicator values."""
        current = indicators.get_current()

        current_price = current.get("current_price")
        tenkan = current.get("tenkan_sen")
        kijun = current.get("kijun_sen")
        span_a = current.get("senkou_span_a")
        span_b = current.get("senkou_span_b")
        cloud_top = current.get("cloud_top")
        cloud_bottom = current.get("cloud_bottom")
        cloud_thickness = current.get("cloud_thickness")

        lines = [
            f"Current Price: {current_price:.2f}",
            "",
            "### Ichimoku Components",
            f"Tenkan-sen (Conversion): {tenkan:.2f}" if tenkan else "Tenkan-sen: N/A",
            f"Kijun-sen (Base): {kijun:.2f}" if kijun else "Kijun-sen: N/A",
            "",
            "### Cloud (Kumo)",
            f"Senkou Span A: {span_a:.2f}" if span_a else "Span A: N/A",
            f"Senkou Span B: {span_b:.2f}" if span_b else "Span B: N/A",
            f"Cloud Top: {cloud_top:.2f}" if cloud_top else "Cloud Top: N/A",
            f"Cloud Bottom: {cloud_bottom:.2f}" if cloud_bottom else "Cloud Bottom: N/A",
            f"Cloud Thickness: {cloud_thickness:.2f}" if cloud_thickness else "Thickness: N/A",
            "",
        ]

        # Signal analysis
        lines.append("### Signal Analysis")
        signals_bullish = 0
        signals_bearish = 0

        # 1. Price vs Cloud
        if cloud_top and cloud_bottom:
            if current_price > cloud_top:
                lines.append("1. Price vs Cloud: BULLISH (above cloud)")
                signals_bullish += 1
            elif current_price < cloud_bottom:
                lines.append("1. Price vs Cloud: BEARISH (below cloud)")
                signals_bearish += 1
            else:
                lines.append("1. Price vs Cloud: NEUTRAL (inside cloud)")

        # 2. TK Cross
        if tenkan and kijun:
            if tenkan > kijun:
                lines.append("2. TK Cross: BULLISH (Tenkan above Kijun)")
                signals_bullish += 1
            elif tenkan < kijun:
                lines.append("2. TK Cross: BEARISH (Tenkan below Kijun)")
                signals_bearish += 1
            else:
                lines.append("2. TK Cross: NEUTRAL (Tenkan equals Kijun)")

        # 3. Cloud color (future trend)
        if span_a and span_b:
            if span_a > span_b:
                lines.append("3. Cloud Color: GREEN/BULLISH")
                signals_bullish += 1
            else:
                lines.append("3. Cloud Color: RED/BEARISH")
                signals_bearish += 1

        # 4. Price vs Kijun
        if kijun:
            if current_price > kijun:
                lines.append("4. Price vs Kijun: BULLISH (above base line)")
                signals_bullish += 1
            else:
                lines.append("4. Price vs Kijun: BEARISH (below base line)")
                signals_bearish += 1

        # Summary
        lines.extend([
            "",
            "### Signal Summary",
            f"Bullish Signals: {signals_bullish}",
            f"Bearish Signals: {signals_bearish}",
        ])

        total_signals = signals_bullish + signals_bearish
        if total_signals > 0:
            if signals_bullish > signals_bearish + 1:
                lines.append("OVERALL: STRONG BULLISH")
            elif signals_bullish > signals_bearish:
                lines.append("OVERALL: MODERATE BULLISH")
            elif signals_bearish > signals_bullish + 1:
                lines.append("OVERALL: STRONG BEARISH")
            elif signals_bearish > signals_bullish:
                lines.append("OVERALL: MODERATE BEARISH")
            else:
                lines.append("OVERALL: MIXED/NEUTRAL")

        # Cloud strength
        if cloud_thickness and current_price:
            thickness_pct = (cloud_thickness / current_price) * 100
            if thickness_pct > 3:
                lines.append(f"Cloud Strength: THICK ({thickness_pct:.1f}%) - Strong S/R")
            elif thickness_pct < 1:
                lines.append(f"Cloud Strength: THIN ({thickness_pct:.1f}%) - Weak S/R")
            else:
                lines.append(f"Cloud Strength: MODERATE ({thickness_pct:.1f}%)")

        return "\n".join(lines)
