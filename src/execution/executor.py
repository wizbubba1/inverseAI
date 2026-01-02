"""Trade execution logic."""

from datetime import datetime, timezone

from src.config import get_risk_config, get_settings
from src.data.database import Database
from src.data.models import (
    ConsensusRecord,
    Direction,
    ExecutionResult,
    PortfolioState,
    Trade,
    TradeDecision,
    TradeStatus,
)
from src.execution.hyperliquid_client import HyperliquidClient
from src.risk.manager import RiskManager
from src.utils.helpers import utc_now
from src.utils.logging import get_logger

log = get_logger(__name__)


class TradeExecutor:
    """Handles trade execution with risk management.

    Responsibilities:
    - Validate trades through risk manager
    - Calculate position sizes
    - Execute trades on Hyperliquid
    - Set stop loss and take profit orders
    - Track and update positions
    """

    def __init__(
        self,
        exchange: HyperliquidClient,
        risk_manager: RiskManager,
        database: Database,
    ):
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.db = database
        self.settings = get_settings()
        self.risk_config = get_risk_config()

    async def execute_trade(
        self,
        trade_decision: TradeDecision,
        consensus_record: ConsensusRecord,
    ) -> ExecutionResult:
        """Execute a trade based on the consensus decision.

        This is the main entry point for trade execution.
        """
        # 1. Get current portfolio state
        try:
            account_balance = await self.exchange.get_account_balance()
        except Exception as e:
            log.error(f"Failed to get account balance: {e}")
            return ExecutionResult(
                success=False,
                reason=f"Failed to get account balance: {e}",
            )

        portfolio_state = await self.db.get_portfolio_state(account_balance)

        # 2. Calculate position size if not specified
        if trade_decision.size_usd is None:
            trade_decision.size_usd = self._calculate_position_size(
                trade_decision.fade_signal,
                account_balance,
            )

        if trade_decision.leverage is None:
            trade_decision.leverage = self.risk_config.max_leverage

        # 3. Risk manager check
        risk_check = self.risk_manager.check_trade(trade_decision, portfolio_state)

        if not risk_check.approved:
            log.warning(
                "Trade vetoed by risk manager",
                vetoes=risk_check.vetoes,
            )
            return ExecutionResult(
                success=False,
                reason=f"Risk manager veto: {'; '.join(risk_check.vetoes)}",
            )

        # 4. Check if paper trading
        if self.settings.paper_trading:
            return await self._paper_trade(trade_decision, consensus_record)

        # 5. Execute real trade
        return await self._execute_real_trade(trade_decision, consensus_record)

    async def _paper_trade(
        self,
        trade_decision: TradeDecision,
        consensus_record: ConsensusRecord,
    ) -> ExecutionResult:
        """Execute a paper trade (log only, no real execution)."""
        log.info(
            "PAPER TRADE executed",
            asset=trade_decision.asset,
            direction=trade_decision.direction.value,
            size=trade_decision.size_usd,
            leverage=trade_decision.leverage,
            fade_signal=trade_decision.fade_signal,
        )

        # Get current price for the paper trade
        try:
            mids = await self.exchange.get_all_mids()
            entry_price = float(mids.get(trade_decision.asset, 0))
        except Exception:
            entry_price = 0  # Will be filled in later

        # Calculate SL/TP
        stop_loss = self.risk_manager.calculate_stop_loss(
            entry_price, trade_decision.direction
        )
        take_profit = self.risk_manager.calculate_take_profit(
            entry_price, trade_decision.direction
        )

        # Create trade record
        trade = Trade(
            consensus_id=consensus_record.id,
            asset=trade_decision.asset,
            direction=trade_decision.direction,
            entry_price=entry_price,
            entry_time=utc_now(),
            size_usd=trade_decision.size_usd,
            leverage=trade_decision.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status=TradeStatus.OPEN,
            order_ids=["PAPER_TRADE"],
        )

        # Save to database
        trade_id = await self.db.save_trade(trade)
        trade.id = trade_id

        return ExecutionResult(
            success=True,
            reason="Paper trade executed",
            order_id="PAPER_TRADE",
            fill_price=entry_price,
            size=trade_decision.size_usd,
            direction=trade_decision.direction,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trade=trade,
        )

    async def _execute_real_trade(
        self,
        trade_decision: TradeDecision,
        consensus_record: ConsensusRecord,
    ) -> ExecutionResult:
        """Execute a real trade on Hyperliquid."""
        try:
            # Get current price
            mids = await self.exchange.get_all_mids()
            current_price = float(mids.get(trade_decision.asset, 0))

            if current_price == 0:
                return ExecutionResult(
                    success=False,
                    reason=f"Could not get current price for {trade_decision.asset}",
                )

            # Calculate size in asset terms
            asset_size = trade_decision.size_usd / current_price

            # Place main order
            is_buy = trade_decision.direction == Direction.LONG

            order_result = await self.exchange.place_order(
                asset=trade_decision.asset,
                is_buy=is_buy,
                size=asset_size,
                order_type="MARKET",
                leverage=trade_decision.leverage,
            )

            # Get fill price from result
            fill_price = current_price  # May be updated from order result

            # Calculate SL/TP levels
            stop_loss = self.risk_manager.calculate_stop_loss(
                fill_price, trade_decision.direction
            )
            take_profit = self.risk_manager.calculate_take_profit(
                fill_price, trade_decision.direction
            )

            # Place stop loss order
            try:
                sl_result = await self.exchange.place_trigger_order(
                    asset=trade_decision.asset,
                    trigger_price=stop_loss,
                    is_buy=not is_buy,  # Opposite direction
                    size=asset_size,
                    order_type="STOP_MARKET",
                )
            except Exception as e:
                log.error(f"Failed to place stop loss: {e}")
                sl_result = None

            # Place take profit order
            try:
                tp_result = await self.exchange.place_trigger_order(
                    asset=trade_decision.asset,
                    trigger_price=take_profit,
                    is_buy=not is_buy,
                    size=asset_size,
                    order_type="TAKE_PROFIT_MARKET",
                )
            except Exception as e:
                log.error(f"Failed to place take profit: {e}")
                tp_result = None

            # Build order IDs list
            order_ids = [str(order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("resting", {}).get("oid", "UNKNOWN"))]
            if sl_result:
                order_ids.append(f"SL:{stop_loss}")
            if tp_result:
                order_ids.append(f"TP:{take_profit}")

            # Create trade record
            trade = Trade(
                consensus_id=consensus_record.id,
                asset=trade_decision.asset,
                direction=trade_decision.direction,
                entry_price=fill_price,
                entry_time=utc_now(),
                size_usd=trade_decision.size_usd,
                leverage=trade_decision.leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status=TradeStatus.OPEN,
                order_ids=order_ids,
            )

            # Save to database
            trade_id = await self.db.save_trade(trade)
            trade.id = trade_id

            log.info(
                "Trade executed",
                asset=trade_decision.asset,
                direction=trade_decision.direction.value,
                fill_price=fill_price,
                size_usd=trade_decision.size_usd,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            return ExecutionResult(
                success=True,
                reason="Trade executed successfully",
                order_id=order_ids[0],
                fill_price=fill_price,
                size=trade_decision.size_usd,
                direction=trade_decision.direction,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trade=trade,
            )

        except Exception as e:
            log.error(f"Trade execution failed: {e}")
            return ExecutionResult(
                success=False,
                reason=f"Execution failed: {str(e)}",
            )

    def _calculate_position_size(
        self,
        fade_signal: float,
        account_balance: float,
    ) -> float:
        """Calculate position size based on fade signal and account balance."""
        # Base position: 10% of account
        base_pct = 0.10

        # Scale by fade signal strength (60-100 maps to 0.6-1.0 multiplier)
        signal_multiplier = fade_signal / 100

        # Calculate position size
        position_size = account_balance * base_pct * signal_multiplier

        # Apply maximum cap
        return min(position_size, self.risk_config.max_position_size_usd)

    async def close_trade(
        self,
        trade: Trade,
        exit_reason: str,
        exit_price: float | None = None,
    ) -> ExecutionResult:
        """Close an existing trade."""
        if trade.status != TradeStatus.OPEN:
            return ExecutionResult(
                success=False,
                reason=f"Trade is not open (status: {trade.status.value})",
            )

        try:
            # Get current price if not provided
            if exit_price is None:
                mids = await self.exchange.get_all_mids()
                exit_price = float(mids.get(trade.asset, 0))

            # Close position on exchange
            if not self.settings.paper_trading:
                await self.exchange.close_position(trade.asset)

            # Calculate P&L
            if trade.direction == Direction.LONG:
                pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
            else:
                pnl_pct = ((trade.entry_price - exit_price) / trade.entry_price) * 100

            # Account for leverage
            pnl_pct *= trade.leverage
            pnl_usd = trade.size_usd * (pnl_pct / 100)

            # Update trade record
            trade.exit_price = exit_price
            trade.exit_time = utc_now()
            trade.pnl_usd = pnl_usd
            trade.pnl_pct = pnl_pct
            trade.exit_reason = exit_reason
            trade.status = TradeStatus.CLOSED

            await self.db.update_trade(trade)

            log.info(
                "Trade closed",
                asset=trade.asset,
                direction=trade.direction.value,
                entry=trade.entry_price,
                exit=exit_price,
                pnl_usd=f"${pnl_usd:.2f}",
                pnl_pct=f"{pnl_pct:.2f}%",
                reason=exit_reason,
            )

            return ExecutionResult(
                success=True,
                reason=f"Trade closed: {exit_reason}",
                fill_price=exit_price,
                trade=trade,
            )

        except Exception as e:
            log.error(f"Failed to close trade: {e}")
            return ExecutionResult(
                success=False,
                reason=f"Failed to close trade: {str(e)}",
            )

    async def update_trailing_stops(self) -> None:
        """Check and update trailing stops for open positions."""
        open_trades = await self.db.get_open_trades()

        for trade in open_trades:
            try:
                # Get current price
                mids = await self.exchange.get_all_mids()
                current_price = float(mids.get(trade.asset, 0))

                if current_price == 0:
                    continue

                # Calculate new trailing stop
                new_stop = self.risk_manager.calculate_trailing_stop(
                    trade.entry_price,
                    current_price,
                    trade.direction,
                    trade.stop_loss,
                )

                if new_stop is not None:
                    # Update stop loss
                    log.info(
                        "Updating trailing stop",
                        asset=trade.asset,
                        old_stop=trade.stop_loss,
                        new_stop=new_stop,
                        current_price=current_price,
                    )

                    # Update on exchange if not paper trading
                    if not self.settings.paper_trading:
                        # Cancel old stop and place new one
                        await self.exchange.cancel_all_orders(trade.asset)

                        asset_size = trade.size_usd / trade.entry_price
                        is_buy = trade.direction == Direction.SHORT

                        await self.exchange.place_trigger_order(
                            asset=trade.asset,
                            trigger_price=new_stop,
                            is_buy=is_buy,
                            size=asset_size,
                            order_type="STOP_MARKET",
                        )

                    # Update trade record
                    trade.stop_loss = new_stop
                    await self.db.update_trade(trade)

            except Exception as e:
                log.error(f"Error updating trailing stop for {trade.asset}: {e}")

    async def check_position_exits(self) -> list[Trade]:
        """Check if any positions should be closed based on SL/TP.

        For paper trading, we need to check manually.
        For real trading, Hyperliquid handles this via trigger orders.
        """
        if not self.settings.paper_trading:
            return []  # Exchange handles exits

        closed_trades = []
        open_trades = await self.db.get_open_trades()

        for trade in open_trades:
            try:
                mids = await self.exchange.get_all_mids()
                current_price = float(mids.get(trade.asset, 0))

                if current_price == 0:
                    continue

                # Check stop loss
                if trade.direction == Direction.LONG:
                    if current_price <= trade.stop_loss:
                        result = await self.close_trade(trade, "STOP_LOSS", current_price)
                        if result.success:
                            closed_trades.append(trade)
                    elif current_price >= trade.take_profit:
                        result = await self.close_trade(trade, "TAKE_PROFIT", current_price)
                        if result.success:
                            closed_trades.append(trade)
                else:  # SHORT
                    if current_price >= trade.stop_loss:
                        result = await self.close_trade(trade, "STOP_LOSS", current_price)
                        if result.success:
                            closed_trades.append(trade)
                    elif current_price <= trade.take_profit:
                        result = await self.close_trade(trade, "TAKE_PROFIT", current_price)
                        if result.success:
                            closed_trades.append(trade)

            except Exception as e:
                log.error(f"Error checking exit for {trade.asset}: {e}")

        return closed_trades
