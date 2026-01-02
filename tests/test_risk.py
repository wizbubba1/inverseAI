"""Tests for the risk manager."""

import pytest
from datetime import datetime, timezone

from src.data.models import (
    Direction,
    PortfolioState,
    Trade,
    TradeDecision,
    TradeStatus,
    ConsensusResult,
)
from src.risk.manager import RiskManager


@pytest.fixture
def risk_manager():
    """Create a risk manager for testing."""
    return RiskManager()


@pytest.fixture
def healthy_portfolio():
    """Create a healthy portfolio state for testing."""
    return PortfolioState(
        account_balance=10000,
        total_exposure_usd=0,
        unrealized_pnl=0,
        daily_pnl_pct=0,
        weekly_pnl_pct=0,
        total_drawdown_pct=0,
        trades_last_24h=0,
        hours_since_last_trade=24,
        open_positions=[],
        peak_balance=10000,
    )


@pytest.fixture
def sample_trade_decision():
    """Create a sample trade decision."""
    return TradeDecision(
        asset="BTC",
        direction=Direction.LONG,
        fade_signal=75,
        consensus=ConsensusResult(
            should_trade=True,
            ta_consensus_direction=Direction.SHORT,
            our_trade_direction=Direction.LONG,
            consensus_strength=0.85,
            avg_confidence=0.75,
            fade_signal=75,
            agent_breakdown={"long": 2, "short": 8, "neutral": 0},
        ),
        size_usd=500,
        leverage=5,
    )


class TestRiskManagerBasics:
    """Basic risk manager tests."""

    def test_healthy_trade_approved(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that a healthy trade is approved."""
        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)
        assert result.approved is True
        assert len(result.vetoes) == 0

    def test_paused_trading_vetoes(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that paused trading vetoes all trades."""
        risk_manager.pause_trading("Manual pause")

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("paused" in v.lower() for v in result.vetoes)

    def test_resume_trading(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that resuming allows trades again."""
        risk_manager.pause_trading("Manual pause")
        risk_manager.resume_trading()

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is True


class TestDrawdownLimits:
    """Tests for drawdown limits."""

    def test_daily_drawdown_vetoes(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that exceeding daily drawdown limit vetoes trade."""
        healthy_portfolio.daily_pnl_pct = -6  # Exceeds -5% limit

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("daily drawdown" in v.lower() for v in result.vetoes)

    def test_weekly_drawdown_vetoes(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that exceeding weekly drawdown limit vetoes trade."""
        healthy_portfolio.weekly_pnl_pct = -16  # Exceeds -15% limit

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("weekly drawdown" in v.lower() for v in result.vetoes)

    def test_total_drawdown_vetoes(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that exceeding total drawdown limit vetoes trade."""
        healthy_portfolio.total_drawdown_pct = 31  # Exceeds 30% limit

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("total drawdown" in v.lower() for v in result.vetoes)

    def test_near_daily_limit_warns(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that approaching daily limit gives warning but allows trade."""
        healthy_portfolio.daily_pnl_pct = -4.5  # 90% of limit, still under

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is True
        assert any("approaching daily" in w.lower() for w in result.warnings)


class TestPositionLimits:
    """Tests for position size limits."""

    def test_position_size_exceeds_limit(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that position size exceeding limit is vetoed."""
        sample_trade_decision.size_usd = 2000  # Exceeds $1000 limit

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("position size" in v.lower() for v in result.vetoes)

    def test_total_exposure_exceeds_limit(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that total exposure exceeding limit is vetoed."""
        healthy_portfolio.total_exposure_usd = 1800  # Already at 1800
        sample_trade_decision.size_usd = 500  # Would bring to 2300, exceeds 2000

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("total exposure" in v.lower() for v in result.vetoes)

    def test_leverage_exceeds_limit(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that leverage exceeding limit is vetoed."""
        sample_trade_decision.leverage = 10  # Exceeds 5x limit

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("leverage" in v.lower() for v in result.vetoes)


class TestTradeFrequencyLimits:
    """Tests for trade frequency limits."""

    def test_max_trades_per_day_vetoes(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that exceeding max trades per day is vetoed."""
        healthy_portfolio.trades_last_24h = 2  # At limit

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("trade limit" in v.lower() for v in result.vetoes)

    def test_min_time_between_trades_vetoes(self, risk_manager, healthy_portfolio, sample_trade_decision):
        """Test that trading too soon after last trade is vetoed."""
        healthy_portfolio.hours_since_last_trade = 2  # Less than 4h minimum

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert result.approved is False
        assert any("too soon" in v.lower() for v in result.vetoes)


class TestStopLossTakeProfit:
    """Tests for SL/TP calculations."""

    def test_long_stop_loss(self, risk_manager):
        """Test stop loss calculation for long position."""
        entry = 100
        sl = risk_manager.calculate_stop_loss(entry, Direction.LONG)

        # 3% below entry
        assert sl == pytest.approx(97, rel=0.01)

    def test_short_stop_loss(self, risk_manager):
        """Test stop loss calculation for short position."""
        entry = 100
        sl = risk_manager.calculate_stop_loss(entry, Direction.SHORT)

        # 3% above entry
        assert sl == pytest.approx(103, rel=0.01)

    def test_long_take_profit(self, risk_manager):
        """Test take profit calculation for long position."""
        entry = 100
        tp = risk_manager.calculate_take_profit(entry, Direction.LONG)

        # 6% above entry
        assert tp == pytest.approx(106, rel=0.01)

    def test_short_take_profit(self, risk_manager):
        """Test take profit calculation for short position."""
        entry = 100
        tp = risk_manager.calculate_take_profit(entry, Direction.SHORT)

        # 6% below entry
        assert tp == pytest.approx(94, rel=0.01)


class TestTrailingStop:
    """Tests for trailing stop calculations."""

    def test_trailing_stop_not_activated_below_threshold(self, risk_manager):
        """Test that trailing stop is not activated below profit threshold."""
        result = risk_manager.calculate_trailing_stop(
            entry_price=100,
            current_price=101,  # Only 1% profit, need 3%
            direction=Direction.LONG,
            current_stop=97,
        )

        assert result is None

    def test_trailing_stop_activated_for_long(self, risk_manager):
        """Test trailing stop activation for profitable long position."""
        result = risk_manager.calculate_trailing_stop(
            entry_price=100,
            current_price=105,  # 5% profit, above 3% threshold
            direction=Direction.LONG,
            current_stop=97,
        )

        # New stop should be 1.5% below current price = 103.425
        assert result is not None
        assert result > 97  # Higher than original stop
        assert result == pytest.approx(103.425, rel=0.01)

    def test_trailing_stop_activated_for_short(self, risk_manager):
        """Test trailing stop activation for profitable short position."""
        result = risk_manager.calculate_trailing_stop(
            entry_price=100,
            current_price=95,  # 5% profit (price dropped)
            direction=Direction.SHORT,
            current_stop=103,
        )

        # New stop should be 1.5% above current price = 96.425
        assert result is not None
        assert result < 103  # Lower than original stop
        assert result == pytest.approx(96.425, rel=0.01)

    def test_trailing_stop_only_moves_in_favor(self, risk_manager):
        """Test that trailing stop doesn't move against the position."""
        # For long, if new calculated stop is lower than current, don't update
        result = risk_manager.calculate_trailing_stop(
            entry_price=100,
            current_price=104,  # 4% profit
            direction=Direction.LONG,
            current_stop=103,  # Current stop already high
        )

        # New stop would be 102.44, but current is 103, so no update
        assert result is None


class TestPositionConflicts:
    """Tests for position conflict detection."""

    def test_adding_to_same_direction_warns(
        self, risk_manager, healthy_portfolio, sample_trade_decision
    ):
        """Test that adding to existing position in same direction gives warning."""
        healthy_portfolio.open_positions = [
            Trade(
                asset="BTC",
                direction=Direction.LONG,
                entry_price=50000,
                entry_time=datetime.now(timezone.utc),
                size_usd=500,
                leverage=5,
                stop_loss=48500,
                take_profit=53000,
                status=TradeStatus.OPEN,
            )
        ]

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert any("adding to existing" in w.lower() for w in result.warnings)

    def test_flipping_position_warns(
        self, risk_manager, healthy_portfolio, sample_trade_decision
    ):
        """Test that flipping position direction gives warning."""
        healthy_portfolio.open_positions = [
            Trade(
                asset="BTC",
                direction=Direction.SHORT,  # Opposite of proposed LONG
                entry_price=50000,
                entry_time=datetime.now(timezone.utc),
                size_usd=500,
                leverage=5,
                stop_loss=51500,
                take_profit=47000,
                status=TradeStatus.OPEN,
            )
        ]

        result = risk_manager.check_trade(sample_trade_decision, healthy_portfolio)

        assert any("flip" in w.lower() for w in result.warnings)
