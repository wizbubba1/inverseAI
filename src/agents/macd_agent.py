"""MACD Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class MACDAgent(BaseAgent):
    """Agent that trades based on MACD signals."""

    @property
    def agent_id(self) -> str:
        return "macd_agent"

    @property
    def methodology_name(self) -> str:
        return "MACD (Moving Average Convergence Divergence)"

    @property
    def methodology_description(self) -> str:
        return """MACD is a trend-following momentum indicator showing the relationship between two EMAs.

Key Components:
- MACD Line: 12-period EMA minus 26-period EMA
- Signal Line: 9-period EMA of the MACD Line
- Histogram: Difference between MACD Line and Signal Line

Trading Rules:
1. BUY (LONG) when MACD Line crosses ABOVE Signal Line (bullish crossover)
2. SELL (SHORT) when MACD Line crosses BELOW Signal Line (bearish crossover)
3. Histogram increasing = momentum building in current direction
4. Histogram decreasing = momentum weakening

Confidence Levels:
- Crossover with large histogram: Very high confidence
- Fresh crossover (just happened): High confidence
- Histogram growing after crossover: High confidence
- Histogram shrinking: Lower confidence (reversal may be coming)
- Lines far from zero line: Trend is strong but may be overextended"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get MACD-specific indicator values."""
        current = indicators.get_current()

        macd_line = current.get("macd_line")
        macd_signal = current.get("macd_signal")
        macd_histogram = current.get("macd_histogram")
        prev_macd_line = current.get("prev_macd_line")
        prev_macd_signal = current.get("prev_macd_signal")
        current_price = current.get("current_price")

        lines = [
            f"Current Price: {current_price:.2f}",
            "",
            "### MACD (12, 26, 9)",
            f"MACD Line: {macd_line:.4f}" if macd_line else "MACD Line: N/A",
            f"Signal Line: {macd_signal:.4f}" if macd_signal else "Signal Line: N/A",
            f"Histogram: {macd_histogram:.4f}" if macd_histogram else "Histogram: N/A",
            "",
            "### Previous Bar Values",
            f"Prev MACD Line: {prev_macd_line:.4f}" if prev_macd_line else "Prev MACD Line: N/A",
            f"Prev Signal Line: {prev_macd_signal:.4f}" if prev_macd_signal else "Prev Signal Line: N/A",
            "",
        ]

        if macd_line is not None and macd_signal is not None:
            # Detect crossover
            if prev_macd_line is not None and prev_macd_signal is not None:
                if prev_macd_line <= prev_macd_signal and macd_line > macd_signal:
                    lines.append("SIGNAL: BULLISH CROSSOVER (MACD just crossed above Signal)")
                elif prev_macd_line >= prev_macd_signal and macd_line < macd_signal:
                    lines.append("SIGNAL: BEARISH CROSSOVER (MACD just crossed below Signal)")
                elif macd_line > macd_signal:
                    lines.append("Status: Bullish (MACD above Signal line)")
                else:
                    lines.append("Status: Bearish (MACD below Signal line)")

            # Histogram analysis
            if macd_histogram:
                if macd_histogram > 0:
                    lines.append(f"Histogram: Positive ({macd_histogram:.4f}) - Bullish momentum")
                else:
                    lines.append(f"Histogram: Negative ({macd_histogram:.4f}) - Bearish momentum")

            # Zero line analysis
            if macd_line > 0:
                lines.append("MACD above zero line (overall bullish)")
            else:
                lines.append("MACD below zero line (overall bearish)")

        return "\n".join(lines)
