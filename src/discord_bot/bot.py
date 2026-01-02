"""Discord bot for monitoring and controlling the trading system."""

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.config import get_settings
from src.utils.helpers import format_pct, format_usd
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.main import TradingOrchestrator

log = get_logger(__name__)


class TradingBot(commands.Bot):
    """Discord bot for the Inverse Sentiment Trading System."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Inverse Sentiment AI Trading Bot",
        )

        self.settings = get_settings()
        self.orchestrator: "TradingOrchestrator | None" = None
        self.channel: discord.TextChannel | None = None

    def set_orchestrator(self, orchestrator: "TradingOrchestrator") -> None:
        """Set the trading orchestrator reference."""
        self.orchestrator = orchestrator

    async def setup_hook(self) -> None:
        """Set up the bot commands."""
        # Add commands
        await self.add_cog(TradingCommands(self))

        # Sync commands
        await self.tree.sync()
        log.info("Discord commands synced")

    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        log.info(f"Discord bot logged in as {self.user}")

        # Get the notification channel
        channel_id = int(self.settings.discord_channel_id)
        self.channel = self.get_channel(channel_id)

        if self.channel:
            log.info(f"Notification channel: #{self.channel.name}")
        else:
            log.warning(f"Could not find channel with ID {channel_id}")

    async def send_notification(self, message: str) -> None:
        """Send a notification to the configured channel."""
        if self.channel:
            try:
                await self.channel.send(message)
            except Exception as e:
                log.error(f"Failed to send notification: {e}")


class TradingCommands(commands.Cog):
    """Trading bot commands."""

    def __init__(self, bot: TradingBot):
        self.bot = bot

    def _check_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user is an admin."""
        admin_ids = self.bot.settings.admin_ids
        return str(interaction.user.id) in admin_ids if admin_ids else True

    @app_commands.command(name="status", description="Get current system status")
    async def status(self, interaction: discord.Interaction) -> None:
        """Get current system status."""
        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        orch = self.bot.orchestrator

        # Get risk manager status
        risk_status = "PAUSED" if orch.risk_manager.is_paused else "RUNNING"
        pause_reason = orch.risk_manager.pause_reason or ""

        # Get last analysis time
        last_analysis = orch.last_analysis_time
        last_analysis_str = last_analysis.strftime("%Y-%m-%d %H:%M UTC") if last_analysis else "Never"

        # Get next scheduled run
        next_run = orch.next_analysis_time
        next_run_str = next_run.strftime("%Y-%m-%d %H:%M UTC") if next_run else "Unknown"

        message = f"""```
SYSTEM STATUS
=============
Status: {risk_status}
{f"Reason: {pause_reason}" if pause_reason else ""}
Mode: {"PAPER" if self.bot.settings.paper_trading else "LIVE"}

Last Analysis: {last_analysis_str}
Next Analysis: {next_run_str}
Analysis Interval: {self.bot.settings.analysis_interval_hours}h

Assets: {', '.join(self.bot.settings.assets_list)}
```"""
        await interaction.response.send_message(message)

    @app_commands.command(name="balance", description="Get current wallet balance")
    async def balance(self, interaction: discord.Interaction) -> None:
        """Get current wallet balance."""
        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        try:
            balance = await self.bot.orchestrator.exchange.get_account_balance()
            positions = await self.bot.orchestrator.exchange.get_open_positions()

            total_exposure = sum(abs(p["size"]) * p["entry_price"] for p in positions)
            unrealized_pnl = sum(p["unrealized_pnl"] for p in positions)

            message = f"""```
ACCOUNT BALANCE
===============
Balance: {format_usd(balance)}
Unrealized P&L: {format_usd(unrealized_pnl)}
Total Exposure: {format_usd(total_exposure)}
Available Margin: {format_usd(balance - total_exposure)}
Open Positions: {len(positions)}
```"""
            await interaction.response.send_message(message)
        except Exception as e:
            await interaction.response.send_message(f"Error getting balance: {e}")

    @app_commands.command(name="positions", description="View all open positions")
    async def positions(self, interaction: discord.Interaction) -> None:
        """View all open positions."""
        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        try:
            positions = await self.bot.orchestrator.exchange.get_open_positions()

            if not positions:
                await interaction.response.send_message("No open positions")
                return

            lines = ["```", "OPEN POSITIONS", "=" * 40]

            for pos in positions:
                direction = "LONG" if pos["size"] > 0 else "SHORT"
                lines.extend([
                    "",
                    f"{pos['asset']} - {direction}",
                    f"  Size: {abs(pos['size']):.4f}",
                    f"  Entry: {format_usd(pos['entry_price'])}",
                    f"  P&L: {format_usd(pos['unrealized_pnl'])}",
                    f"  Leverage: {pos['leverage']}x",
                ])
                if pos.get("liquidation_price"):
                    lines.append(f"  Liq. Price: {format_usd(pos['liquidation_price'])}")

            lines.append("```")
            await interaction.response.send_message("\n".join(lines))
        except Exception as e:
            await interaction.response.send_message(f"Error getting positions: {e}")

    @app_commands.command(name="history", description="View recent trade history")
    @app_commands.describe(limit="Number of trades to show (default 10)")
    async def history(self, interaction: discord.Interaction, limit: int = 10) -> None:
        """View recent trade history."""
        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        try:
            trades = await self.bot.orchestrator.db.get_recent_trades(limit)

            if not trades:
                await interaction.response.send_message("No trade history")
                return

            lines = ["```", f"LAST {len(trades)} TRADES", "=" * 40]

            for trade in trades:
                status = trade.status.value
                pnl_str = format_usd(trade.pnl_usd) if trade.pnl_usd else "Open"
                pnl_pct = format_pct(trade.pnl_pct) if trade.pnl_pct else ""

                lines.extend([
                    "",
                    f"{trade.asset} - {trade.direction.value} ({status})",
                    f"  Entry: {format_usd(trade.entry_price)} @ {trade.entry_time.strftime('%m/%d %H:%M')}",
                ])

                if trade.exit_price:
                    lines.append(f"  Exit: {format_usd(trade.exit_price)} ({trade.exit_reason.value if trade.exit_reason else 'N/A'})")
                    lines.append(f"  P&L: {pnl_str} ({pnl_pct})")

            lines.append("```")
            await interaction.response.send_message("\n".join(lines))
        except Exception as e:
            await interaction.response.send_message(f"Error getting history: {e}")

    @app_commands.command(name="performance", description="View performance metrics")
    async def performance(self, interaction: discord.Interaction) -> None:
        """View performance metrics."""
        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        try:
            metrics = await self.bot.orchestrator.db.get_performance_metrics()

            message = f"""```
PERFORMANCE METRICS
==================
Total Trades: {metrics['total_trades']}
Winning: {metrics['winning_trades']} | Losing: {metrics['losing_trades']}
Win Rate: {metrics['win_rate']:.1f}%

Total P&L: {format_usd(metrics['total_pnl'])}
Avg P&L: {format_pct(metrics['avg_pnl_pct'])}

Best Trade: {format_usd(metrics['best_trade'])}
Worst Trade: {format_usd(metrics['worst_trade'])}

Avg Win: {format_usd(metrics['avg_win'])}
Avg Loss: {format_usd(metrics['avg_loss'])}
Profit Factor: {metrics['profit_factor']:.2f}
```"""
            await interaction.response.send_message(message)
        except Exception as e:
            await interaction.response.send_message(f"Error getting performance: {e}")

    @app_commands.command(name="agents", description="View TA agent signals")
    async def agents(self, interaction: discord.Interaction) -> None:
        """View the latest TA agent signals."""
        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        if not self.bot.orchestrator.last_agent_outputs:
            await interaction.response.send_message("No recent agent analysis available")
            return

        summary = self.bot.orchestrator.consensus_engine.get_agent_summary(
            self.bot.orchestrator.last_agent_outputs
        )

        # Truncate if too long for Discord
        if len(summary) > 1900:
            summary = summary[:1900] + "\n..."

        await interaction.response.send_message(f"```md\n{summary}\n```")

    @app_commands.command(name="consensus", description="View latest consensus analysis")
    async def consensus(self, interaction: discord.Interaction) -> None:
        """View the latest consensus analysis."""
        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        if not self.bot.orchestrator.last_consensus:
            await interaction.response.send_message("No recent consensus available")
            return

        cons = self.bot.orchestrator.last_consensus

        message = f"""```
LATEST CONSENSUS
================
Should Trade: {"YES" if cons.should_trade else "NO"}
Reason: {cons.reason}

TA Consensus: {cons.ta_consensus_direction.value if cons.ta_consensus_direction else "N/A"}
Our Trade: {cons.our_trade_direction.value if cons.our_trade_direction else "N/A"}

Agreement: {cons.consensus_strength:.0%}
Confidence: {cons.avg_confidence:.0%}
Fade Signal: {cons.fade_signal:.1f}/100

Agent Breakdown:
  LONG: {cons.agent_breakdown.get('long', 0)}
  SHORT: {cons.agent_breakdown.get('short', 0)}
  NEUTRAL: {cons.agent_breakdown.get('neutral', 0)}
```"""
        await interaction.response.send_message(message)

    @app_commands.command(name="pause", description="Pause trading (admin only)")
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pause trading."""
        if not self._check_admin(interaction):
            await interaction.response.send_message("You don't have permission to do this", ephemeral=True)
            return

        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        self.bot.orchestrator.risk_manager.pause_trading("Manually paused via Discord")
        await interaction.response.send_message("Trading PAUSED")

    @app_commands.command(name="resume", description="Resume trading (admin only)")
    async def resume(self, interaction: discord.Interaction) -> None:
        """Resume trading."""
        if not self._check_admin(interaction):
            await interaction.response.send_message("You don't have permission to do this", ephemeral=True)
            return

        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        self.bot.orchestrator.risk_manager.resume_trading()
        await interaction.response.send_message("Trading RESUMED")

    @app_commands.command(name="config", description="View current risk configuration")
    async def config(self, interaction: discord.Interaction) -> None:
        """View current risk configuration."""
        from src.config import get_risk_config
        config = get_risk_config()

        message = f"""```
RISK CONFIGURATION
==================
Position Limits:
  Max Position Size: {format_usd(config.max_position_size_usd)}
  Max Total Exposure: {format_usd(config.max_total_exposure_usd)}
  Max Leverage: {config.max_leverage}x

Drawdown Limits:
  Daily: -{config.max_daily_drawdown_pct}%
  Weekly: -{config.max_weekly_drawdown_pct}%
  Total: -{config.max_total_drawdown_pct}%

Trade Limits:
  Max Trades/Day: {config.max_trades_per_day}
  Min Time Between: {config.min_time_between_trades_hours}h

Stop Loss: -{config.default_stop_loss_pct}%
Take Profit: +{config.default_take_profit_pct}%
Trailing Stop: {"Enabled" if config.trailing_stop_enabled else "Disabled"}
```"""
        await interaction.response.send_message(message)

    @app_commands.command(name="analyze", description="Force analysis for an asset (admin only)")
    @app_commands.describe(asset="Asset to analyze (e.g., BTC, ETH)")
    async def analyze(self, interaction: discord.Interaction, asset: str) -> None:
        """Force an analysis for a specific asset."""
        if not self._check_admin(interaction):
            await interaction.response.send_message("You don't have permission to do this", ephemeral=True)
            return

        if not self.bot.orchestrator:
            await interaction.response.send_message("System not initialized")
            return

        await interaction.response.defer()

        try:
            result = await self.bot.orchestrator.analyze_asset(asset.upper())

            if result:
                await interaction.followup.send(
                    f"Analysis complete for {asset.upper()}. "
                    f"Check /consensus for results."
                )
            else:
                await interaction.followup.send(f"Analysis failed for {asset.upper()}")
        except Exception as e:
            await interaction.followup.send(f"Error during analysis: {e}")
