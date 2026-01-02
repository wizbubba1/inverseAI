"""Volume Profile Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class VolumeProfileAgent(BaseAgent):
    """Agent that trades based on volume analysis and volume profile."""

    @property
    def agent_id(self) -> str:
        return "volume_profile_agent"

    @property
    def methodology_name(self) -> str:
        return "Volume Profile Analysis"

    @property
    def methodology_description(self) -> str:
        return """Volume Profile analysis examines where trading volume occurs at different price levels.

Key Concepts:
- Point of Control (POC): Price level with most trading volume
- High Volume Nodes (HVN): Price levels with significant volume concentration
- Low Volume Nodes (LVN): Price levels with little volume (price moves quickly through these)
- Value Area: Range containing 70% of volume

Trading Rules:
1. BUY (LONG) at high-volume support zones (HVN below current price)
2. SELL (SHORT) at high-volume resistance zones (HVN above current price)
3. POC acts as a magnet - price tends to return to it
4. LVN levels offer little resistance - quick moves through them

Volume Confirmation:
- High volume on breakouts = strength
- Low volume on breakouts = likely fake out
- Volume increasing with trend = healthy trend
- Volume decreasing with trend = weakening trend

Confidence Levels:
- Price at HVN with volume confirmation: High confidence
- Price at POC: Moderate confidence (could go either way)
- Price at LVN: Low confidence (unstable level)"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get volume-specific indicator values."""
        current = indicators.get_current()
        volume_zones = indicators.get_volume_profile_zones()

        current_price = current.get("current_price")
        volume = current.get("volume")
        volume_sma = current.get("volume_sma_20")
        volume_ratio = current.get("volume_ratio")
        vwap = current.get("vwap")

        lines = [
            f"Current Price: {current_price:.2f}",
            "",
            "### Volume Analysis",
            f"Current Volume: {volume:.2f}" if volume else "Volume: N/A",
            f"20-period Volume SMA: {volume_sma:.2f}" if volume_sma else "Volume SMA: N/A",
            f"Volume Ratio (vs SMA): {volume_ratio:.2f}x" if volume_ratio else "Volume Ratio: N/A",
            f"VWAP: {vwap:.2f}" if vwap else "VWAP: N/A",
            "",
        ]

        # Volume interpretation
        if volume_ratio:
            if volume_ratio > 2.0:
                lines.append("ALERT: Very high volume (2x+ average) - significant interest")
            elif volume_ratio > 1.5:
                lines.append("High volume (above average)")
            elif volume_ratio < 0.5:
                lines.append("Low volume (below average) - weak conviction")

        lines.extend([
            "",
            "### Volume Profile Zones",
            f"Point of Control (POC): {volume_zones.get('poc', 'N/A'):.2f}" if volume_zones.get('poc') else "POC: N/A",
        ])

        # High volume zones
        hv_zones = volume_zones.get("high_volume_zones", [])
        if hv_zones:
            lines.append("")
            lines.append("High Volume Nodes:")
            for zone in hv_zones[:5]:
                position = "above" if zone > current_price else "below"
                distance = abs((zone - current_price) / current_price) * 100
                lines.append(f"  {zone:.2f} ({distance:.1f}% {position})")

        # Nearest S/R from volume
        nearest_support = volume_zones.get("nearest_hv_support")
        nearest_resistance = volume_zones.get("nearest_hv_resistance")

        lines.extend([
            "",
            "### Volume-Based Support/Resistance",
        ])

        if nearest_support:
            dist = ((current_price - nearest_support) / current_price) * 100
            lines.append(f"Nearest HV Support: {nearest_support:.2f} ({dist:.1f}% below)")

        if nearest_resistance:
            dist = ((nearest_resistance - current_price) / current_price) * 100
            lines.append(f"Nearest HV Resistance: {nearest_resistance:.2f} ({dist:.1f}% above)")

        # VWAP relationship
        if vwap and current_price:
            if current_price > vwap:
                lines.append(f"Price ABOVE VWAP (bullish intraday)")
            else:
                lines.append(f"Price BELOW VWAP (bearish intraday)")

        return "\n".join(lines)
