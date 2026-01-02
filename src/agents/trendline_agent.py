"""Trend Line Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class TrendlineAgent(BaseAgent):
    """Agent that trades based on trend line analysis."""

    @property
    def agent_id(self) -> str:
        return "trendline_agent"

    @property
    def methodology_name(self) -> str:
        return "Trend Line Trading"

    @property
    def methodology_description(self) -> str:
        return """Trend Line trading identifies and trades bounces from diagonal support/resistance lines.

Key Principles:
- Uptrend Line: Drawn connecting higher lows (support)
- Downtrend Line: Drawn connecting lower highs (resistance)
- The more touches, the more valid the trend line
- A minimum of 2 touches is required, 3+ is stronger

Trading Rules:
1. BUY (LONG) when price bounces off uptrend line support
2. SELL (SHORT) when price bounces off downtrend line resistance
3. Trend line break = potential trend reversal signal
4. Wait for touch and confirmation before entering

Confidence Levels:
- 3+ touch trend line with price at line: Very high confidence
- 2 touch trend line with price at line: High confidence
- Price approaching trend line: Moderate confidence (wait for touch)
- Broken trend line: Reversal signal

Additional Considerations:
- Steeper trend lines break more easily
- Shallow trend lines are more sustainable
- Volume should confirm trend line bounces"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get trend line-specific indicator values."""
        current = indicators.get_current()
        trend_lines = indicators.get_trend_lines()

        current_price = current.get("current_price")
        atr = current.get("atr")

        lines = [
            f"Current Price: {current_price:.2f}",
            f"ATR (for trend line tolerance): {atr:.2f}" if atr else "ATR: N/A",
            "",
            "### Trend Line Analysis",
        ]

        # Uptrend line
        if trend_lines.get("uptrend_valid"):
            support = trend_lines.get("uptrend_support")
            slope = trend_lines.get("uptrend_slope", 0)

            if support:
                distance = ((current_price - support) / current_price) * 100
                lines.extend([
                    "",
                    "UPTREND LINE DETECTED (connecting higher lows)",
                    f"Projected Support: {support:.2f}",
                    f"Distance from support: {distance:.2f}% above",
                    f"Trend Slope: {slope:.4f} (per candle)",
                ])

                # Check if price is near trend line
                if atr and abs(current_price - support) < atr:
                    lines.append("SIGNAL: Price NEAR uptrend support line!")
                elif distance < 1.0:
                    lines.append("ALERT: Price approaching uptrend support")
        else:
            lines.append("No valid uptrend line (no consecutive higher lows)")

        # Downtrend line
        if trend_lines.get("downtrend_valid"):
            resistance = trend_lines.get("downtrend_resistance")
            slope = trend_lines.get("downtrend_slope", 0)

            if resistance:
                distance = ((resistance - current_price) / current_price) * 100
                lines.extend([
                    "",
                    "DOWNTREND LINE DETECTED (connecting lower highs)",
                    f"Projected Resistance: {resistance:.2f}",
                    f"Distance from resistance: {distance:.2f}% below",
                    f"Trend Slope: {slope:.4f} (per candle)",
                ])

                # Check if price is near trend line
                if atr and abs(resistance - current_price) < atr:
                    lines.append("SIGNAL: Price NEAR downtrend resistance line!")
                elif distance < 1.0:
                    lines.append("ALERT: Price approaching downtrend resistance")
        else:
            lines.append("")
            lines.append("No valid downtrend line (no consecutive lower highs)")

        # Overall trend assessment
        lines.append("")
        lines.append("### Trend Assessment")

        uptrend = trend_lines.get("uptrend_valid", False)
        downtrend = trend_lines.get("downtrend_valid", False)

        if uptrend and not downtrend:
            lines.append("Overall: UPTREND (higher lows pattern)")
        elif downtrend and not uptrend:
            lines.append("Overall: DOWNTREND (lower highs pattern)")
        elif uptrend and downtrend:
            lines.append("Overall: CONSOLIDATION (both trend lines present)")
        else:
            lines.append("Overall: NO CLEAR TREND (no valid trend lines)")

        return "\n".join(lines)
