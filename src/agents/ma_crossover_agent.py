"""Moving Average Crossover Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class MACrossoverAgent(BaseAgent):
    """Agent that trades based on EMA crossover signals."""

    @property
    def agent_id(self) -> str:
        return "ma_crossover_agent"

    @property
    def methodology_name(self) -> str:
        return "Moving Average Crossover (9 EMA / 21 EMA)"

    @property
    def methodology_description(self) -> str:
        return """Moving Average Crossover strategy uses the relationship between fast and slow moving averages.

Key Principles:
- Uses 9-period EMA (fast) and 21-period EMA (slow)
- When fast MA crosses above slow MA = "Golden Cross" (bullish signal)
- When fast MA crosses below slow MA = "Death Cross" (bearish signal)
- The separation between MAs indicates trend strength

Trading Rules:
1. BUY (LONG) when 9 EMA crosses ABOVE 21 EMA (Golden Cross)
2. SELL (SHORT) when 9 EMA crosses BELOW 21 EMA (Death Cross)
3. When fast MA is above slow MA, the trend is bullish
4. When fast MA is below slow MA, the trend is bearish

Confidence Levels:
- Recent crossover (just happened): Very high confidence
- Clear separation between MAs: High confidence
- MAs close together: Lower confidence (potential crossover coming)
- Wide gap between MAs: Could signal overextension, use caution"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get MA-specific indicator values."""
        current = indicators.get_current()

        ema_9 = current.get("ema_9")
        ema_21 = current.get("ema_21")
        prev_ema_9 = current.get("prev_ema_9")
        prev_ema_21 = current.get("prev_ema_21")
        current_price = current.get("current_price")

        lines = [
            f"Current Price: {current_price:.2f}",
            "",
            "### Exponential Moving Averages",
            f"9 EMA (current): {ema_9:.2f}" if ema_9 else "9 EMA: N/A",
            f"21 EMA (current): {ema_21:.2f}" if ema_21 else "21 EMA: N/A",
            f"9 EMA (previous bar): {prev_ema_9:.2f}" if prev_ema_9 else "9 EMA prev: N/A",
            f"21 EMA (previous bar): {prev_ema_21:.2f}" if prev_ema_21 else "21 EMA prev: N/A",
            "",
        ]

        if ema_9 and ema_21:
            spread = ema_9 - ema_21
            spread_pct = (spread / ema_21) * 100

            lines.append(f"EMA Spread: {spread:.2f} ({spread_pct:.2f}%)")

            # Detect crossover
            if prev_ema_9 and prev_ema_21:
                if prev_ema_9 <= prev_ema_21 and ema_9 > ema_21:
                    lines.append("SIGNAL: GOLDEN CROSS (9 EMA just crossed above 21 EMA)")
                elif prev_ema_9 >= prev_ema_21 and ema_9 < ema_21:
                    lines.append("SIGNAL: DEATH CROSS (9 EMA just crossed below 21 EMA)")
                elif ema_9 > ema_21:
                    lines.append("Status: Bullish trend (9 EMA above 21 EMA)")
                else:
                    lines.append("Status: Bearish trend (9 EMA below 21 EMA)")

        return "\n".join(lines)
