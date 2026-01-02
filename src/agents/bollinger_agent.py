"""Bollinger Band Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class BollingerAgent(BaseAgent):
    """Agent that trades based on Bollinger Band signals."""

    @property
    def agent_id(self) -> str:
        return "bollinger_agent"

    @property
    def methodology_name(self) -> str:
        return "Bollinger Bands"

    @property
    def methodology_description(self) -> str:
        return """Bollinger Bands are volatility bands placed above and below a moving average.

Key Components:
- Middle Band: 20-period Simple Moving Average
- Upper Band: Middle Band + (2 × 20-period Standard Deviation)
- Lower Band: Middle Band - (2 × 20-period Standard Deviation)
- %B: Shows where price is relative to bands (0 = lower band, 1 = upper band)

Trading Rules (Mean Reversion Strategy):
1. BUY (LONG) when price touches or goes below lower band (oversold)
2. SELL (SHORT) when price touches or goes above upper band (overbought)
3. Expect price to revert to the middle band (mean reversion)

Band Width Analysis:
- Narrow bands (low width) = Low volatility, potential breakout coming
- Wide bands (high width) = High volatility, potential reversal

Confidence Levels:
- Price beyond outer band: Very high confidence
- Price touching band: High confidence
- Price near middle band: Low confidence (no signal)
- Squeeze (narrow bands): Prepare for breakout, wait for confirmation"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get Bollinger Band-specific indicator values."""
        current = indicators.get_current()

        current_price = current.get("current_price")
        bb_upper = current.get("bb_upper")
        bb_middle = current.get("bb_middle")
        bb_lower = current.get("bb_lower")
        bb_width = current.get("bb_width")
        bb_percent = current.get("bb_percent")

        lines = [
            f"Current Price: {current_price:.2f}",
            "",
            "### Bollinger Bands (20, 2)",
            f"Upper Band: {bb_upper:.2f}" if bb_upper else "Upper Band: N/A",
            f"Middle Band (SMA 20): {bb_middle:.2f}" if bb_middle else "Middle Band: N/A",
            f"Lower Band: {bb_lower:.2f}" if bb_lower else "Lower Band: N/A",
            "",
            f"Band Width: {bb_width:.4f}" if bb_width else "Band Width: N/A",
            f"%B: {bb_percent:.4f}" if bb_percent is not None else "%B: N/A",
            "",
        ]

        if bb_upper and bb_lower and bb_percent is not None:
            # Position analysis
            if bb_percent > 1.0:
                lines.append(f"SIGNAL: Price ABOVE upper band (extremely overbought)")
                lines.append(f"Distance above upper band: {(current_price - bb_upper):.2f}")
            elif bb_percent >= 0.95:
                lines.append(f"SIGNAL: Price touching upper band (overbought)")
            elif bb_percent <= 0.0:
                lines.append(f"SIGNAL: Price BELOW lower band (extremely oversold)")
                lines.append(f"Distance below lower band: {(bb_lower - current_price):.2f}")
            elif bb_percent <= 0.05:
                lines.append(f"SIGNAL: Price touching lower band (oversold)")
            elif 0.45 <= bb_percent <= 0.55:
                lines.append("Status: Price near middle band (neutral)")
            elif bb_percent > 0.5:
                lines.append("Status: Price in upper half of bands (bullish bias)")
            else:
                lines.append("Status: Price in lower half of bands (bearish bias)")

            # Volatility analysis
            if bb_width:
                if bb_width < 0.03:
                    lines.append("SQUEEZE ALERT: Very narrow bands (low volatility, breakout imminent)")
                elif bb_width < 0.05:
                    lines.append("Narrow bands (below average volatility)")
                elif bb_width > 0.10:
                    lines.append("Wide bands (high volatility)")

        return "\n".join(lines)
