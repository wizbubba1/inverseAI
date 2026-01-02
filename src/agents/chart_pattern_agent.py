"""Chart Pattern Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class ChartPatternAgent(BaseAgent):
    """Agent that trades based on chart pattern recognition."""

    @property
    def agent_id(self) -> str:
        return "chart_pattern_agent"

    @property
    def methodology_name(self) -> str:
        return "Chart Pattern Recognition"

    @property
    def methodology_description(self) -> str:
        return """Chart Pattern trading identifies and trades classic price patterns.

Reversal Patterns:
- Head and Shoulders: Bearish reversal (three peaks, middle highest)
- Inverse Head and Shoulders: Bullish reversal (three troughs, middle lowest)
- Double Top: Bearish reversal (two peaks at same level)
- Double Bottom: Bullish reversal (two troughs at same level)

Continuation Patterns:
- Ascending Triangle: Bullish (flat resistance, rising support)
- Descending Triangle: Bearish (flat support, falling resistance)
- Bull Flag: Bullish (downward consolidation after uptrend)
- Bear Flag: Bearish (upward consolidation after downtrend)

Trading Rules:
1. BUY (LONG) on:
   - Inverse Head and Shoulders breakout above neckline
   - Double Bottom breakout above middle peak
   - Ascending Triangle breakout above resistance
   - Bull Flag breakout above flag

2. SELL (SHORT) on:
   - Head and Shoulders breakdown below neckline
   - Double Top breakdown below middle trough
   - Descending Triangle breakdown below support
   - Bear Flag breakdown below flag

Confidence Levels:
- Clear pattern with volume confirmation: Very high
- Clear pattern without volume confirmation: High
- Developing pattern: Moderate
- Ambiguous pattern: Low

Pattern Quality:
- Symmetry improves pattern reliability
- Volume should decline during pattern formation
- Volume should spike on breakout"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get pattern-specific indicator values."""
        current = indicators.get_current()
        patterns = indicators.get_chart_patterns()
        sr_levels = indicators.get_support_resistance_levels()

        current_price = current.get("current_price")
        volume_ratio = current.get("volume_ratio")

        lines = [
            f"Current Price: {current_price:.2f}",
            f"Volume Ratio: {volume_ratio:.2f}x average" if volume_ratio else "Volume Ratio: N/A",
            "",
            "### Detected Patterns",
        ]

        patterns_found = False

        # Double Top
        if patterns.get("double_top"):
            patterns_found = True
            level = patterns.get("double_top_level")
            lines.extend([
                "",
                "DOUBLE TOP DETECTED (Bearish Reversal)",
                f"Double Top Level: {level:.2f}" if level else "",
                "Signal: Wait for breakdown below recent low (neckline)",
            ])
            if current_price < level:
                lines.append("Status: Price below double top - BEARISH CONFIRMED")

        # Double Bottom
        if patterns.get("double_bottom"):
            patterns_found = True
            level = patterns.get("double_bottom_level")
            lines.extend([
                "",
                "DOUBLE BOTTOM DETECTED (Bullish Reversal)",
                f"Double Bottom Level: {level:.2f}" if level else "",
                "Signal: Wait for breakout above recent high (neckline)",
            ])
            if current_price > level:
                lines.append("Status: Price above double bottom - BULLISH CONFIRMED")

        # Head and Shoulders
        if patterns.get("head_and_shoulders"):
            patterns_found = True
            neckline = patterns.get("neckline")
            lines.extend([
                "",
                "HEAD AND SHOULDERS DETECTED (Bearish Reversal)",
                f"Neckline: {neckline:.2f}" if neckline else "",
                "Signal: SELL on breakdown below neckline",
            ])
            if neckline and current_price < neckline:
                lines.append("STATUS: BREAKDOWN CONFIRMED - Strong bearish signal!")

        # Inverse Head and Shoulders
        if patterns.get("inverse_head_and_shoulders"):
            patterns_found = True
            neckline = patterns.get("neckline")
            lines.extend([
                "",
                "INVERSE HEAD AND SHOULDERS DETECTED (Bullish Reversal)",
                f"Neckline: {neckline:.2f}" if neckline else "",
                "Signal: BUY on breakout above neckline",
            ])
            if neckline and current_price > neckline:
                lines.append("STATUS: BREAKOUT CONFIRMED - Strong bullish signal!")

        if not patterns_found:
            lines.append("No classic patterns currently detected")
            lines.append("")
            lines.append("Scanning for developing patterns based on swing points...")

        # Additional context from S/R levels
        lines.extend([
            "",
            "### Key Levels for Pattern Analysis",
            "Recent Swing Highs (potential resistance/necklines):",
        ])

        for i, level in enumerate(sr_levels.get("resistance", [])[:3], 1):
            lines.append(f"  R{i}: {level:.2f}")

        lines.append("Recent Swing Lows (potential support/necklines):")
        for i, level in enumerate(sr_levels.get("support", [])[:3], 1):
            lines.append(f"  S{i}: {level:.2f}")

        # Volume analysis for pattern confirmation
        lines.extend([
            "",
            "### Volume Confirmation",
        ])

        if volume_ratio:
            if volume_ratio > 1.5:
                lines.append("HIGH VOLUME: Good for breakout/breakdown confirmation")
            elif volume_ratio < 0.7:
                lines.append("LOW VOLUME: Pattern may lack conviction")
            else:
                lines.append("NORMAL VOLUME: Neutral volume reading")

        return "\n".join(lines)

    def get_extra_context(self, indicators: TechnicalIndicators) -> str:
        """Provide additional pattern recognition guidance."""
        return """
## Pattern Trading Tips
- Wait for confirmed breakout/breakdown before entering
- Use the pattern height to project price target
- Place stops just beyond the opposite side of the pattern
- Higher timeframe patterns are more reliable
- Volume confirmation is crucial for pattern validity
"""
