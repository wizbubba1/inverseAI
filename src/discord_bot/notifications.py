"""Discord notification service."""

from src.data.models import ConsensusResult, Direction, ExecutionResult, Trade
from src.utils.helpers import format_duration, format_pct, format_usd
from src.utils.logging import get_logger

log = get_logger(__name__)


class NotificationService:
    """Service for sending Discord notifications."""

    def __init__(self, bot):
        self.bot = bot

    async def send(self, message: str) -> None:
        """Send a message to the notification channel."""
        await self.bot.send_notification(message)

    async def trade_executed(self, result: ExecutionResult, consensus: ConsensusResult) -> None:
        """Send notification for trade execution."""
        if not result.success or not result.trade:
            return

        trade = result.trade

        message = f"""
**TRADE EXECUTED**
```
Asset: {trade.asset}-PERP
Direction: {trade.direction.value} (Fading {consensus.ta_consensus_direction.value} consensus of {consensus.consensus_strength:.0%})
Size: {format_usd(trade.size_usd)} @ {trade.leverage}x leverage
Entry: {format_usd(trade.entry_price)}
Stop Loss: {format_usd(trade.stop_loss)} ({format_pct(-3)})
Take Profit: {format_usd(trade.take_profit)} ({format_pct(6)})
Fade Signal: {consensus.fade_signal:.0f}/100
```
"""
        await self.send(message)

    async def trade_closed(self, trade: Trade) -> None:
        """Send notification for trade closure."""
        if trade.pnl_usd is None:
            return

        # Determine emoji based on P&L
        if trade.pnl_usd > 0:
            header = "**TRADE CLOSED - PROFIT**"
        else:
            header = "**TRADE CLOSED - LOSS**"

        # Calculate hold time
        if trade.exit_time and trade.entry_time:
            hold_hours = (trade.exit_time - trade.entry_time).total_seconds() / 3600
            hold_time = format_duration(hold_hours)
        else:
            hold_time = "Unknown"

        message = f"""
{header}
```
Asset: {trade.asset}-PERP
Direction: {trade.direction.value}
Entry: {format_usd(trade.entry_price)} -> Exit: {format_usd(trade.exit_price or 0)}
P&L: {format_usd(trade.pnl_usd)} ({format_pct(trade.pnl_pct or 0)})
Hold Time: {hold_time}
Exit Reason: {trade.exit_reason.value if trade.exit_reason else "Unknown"}
```
"""
        await self.send(message)

    async def trade_vetoed(self, asset: str, direction: Direction, vetoes: list[str]) -> None:
        """Send notification for vetoed trade."""
        message = f"""
**TRADE VETOED**
```
Asset: {asset}
Intended Direction: {direction.value}
Reason(s):
{chr(10).join('- ' + v for v in vetoes)}
```
"""
        await self.send(message)

    async def risk_alert(self, alert_type: str, current_value: float, limit: float) -> None:
        """Send risk alert notification."""
        message = f"""
**RISK ALERT**
```
Type: {alert_type}
Current: {format_pct(current_value)}
Limit: {format_pct(-limit)}
Action: Reducing position sizes / Trading paused
```
"""
        await self.send(message)

    async def analysis_complete(
        self,
        asset: str,
        consensus: ConsensusResult,
        trade_executed: bool = False,
    ) -> None:
        """Send notification after analysis completes."""
        action = "Trade executed" if trade_executed else "No trade"

        if consensus.should_trade:
            action_detail = f"-> {consensus.our_trade_direction.value if consensus.our_trade_direction else 'N/A'}"
        else:
            action_detail = f"({consensus.reason})"

        message = f"""
**ANALYSIS COMPLETE**
```
Asset: {asset}
TA Consensus: {consensus.ta_consensus_direction.value if consensus.ta_consensus_direction else 'N/A'} ({consensus.consensus_strength:.0%})
Fade Signal: {consensus.fade_signal:.1f}/100
Action: {action} {action_detail}
```
"""
        await self.send(message)

    async def daily_summary(
        self,
        balance: float,
        daily_pnl: float,
        daily_pnl_pct: float,
        trades_today: int,
        wins: int,
        losses: int,
        open_positions: list[dict],
    ) -> None:
        """Send daily summary notification."""
        from datetime import datetime

        date_str = datetime.utcnow().strftime("%b %d, %Y")

        positions_str = ", ".join(
            f"{p['asset']} {p['direction']}"
            for p in open_positions
        ) if open_positions else "None"

        message = f"""
**DAILY SUMMARY - {date_str}**
```
Trades: {trades_today}
Win/Loss: {wins}/{losses}
Daily P&L: {format_usd(daily_pnl)} ({format_pct(daily_pnl_pct)})
Total Balance: {format_usd(balance)}
Open Positions: {positions_str}
```
"""
        await self.send(message)

    async def system_status(self, status: str, details: str = "") -> None:
        """Send system status notification."""
        message = f"""
**SYSTEM STATUS**
```
Status: {status}
{details}
```
"""
        await self.send(message)

    async def error_alert(self, component: str, error: str) -> None:
        """Send error alert notification."""
        message = f"""
**ERROR ALERT**
```
Component: {component}
Error: {error}
```
"""
        await self.send(message)
