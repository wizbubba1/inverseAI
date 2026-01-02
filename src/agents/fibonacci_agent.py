"""Fibonacci Retracement Technical Analysis Agent."""

from src.agents.base_agent import BaseAgent
from src.data.indicators import TechnicalIndicators


class FibonacciAgent(BaseAgent):
    """Agent that trades based on Fibonacci retracement levels."""

    @property
    def agent_id(self) -> str:
        return "fibonacci_agent"

    @property
    def methodology_name(self) -> str:
        return "Fibonacci Retracement"

    @property
    def methodology_description(self) -> str:
        return """Fibonacci Retracement uses mathematical ratios to identify potential reversal levels.

Key Fibonacci Levels:
- 0.236 (23.6%): Shallow retracement
- 0.382 (38.2%): Moderate retracement
- 0.500 (50.0%): Half-way retracement
- 0.618 (61.8%): Golden ratio - most important level
- 0.786 (78.6%): Deep retracement

Extension Levels (for targets):
- 1.272 (127.2%): First extension target
- 1.618 (161.8%): Golden ratio extension

Trading Rules:
1. BUY (LONG) when price retraces to 0.618 or 0.786 in an uptrend
2. SELL (SHORT) when price retraces to 0.618 or 0.786 in a downtrend
3. Use extension levels for take profit targets
4. 0.618 is the most reliable reversal level

Confidence Levels:
- Price at 0.618 with other confluence: Very high confidence
- Price at 0.786 (deep retracement): High confidence
- Price at 0.382 or 0.500: Moderate confidence
- Price between levels: Lower confidence"""

    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get Fibonacci-specific indicator values."""
        current = indicators.get_current()
        fib_levels = indicators.get_fibonacci_levels()

        current_price = current.get("current_price")

        lines = [
            f"Current Price: {current_price:.2f}",
            "",
            "### Fibonacci Levels",
        ]

        if fib_levels:
            swing_high = fib_levels.get("swing_high")
            swing_low = fib_levels.get("swing_low")

            lines.extend([
                f"Recent Swing High: {swing_high:.2f}" if swing_high else "Swing High: N/A",
                f"Recent Swing Low: {swing_low:.2f}" if swing_low else "Swing Low: N/A",
                "",
                "### Retracement Levels",
            ])

            # List each fib level with distance from current price
            for key in ["fib_0", "fib_236", "fib_382", "fib_500", "fib_618", "fib_786", "fib_100"]:
                level = fib_levels.get(key)
                if level:
                    pct_key = key.replace("fib_", "")
                    if pct_key == "0":
                        label = "0% (Swing Point)"
                    elif pct_key == "100":
                        label = "100% (Swing Point)"
                    else:
                        label = f"{float(pct_key)/10:.1f}%"

                    distance = ((level - current_price) / current_price) * 100
                    direction = "above" if level > current_price else "below"
                    lines.append(f"  {label}: {level:.2f} ({abs(distance):.1f}% {direction})")

            lines.extend([
                "",
                "### Extension Levels (Targets)",
            ])

            for key in ["fib_1272", "fib_1618"]:
                level = fib_levels.get(key)
                if level:
                    pct_key = key.replace("fib_", "")
                    label = f"{float(pct_key)/10:.1f}%"
                    distance = ((level - current_price) / current_price) * 100
                    direction = "above" if level > current_price else "below"
                    lines.append(f"  {label}: {level:.2f} ({abs(distance):.1f}% {direction})")

            # Find nearest levels
            lines.append("")
            lines.append("### Position Analysis")

            nearest_below = None
            nearest_above = None

            for key in ["fib_236", "fib_382", "fib_500", "fib_618", "fib_786"]:
                level = fib_levels.get(key)
                if level:
                    if level < current_price and (nearest_below is None or level > nearest_below[1]):
                        nearest_below = (key, level)
                    if level > current_price and (nearest_above is None or level < nearest_above[1]):
                        nearest_above = (key, level)

            if nearest_below:
                pct = nearest_below[0].replace("fib_", "")
                lines.append(f"Nearest Fib BELOW: {float(pct)/10:.1f}% at {nearest_below[1]:.2f}")

            if nearest_above:
                pct = nearest_above[0].replace("fib_", "")
                lines.append(f"Nearest Fib ABOVE: {float(pct)/10:.1f}% at {nearest_above[1]:.2f}")

            # Check if at key levels
            fib_618 = fib_levels.get("fib_618")
            fib_786 = fib_levels.get("fib_786")

            if fib_618:
                if abs((current_price - fib_618) / current_price) < 0.005:  # Within 0.5%
                    lines.append("SIGNAL: Price at GOLDEN RATIO (61.8%) level!")

            if fib_786:
                if abs((current_price - fib_786) / current_price) < 0.005:
                    lines.append("SIGNAL: Price at DEEP RETRACEMENT (78.6%) level!")
        else:
            lines.append("Unable to calculate Fibonacci levels (insufficient swing points)")

        return "\n".join(lines)
