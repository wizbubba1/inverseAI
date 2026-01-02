"""Support and Resistance Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class SupportResistanceAgent(BaseAgent):
    """Agent that trades based on support and resistance levels."""

    @property
    def agent_id(self) -> str:
        return "support_resistance_agent"

    @property
    def methodology_name(self) -> str:
        return "Support and Resistance Trading"

    @property
    def methodology_description(self) -> str:
        return """Support and Resistance trading identifies horizontal price levels where price has historically reversed.

Key Principles:
- Support: Price levels where buying pressure prevents further decline
- Resistance: Price levels where selling pressure prevents further advance
- The more times a level is tested, the stronger it becomes
- Broken resistance becomes support, broken support becomes resistance

Trading Rules:
1. BUY (LONG) when price bounces off support level
2. SELL (SHORT) when price rejects from resistance level
3. Wait for confirmation (price touching level and reversing)
4. Stronger levels (more touches) = higher confidence

Confidence Levels:
- Level tested 4+ times: Very high confidence
- Level tested 3 times: High confidence
- Level tested 2 times: Moderate confidence
- Price at untested level: Low confidence

Additional Factors:
- Look for volume confirmation at S/R levels
- Consider dynamic S/R from moving averages
- VWAP acts as intraday dynamic S/R"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get S/R-specific indicator values."""
        current = indicators.get_current()
        sr_levels = indicators.get_support_resistance_levels()

        current_price = current.get("current_price")
        vwap = current.get("vwap")
        ema_50 = current.get("ema_50")
        sma_50 = current.get("sma_50")

        lines = [
            f"Current Price: {current_price:.2f}",
            "",
            "### Key Support Levels (from recent swing lows)",
        ]

        for i, level in enumerate(sr_levels.get("support", [])[:5], 1):
            distance = ((current_price - level) / current_price) * 100
            lines.append(f"  S{i}: {level:.2f} ({distance:.1f}% below current price)")

        lines.append("")
        lines.append("### Key Resistance Levels (from recent swing highs)")

        for i, level in enumerate(sr_levels.get("resistance", [])[:5], 1):
            distance = ((level - current_price) / current_price) * 100
            lines.append(f"  R{i}: {level:.2f} ({distance:.1f}% above current price)")

        lines.extend([
            "",
            "### Dynamic Support/Resistance",
            f"VWAP: {vwap:.2f}" if vwap else "VWAP: N/A",
            f"50 EMA: {ema_50:.2f}" if ema_50 else "50 EMA: N/A",
            f"50 SMA: {sma_50:.2f}" if sma_50 else "50 SMA: N/A",
        ])

        # Determine proximity to levels
        lines.append("")
        lines.append("### Current Position Analysis")

        supports = sr_levels.get("support", [])
        resistances = sr_levels.get("resistance", [])

        if supports:
            nearest_support = max([s for s in supports if s < current_price], default=None)
            if nearest_support:
                dist = ((current_price - nearest_support) / current_price) * 100
                if dist < 1:
                    lines.append(f"NEAR SUPPORT: Price is {dist:.2f}% above nearest support at {nearest_support:.2f}")

        if resistances:
            nearest_resistance = min([r for r in resistances if r > current_price], default=None)
            if nearest_resistance:
                dist = ((nearest_resistance - current_price) / current_price) * 100
                if dist < 1:
                    lines.append(f"NEAR RESISTANCE: Price is {dist:.2f}% below nearest resistance at {nearest_resistance:.2f}")

        return "\n".join(lines)
