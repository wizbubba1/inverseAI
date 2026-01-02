"""Data models for the trading system."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Direction(str, Enum):
    """Trading direction."""

    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


class TradeStatus(str, Enum):
    """Trade status."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ExitReason(str, Enum):
    """Reason for trade exit."""

    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    MANUAL = "MANUAL"
    SIGNAL_FLIP = "SIGNAL_FLIP"
    TRAILING_STOP = "TRAILING_STOP"
    RISK_LIMIT = "RISK_LIMIT"


class LogLevel(str, Enum):
    """Log level."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AgentOutput(BaseModel):
    """Output from a TA agent."""

    agent_id: str
    asset: str
    timestamp: datetime
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    key_levels: dict[str, float] = Field(default_factory=dict)
    indicators: dict[str, Any] = Field(default_factory=dict)


class AgentAnalysis(BaseModel):
    """Record of an agent's analysis in the database."""

    id: int | None = None
    timestamp: datetime
    agent_id: str
    asset: str
    direction: Direction
    confidence: float
    reasoning: str | None = None
    indicator_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ConsensusResult(BaseModel):
    """Result of consensus calculation."""

    should_trade: bool
    reason: str = ""
    ta_consensus_direction: Direction | None = None
    our_trade_direction: Direction | None = None
    consensus_strength: float = 0.0
    avg_confidence: float = 0.0
    fade_signal: float = 0.0
    agent_breakdown: dict[str, int] = Field(default_factory=dict)


class ConsensusRecord(BaseModel):
    """Record of a consensus calculation in the database."""

    id: int | None = None
    timestamp: datetime
    asset: str
    ta_consensus_direction: Direction
    our_trade_direction: Direction | None = None
    consensus_strength: float
    avg_confidence: float
    fade_signal: float
    agent_breakdown: dict[str, int]
    should_trade: bool
    trade_executed: bool = False
    created_at: datetime | None = None


class Trade(BaseModel):
    """Trade record."""

    id: int | None = None
    consensus_id: int | None = None
    asset: str
    direction: Direction
    entry_price: float
    entry_time: datetime
    exit_price: float | None = None
    exit_time: datetime | None = None
    size_usd: float
    leverage: float
    stop_loss: float
    take_profit: float
    pnl_usd: float | None = None
    pnl_pct: float | None = None
    exit_reason: ExitReason | None = None
    status: TradeStatus = TradeStatus.OPEN
    order_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class RiskSnapshot(BaseModel):
    """Snapshot of risk state."""

    id: int | None = None
    timestamp: datetime
    account_balance: float
    total_exposure: float
    unrealized_pnl: float
    daily_pnl: float
    weekly_pnl: float
    drawdown_from_peak: float
    trades_last_24h: int
    created_at: datetime | None = None


class SystemLog(BaseModel):
    """System log entry."""

    id: int | None = None
    timestamp: datetime
    level: LogLevel
    component: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class PortfolioState(BaseModel):
    """Current state of the portfolio for risk checking."""

    account_balance: float
    total_exposure_usd: float
    unrealized_pnl: float
    daily_pnl_pct: float
    weekly_pnl_pct: float
    total_drawdown_pct: float
    trades_last_24h: int
    hours_since_last_trade: float
    open_positions: list[Trade] = Field(default_factory=list)
    peak_balance: float = 0.0


class TradeDecision(BaseModel):
    """Decision to execute a trade."""

    asset: str
    direction: Direction
    fade_signal: float
    consensus: ConsensusResult
    size_usd: float | None = None
    leverage: float | None = None


class RiskDecision(BaseModel):
    """Result of risk manager evaluation."""

    approved: bool
    vetoes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Result of trade execution."""

    success: bool
    reason: str = ""
    order_id: str | None = None
    fill_price: float | None = None
    size: float | None = None
    direction: Direction | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    trade: Trade | None = None
