"""Risk Manager with veto power over all trades."""

from src.config import get_risk_config
from src.data.models import (
    Direction,
    PortfolioState,
    RiskDecision,
    Trade,
    TradeDecision,
)
from src.utils.logging import get_logger

log = get_logger(__name__)


class RiskManager:
    """Risk Manager with VETO POWER over all trades.

    The Risk Manager runs independently and can block any trade,
    regardless of how strong the consensus signal is.

    Key responsibilities:
    - Enforce position size limits
    - Monitor drawdown and pause trading when limits hit
    - Limit trade frequency
    - Validate leverage levels
    - Track overall portfolio risk
    """

    def __init__(self):
        self.config = get_risk_config()
        self._trading_paused = False
        self._pause_reason: str | None = None

    @property
    def is_paused(self) -> bool:
        """Check if trading is paused."""
        return self._trading_paused

    @property
    def pause_reason(self) -> str | None:
        """Get the reason for pause if paused."""
        return self._pause_reason

    def pause_trading(self, reason: str) -> None:
        """Pause trading with a reason."""
        self._trading_paused = True
        self._pause_reason = reason
        log.warning("Trading PAUSED", reason=reason)

    def resume_trading(self) -> None:
        """Resume trading."""
        self._trading_paused = False
        self._pause_reason = None
        log.info("Trading RESUMED")

    def check_trade(
        self,
        proposed_trade: TradeDecision,
        portfolio_state: PortfolioState,
    ) -> RiskDecision:
        """Check if a proposed trade passes all risk checks.

        Returns a RiskDecision with:
        - approved: Whether the trade is allowed
        - vetoes: List of reasons if rejected
        - warnings: List of warnings (trade still allowed)
        """
        vetoes: list[str] = []
        warnings: list[str] = []

        # Check if trading is paused
        if self._trading_paused:
            vetoes.append(f"Trading is paused: {self._pause_reason}")
            return RiskDecision(approved=False, vetoes=vetoes, warnings=warnings)

        # Calculate proposed position size
        proposed_size = proposed_trade.size_usd or self._calculate_position_size(
            proposed_trade.fade_signal, portfolio_state.account_balance
        )
        proposed_leverage = proposed_trade.leverage or self.config.max_leverage

        # 1. Check drawdown limits
        self._check_drawdown_limits(portfolio_state, vetoes, warnings)

        # 2. Check position size limits
        if proposed_size > self.config.max_position_size_usd:
            vetoes.append(
                f"Position size ${proposed_size:.2f} exceeds max ${self.config.max_position_size_usd:.2f}"
            )

        # 3. Check total exposure limits
        new_exposure = portfolio_state.total_exposure_usd + proposed_size
        if new_exposure > self.config.max_total_exposure_usd:
            vetoes.append(
                f"Total exposure ${new_exposure:.2f} would exceed max ${self.config.max_total_exposure_usd:.2f}"
            )

        # 4. Check leverage limit
        if proposed_leverage > self.config.max_leverage:
            vetoes.append(
                f"Leverage {proposed_leverage}x exceeds max {self.config.max_leverage}x"
            )

        # 5. Check trade frequency
        if portfolio_state.trades_last_24h >= self.config.max_trades_per_day:
            vetoes.append(
                f"Trade limit reached: {portfolio_state.trades_last_24h} trades in last 24h "
                f"(max: {self.config.max_trades_per_day})"
            )

        # 6. Check time since last trade
        hours_since = portfolio_state.hours_since_last_trade
        if hours_since < self.config.min_time_between_trades_hours:
            vetoes.append(
                f"Too soon since last trade: {hours_since:.1f}h "
                f"(min: {self.config.min_time_between_trades_hours}h)"
            )

        # 7. Check for conflicting positions
        self._check_position_conflicts(
            proposed_trade, portfolio_state.open_positions, vetoes, warnings
        )

        # Log the decision
        if vetoes:
            log.warning(
                "Trade VETOED",
                asset=proposed_trade.asset,
                direction=proposed_trade.direction.value,
                vetoes=vetoes,
            )
            return RiskDecision(approved=False, vetoes=vetoes, warnings=warnings)

        if warnings:
            log.info(
                "Trade approved with warnings",
                asset=proposed_trade.asset,
                direction=proposed_trade.direction.value,
                warnings=warnings,
            )
        else:
            log.info(
                "Trade approved",
                asset=proposed_trade.asset,
                direction=proposed_trade.direction.value,
            )

        return RiskDecision(approved=True, vetoes=[], warnings=warnings)

    def _check_drawdown_limits(
        self,
        state: PortfolioState,
        vetoes: list[str],
        warnings: list[str],
    ) -> None:
        """Check drawdown limits and add vetoes/warnings as needed."""
        # Daily drawdown
        if state.daily_pnl_pct <= -self.config.max_daily_drawdown_pct:
            vetoes.append(
                f"Daily drawdown limit hit: {state.daily_pnl_pct:.2f}% "
                f"(limit: -{self.config.max_daily_drawdown_pct}%)"
            )
            self.pause_trading(f"Daily drawdown limit: {state.daily_pnl_pct:.2f}%")
        elif state.daily_pnl_pct <= -self.config.max_daily_drawdown_pct * 0.8:
            warnings.append(
                f"Approaching daily drawdown limit: {state.daily_pnl_pct:.2f}%"
            )

        # Weekly drawdown
        if state.weekly_pnl_pct <= -self.config.max_weekly_drawdown_pct:
            vetoes.append(
                f"Weekly drawdown limit hit: {state.weekly_pnl_pct:.2f}% "
                f"(limit: -{self.config.max_weekly_drawdown_pct}%)"
            )
            self.pause_trading(f"Weekly drawdown limit: {state.weekly_pnl_pct:.2f}%")
        elif state.weekly_pnl_pct <= -self.config.max_weekly_drawdown_pct * 0.8:
            warnings.append(
                f"Approaching weekly drawdown limit: {state.weekly_pnl_pct:.2f}%"
            )

        # Total drawdown from peak
        if state.total_drawdown_pct >= self.config.max_total_drawdown_pct:
            vetoes.append(
                f"CRITICAL: Total drawdown limit hit: {state.total_drawdown_pct:.2f}% "
                f"(limit: {self.config.max_total_drawdown_pct}%)"
            )
            self.pause_trading(
                f"CRITICAL: Total drawdown from peak: {state.total_drawdown_pct:.2f}%"
            )

    def _check_position_conflicts(
        self,
        proposed: TradeDecision,
        open_positions: list[Trade],
        vetoes: list[str],
        warnings: list[str],
    ) -> None:
        """Check for conflicts with existing positions."""
        for position in open_positions:
            if position.asset == proposed.asset:
                if position.direction == proposed.direction:
                    # Adding to existing position in same direction
                    warnings.append(
                        f"Adding to existing {position.direction.value} position in {position.asset}"
                    )
                else:
                    # Flipping position - this is allowed but noted
                    warnings.append(
                        f"This will flip the position from {position.direction.value} to {proposed.direction.value}"
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
        return min(position_size, self.config.max_position_size_usd)

    def calculate_stop_loss(
        self,
        entry_price: float,
        direction: Direction,
    ) -> float:
        """Calculate stop loss price."""
        if direction == Direction.LONG:
            return entry_price * (1 - self.config.default_stop_loss_pct / 100)
        else:  # SHORT
            return entry_price * (1 + self.config.default_stop_loss_pct / 100)

    def calculate_take_profit(
        self,
        entry_price: float,
        direction: Direction,
    ) -> float:
        """Calculate take profit price."""
        if direction == Direction.LONG:
            return entry_price * (1 + self.config.default_take_profit_pct / 100)
        else:  # SHORT
            return entry_price * (1 - self.config.default_take_profit_pct / 100)

    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        direction: Direction,
        current_stop: float,
    ) -> float | None:
        """Calculate trailing stop if conditions are met.

        Returns new stop price if trailing stop should be updated, None otherwise.
        """
        if not self.config.trailing_stop_enabled:
            return None

        # Calculate current profit percentage
        if direction == Direction.LONG:
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100

        # Check if trailing stop should be activated
        if profit_pct < self.config.trailing_stop_activation_pct:
            return None

        # Calculate new trailing stop
        if direction == Direction.LONG:
            new_stop = current_price * (1 - self.config.trailing_stop_distance_pct / 100)
            # Only update if new stop is higher than current
            if new_stop > current_stop:
                return new_stop
        else:
            new_stop = current_price * (1 + self.config.trailing_stop_distance_pct / 100)
            # Only update if new stop is lower than current
            if new_stop < current_stop:
                return new_stop

        return None

    def get_status(self, portfolio_state: PortfolioState) -> dict:
        """Get current risk manager status."""
        return {
            "trading_paused": self._trading_paused,
            "pause_reason": self._pause_reason,
            "daily_pnl_pct": portfolio_state.daily_pnl_pct,
            "weekly_pnl_pct": portfolio_state.weekly_pnl_pct,
            "total_drawdown_pct": portfolio_state.total_drawdown_pct,
            "trades_last_24h": portfolio_state.trades_last_24h,
            "total_exposure_usd": portfolio_state.total_exposure_usd,
            "open_positions": len(portfolio_state.open_positions),
            "limits": {
                "max_position_size_usd": self.config.max_position_size_usd,
                "max_total_exposure_usd": self.config.max_total_exposure_usd,
                "max_leverage": self.config.max_leverage,
                "max_daily_drawdown_pct": self.config.max_daily_drawdown_pct,
                "max_weekly_drawdown_pct": self.config.max_weekly_drawdown_pct,
                "max_total_drawdown_pct": self.config.max_total_drawdown_pct,
                "max_trades_per_day": self.config.max_trades_per_day,
            },
        }
