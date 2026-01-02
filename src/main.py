"""Main entry point and orchestrator for the Inverse Sentiment Trading System."""

import asyncio
import signal
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.agents import create_all_agents
from src.config import get_settings
from src.consensus.engine import ConsensusEngine
from src.data.database import Database
from src.data.indicators import TechnicalIndicators
from src.data.models import (
    AgentAnalysis,
    AgentOutput,
    ConsensusRecord,
    ConsensusResult,
    Direction,
    LogLevel,
    RiskSnapshot,
    TradeDecision,
)
from src.data.price_feeds import create_price_feed
from src.discord_bot.bot import TradingBot
from src.discord_bot.notifications import NotificationService
from src.execution.executor import TradeExecutor
from src.execution.hyperliquid_client import HyperliquidClient
from src.risk.manager import RiskManager
from src.utils.helpers import utc_now
from src.utils.logging import get_logger, setup_logging

log = get_logger(__name__)


class TradingOrchestrator:
    """Main orchestrator that coordinates all components.

    This is the brain of the system that:
    - Runs analysis cycles on schedule
    - Coordinates TA agents
    - Processes consensus signals
    - Executes trades through the trade executor
    - Manages the Discord bot for monitoring
    """

    def __init__(self):
        self.settings = get_settings()

        # Initialize components
        self.db = Database(self.settings.db_path)
        self.price_feed = create_price_feed(testnet=self.settings.hyperliquid_testnet)
        self.exchange = HyperliquidClient(testnet=self.settings.hyperliquid_testnet)
        self.risk_manager = RiskManager()
        self.consensus_engine = ConsensusEngine()
        self.ta_agents = create_all_agents()

        # Trade executor
        self.executor = TradeExecutor(
            exchange=self.exchange,
            risk_manager=self.risk_manager,
            database=self.db,
        )

        # Discord bot
        self.discord_bot = TradingBot()
        self.discord_bot.set_orchestrator(self)
        self.notifications = NotificationService(self.discord_bot)

        # Scheduler
        self.scheduler = AsyncIOScheduler()

        # State
        self.last_analysis_time: datetime | None = None
        self.next_analysis_time: datetime | None = None
        self.last_agent_outputs: list[AgentOutput] = []
        self.last_consensus: ConsensusResult | None = None
        self._running = False

    async def start(self) -> None:
        """Start the trading system."""
        log.info("Starting Inverse Sentiment Trading System")

        # Connect to database
        await self.db.connect()
        log.info("Database connected")

        # Schedule the main analysis loop
        self.scheduler.add_job(
            self.run_analysis_cycle,
            trigger=IntervalTrigger(hours=self.settings.analysis_interval_hours),
            id="main_analysis",
            name="Main Analysis Cycle",
            next_run_time=utc_now() + timedelta(seconds=10),  # First run in 10 seconds
        )

        # Schedule trailing stop updates (every 15 minutes)
        self.scheduler.add_job(
            self.executor.update_trailing_stops,
            trigger=IntervalTrigger(minutes=15),
            id="trailing_stops",
            name="Trailing Stop Updates",
        )

        # Schedule position exit checks for paper trading (every 5 minutes)
        if self.settings.paper_trading:
            self.scheduler.add_job(
                self._check_paper_exits,
                trigger=IntervalTrigger(minutes=5),
                id="paper_exits",
                name="Paper Trade Exit Checks",
            )

        # Schedule daily summary (at midnight UTC)
        self.scheduler.add_job(
            self._send_daily_summary,
            trigger=IntervalTrigger(days=1),
            id="daily_summary",
            name="Daily Summary",
        )

        # Start scheduler
        self.scheduler.start()
        log.info("Scheduler started")

        # Update next analysis time
        job = self.scheduler.get_job("main_analysis")
        if job and job.next_run_time:
            self.next_analysis_time = job.next_run_time.replace(tzinfo=timezone.utc)

        # Start Discord bot
        self._running = True

        try:
            await self.discord_bot.start(
                self.settings.discord_bot_token.get_secret_value()
            )
        except Exception as e:
            log.error(f"Discord bot error: {e}")
            self._running = False

    async def stop(self) -> None:
        """Stop the trading system."""
        log.info("Stopping trading system")
        self._running = False

        # Stop scheduler
        self.scheduler.shutdown(wait=False)

        # Close Discord bot
        await self.discord_bot.close()

        # Close database
        await self.db.close()

        log.info("Trading system stopped")

    async def run_analysis_cycle(self) -> None:
        """Run a complete analysis cycle for all configured assets."""
        log.info("Starting analysis cycle")
        self.last_analysis_time = utc_now()

        try:
            for asset in self.settings.assets_list:
                await self.analyze_asset(asset)

            # Update next analysis time
            job = self.scheduler.get_job("main_analysis")
            if job and job.next_run_time:
                self.next_analysis_time = job.next_run_time.replace(tzinfo=timezone.utc)

        except Exception as e:
            log.error(f"Error in analysis cycle: {e}")
            await self.notifications.error_alert("Orchestrator", str(e))
            await self.db.log(LogLevel.ERROR, "ORCHESTRATOR", f"Analysis cycle error: {e}")

    async def analyze_asset(self, asset: str) -> bool:
        """Run analysis for a single asset.

        Returns True if analysis completed successfully.
        """
        log.info(f"Analyzing {asset}")

        try:
            # 1. Fetch price data
            price_data = await self.price_feed.fetch_ohlcv(asset, "4h", 100)
            indicators = TechnicalIndicators(price_data)

            log.info(f"Fetched {len(price_data.df)} candles for {asset}")

            # 2. Run all TA agents in parallel
            agent_tasks = [
                agent.analyze(asset, price_data, indicators)
                for agent in self.ta_agents
            ]
            agent_outputs = await asyncio.gather(*agent_tasks)

            self.last_agent_outputs = agent_outputs

            # Log each agent's output
            for output in agent_outputs:
                log.info(
                    f"Agent {output.agent_id}: {output.direction.value} ({output.confidence:.0%})"
                )

                # Save to database
                await self.db.save_agent_analysis(
                    AgentAnalysis(
                        timestamp=output.timestamp,
                        agent_id=output.agent_id,
                        asset=output.asset,
                        direction=output.direction,
                        confidence=output.confidence,
                        reasoning=output.reasoning,
                        indicator_data=output.indicators,
                    )
                )

            # 3. Calculate consensus
            consensus = self.consensus_engine.calculate(agent_outputs)
            self.last_consensus = consensus

            log.info(
                "Consensus calculated",
                ta_direction=consensus.ta_consensus_direction.value if consensus.ta_consensus_direction else "N/A",
                strength=f"{consensus.consensus_strength:.0%}",
                fade_signal=f"{consensus.fade_signal:.1f}/100",
                should_trade=consensus.should_trade,
            )

            # 4. Save consensus record
            consensus_record = ConsensusRecord(
                timestamp=utc_now(),
                asset=asset,
                ta_consensus_direction=consensus.ta_consensus_direction or Direction.NEUTRAL,
                our_trade_direction=consensus.our_trade_direction,
                consensus_strength=consensus.consensus_strength,
                avg_confidence=consensus.avg_confidence,
                fade_signal=consensus.fade_signal,
                agent_breakdown=consensus.agent_breakdown,
                should_trade=consensus.should_trade,
            )
            consensus_record.id = await self.db.save_consensus_record(consensus_record)

            # 5. Execute trade if conditions are met
            trade_executed = False
            if consensus.should_trade:
                log.info(
                    f"Trade signal: {consensus.our_trade_direction.value} "
                    f"(inverse of {consensus.ta_consensus_direction.value})"
                )

                trade_decision = TradeDecision(
                    asset=asset,
                    direction=consensus.our_trade_direction,
                    fade_signal=consensus.fade_signal,
                    consensus=consensus,
                )

                result = await self.executor.execute_trade(trade_decision, consensus_record)

                if result.success:
                    trade_executed = True
                    await self.db.mark_consensus_trade_executed(consensus_record.id)
                    await self.notifications.trade_executed(result, consensus)
                    log.info(f"Trade executed: {result.trade.asset if result.trade else 'N/A'}")
                else:
                    log.warning(f"Trade not executed: {result.reason}")
                    if "veto" in result.reason.lower():
                        await self.notifications.trade_vetoed(
                            asset,
                            consensus.our_trade_direction,
                            result.reason.split(": ")[1].split("; ") if ": " in result.reason else [result.reason],
                        )

            # 6. Send analysis notification
            await self.notifications.analysis_complete(asset, consensus, trade_executed)

            # 7. Log to database
            await self.db.log(
                LogLevel.INFO,
                "ORCHESTRATOR",
                f"Analysis complete for {asset}",
                {
                    "should_trade": consensus.should_trade,
                    "trade_executed": trade_executed,
                    "fade_signal": consensus.fade_signal,
                },
            )

            return True

        except Exception as e:
            log.error(f"Error analyzing {asset}: {e}")
            await self.db.log(LogLevel.ERROR, "ORCHESTRATOR", f"Analysis error for {asset}: {e}")
            return False

    async def _check_paper_exits(self) -> None:
        """Check and execute paper trade exits."""
        try:
            closed_trades = await self.executor.check_position_exits()
            for trade in closed_trades:
                await self.notifications.trade_closed(trade)
        except Exception as e:
            log.error(f"Error checking paper exits: {e}")

    async def _send_daily_summary(self) -> None:
        """Send daily performance summary."""
        try:
            balance = await self.exchange.get_account_balance()
            portfolio = await self.db.get_portfolio_state(balance)
            positions = await self.exchange.get_open_positions()

            # Get today's trades
            today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
            trades = await self.db.get_trades_since(today_start)

            wins = sum(1 for t in trades if t.pnl_usd and t.pnl_usd > 0)
            losses = sum(1 for t in trades if t.pnl_usd and t.pnl_usd < 0)
            daily_pnl = sum(t.pnl_usd or 0 for t in trades)

            open_positions = [
                {"asset": p["asset"], "direction": "LONG" if p["size"] > 0 else "SHORT"}
                for p in positions
            ]

            await self.notifications.daily_summary(
                balance=balance,
                daily_pnl=daily_pnl,
                daily_pnl_pct=portfolio.daily_pnl_pct,
                trades_today=len(trades),
                wins=wins,
                losses=losses,
                open_positions=open_positions,
            )

            # Save risk snapshot
            await self.db.save_risk_snapshot(
                RiskSnapshot(
                    timestamp=utc_now(),
                    account_balance=balance,
                    total_exposure=portfolio.total_exposure_usd,
                    unrealized_pnl=portfolio.unrealized_pnl,
                    daily_pnl=daily_pnl,
                    weekly_pnl=sum(t.pnl_usd or 0 for t in await self.db.get_trades_since(
                        utc_now() - timedelta(days=7)
                    )),
                    drawdown_from_peak=portfolio.total_drawdown_pct,
                    trades_last_24h=portfolio.trades_last_24h,
                )
            )

        except Exception as e:
            log.error(f"Error sending daily summary: {e}")


async def main() -> None:
    """Main entry point."""
    # Set up logging
    settings = get_settings()
    setup_logging(settings.log_level)

    log.info("=" * 60)
    log.info("INVERSE SENTIMENT AI TRADING SYSTEM")
    log.info("=" * 60)
    log.info(f"Mode: {'PAPER' if settings.paper_trading else 'LIVE'}")
    log.info(f"Network: {'TESTNET' if settings.hyperliquid_testnet else 'MAINNET'}")
    log.info(f"Assets: {', '.join(settings.assets_list)}")
    log.info(f"Analysis Interval: {settings.analysis_interval_hours}h")
    log.info("=" * 60)

    # Create orchestrator
    orchestrator = TradingOrchestrator()

    # Set up signal handlers
    def signal_handler(sig, frame):
        log.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(orchestrator.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start the system
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received")
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())
