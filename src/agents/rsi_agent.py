"""RSI-based Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class RSIAgent(BaseAgent):
    """Agent that trades based on RSI (Relative Strength Index) signals."""

    @property
    def agent_id(self) -> str:
        return "rsi_agent"

    @property
    def methodology_name(self) -> str:
        return "RSI (Relative Strength Index)"

    @property
    def methodology_description(self) -> str:
        return """RSI is a momentum oscillator that measures the speed and magnitude of recent price changes.

Key Principles:
- RSI ranges from 0 to 100
- RSI below 30 indicates OVERSOLD conditions (potential buy signal)
- RSI above 70 indicates OVERBOUGHT conditions (potential sell signal)
- Divergences between RSI and price can signal reversals

Trading Rules:
1. BUY (LONG) when RSI drops below 30 and starts to turn up
2. SELL (SHORT) when RSI rises above 70 and starts to turn down
3. The more extreme the RSI reading, the stronger the signal
4. Look for divergences: price making new highs while RSI makes lower highs (bearish divergence)
   or price making new lows while RSI makes higher lows (bullish divergence)

Confidence Levels:
- RSI < 20 or > 80: Very high confidence (extreme readings)
- RSI < 30 or > 70: High confidence (standard oversold/overbought)
- RSI 30-40 or 60-70: Moderate confidence
- RSI 40-60: Low confidence (neutral zone)"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get RSI-specific indicator values."""
        current = indicators.get_current()

        rsi = current.get("rsi_14")
        current_price = current.get("current_price")
        prev_close = current.get("prev_close")

        lines = [
            f"Current Price: {current_price:.2f}",
            f"Previous Close: {prev_close:.2f}",
            "",
            "### RSI (14-period)",
            f"Current RSI: {rsi:.2f}" if rsi else "RSI: N/A",
            "",
        ]

        if rsi:
            if rsi < 30:
                lines.append("Status: OVERSOLD (potential buy zone)")
            elif rsi > 70:
                lines.append("Status: OVERBOUGHT (potential sell zone)")
            else:
                lines.append("Status: NEUTRAL zone")

        return "\n".join(lines)
