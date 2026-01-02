"""Database operations using SQLite."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from src.data.models import (
    AgentAnalysis,
    ConsensusRecord,
    Direction,
    ExitReason,
    LogLevel,
    PortfolioState,
    RiskSnapshot,
    SystemLog,
    Trade,
    TradeStatus,
)
from src.utils.helpers import utc_now


SCHEMA = """
-- Agent analysis records
CREATE TABLE IF NOT EXISTS agent_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    agent_id TEXT NOT NULL,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    reasoning TEXT,
    indicator_data JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Consensus calculations
CREATE TABLE IF NOT EXISTS consensus_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    asset TEXT NOT NULL,
    ta_consensus_direction TEXT NOT NULL,
    our_trade_direction TEXT,
    consensus_strength REAL NOT NULL,
    avg_confidence REAL NOT NULL,
    fade_signal REAL NOT NULL,
    agent_breakdown JSON NOT NULL,
    should_trade BOOLEAN NOT NULL,
    trade_executed BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Trade history
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    consensus_id INTEGER REFERENCES consensus_records(id),
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    entry_time DATETIME NOT NULL,
    exit_price REAL,
    exit_time DATETIME,
    size_usd REAL NOT NULL,
    leverage REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    pnl_usd REAL,
    pnl_pct REAL,
    exit_reason TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    order_ids JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Risk state snapshots
CREATE TABLE IF NOT EXISTS risk_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    account_balance REAL NOT NULL,
    total_exposure REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    daily_pnl REAL NOT NULL,
    weekly_pnl REAL NOT NULL,
    drawdown_from_peak REAL NOT NULL,
    trades_last_24h INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- System logs
CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_agent_analyses_timestamp ON agent_analyses(timestamp);
CREATE INDEX IF NOT EXISTS idx_agent_analyses_asset ON agent_analyses(asset);
CREATE INDEX IF NOT EXISTS idx_consensus_records_timestamp ON consensus_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_consensus_records_asset ON consensus_records(asset);
CREATE INDEX IF NOT EXISTS idx_trades_asset ON trades(asset);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON system_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level);
"""


class Database:
    """Async database operations for the trading system."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Connect to the database and initialize schema."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row

        # Initialize schema
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    # Agent Analysis Methods
    async def save_agent_analysis(self, analysis: AgentAnalysis) -> int:
        """Save an agent analysis record."""
        cursor = await self.conn.execute(
            """
            INSERT INTO agent_analyses (timestamp, agent_id, asset, direction, confidence, reasoning, indicator_data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis.timestamp.isoformat(),
                analysis.agent_id,
                analysis.asset,
                analysis.direction.value,
                analysis.confidence,
                analysis.reasoning,
                json.dumps(analysis.indicator_data),
            ),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_recent_agent_analyses(
        self, asset: str, hours: int = 24
    ) -> list[AgentAnalysis]:
        """Get recent agent analyses for an asset."""
        since = (utc_now() - timedelta(hours=hours)).isoformat()
        cursor = await self.conn.execute(
            """
            SELECT * FROM agent_analyses
            WHERE asset = ? AND timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (asset, since),
        )
        rows = await cursor.fetchall()
        return [self._row_to_agent_analysis(row) for row in rows]

    # Consensus Methods
    async def save_consensus_record(self, record: ConsensusRecord) -> int:
        """Save a consensus record."""
        cursor = await self.conn.execute(
            """
            INSERT INTO consensus_records (
                timestamp, asset, ta_consensus_direction, our_trade_direction,
                consensus_strength, avg_confidence, fade_signal, agent_breakdown,
                should_trade, trade_executed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.timestamp.isoformat(),
                record.asset,
                record.ta_consensus_direction.value,
                record.our_trade_direction.value if record.our_trade_direction else None,
                record.consensus_strength,
                record.avg_confidence,
                record.fade_signal,
                json.dumps(record.agent_breakdown),
                record.should_trade,
                record.trade_executed,
            ),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_latest_consensus(self, asset: str) -> ConsensusRecord | None:
        """Get the latest consensus record for an asset."""
        cursor = await self.conn.execute(
            """
            SELECT * FROM consensus_records
            WHERE asset = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (asset,),
        )
        row = await cursor.fetchone()
        return self._row_to_consensus_record(row) if row else None

    async def mark_consensus_trade_executed(self, consensus_id: int) -> None:
        """Mark a consensus record as having had its trade executed."""
        await self.conn.execute(
            "UPDATE consensus_records SET trade_executed = TRUE WHERE id = ?",
            (consensus_id,),
        )
        await self.conn.commit()

    # Trade Methods
    async def save_trade(self, trade: Trade) -> int:
        """Save a trade record."""
        cursor = await self.conn.execute(
            """
            INSERT INTO trades (
                consensus_id, asset, direction, entry_price, entry_time,
                exit_price, exit_time, size_usd, leverage, stop_loss, take_profit,
                pnl_usd, pnl_pct, exit_reason, status, order_ids
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.consensus_id,
                trade.asset,
                trade.direction.value,
                trade.entry_price,
                trade.entry_time.isoformat(),
                trade.exit_price,
                trade.exit_time.isoformat() if trade.exit_time else None,
                trade.size_usd,
                trade.leverage,
                trade.stop_loss,
                trade.take_profit,
                trade.pnl_usd,
                trade.pnl_pct,
                trade.exit_reason.value if trade.exit_reason else None,
                trade.status.value,
                json.dumps(trade.order_ids),
            ),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def update_trade(self, trade: Trade) -> None:
        """Update an existing trade."""
        if not trade.id:
            raise ValueError("Trade must have an ID to update")

        await self.conn.execute(
            """
            UPDATE trades SET
                exit_price = ?, exit_time = ?, pnl_usd = ?, pnl_pct = ?,
                exit_reason = ?, status = ?, order_ids = ?
            WHERE id = ?
            """,
            (
                trade.exit_price,
                trade.exit_time.isoformat() if trade.exit_time else None,
                trade.pnl_usd,
                trade.pnl_pct,
                trade.exit_reason.value if trade.exit_reason else None,
                trade.status.value,
                json.dumps(trade.order_ids),
                trade.id,
            ),
        )
        await self.conn.commit()

    async def get_open_trades(self, asset: str | None = None) -> list[Trade]:
        """Get all open trades, optionally filtered by asset."""
        if asset:
            cursor = await self.conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' AND asset = ?",
                (asset,),
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN'"
            )
        rows = await cursor.fetchall()
        return [self._row_to_trade(row) for row in rows]

    async def get_trade_by_id(self, trade_id: int) -> Trade | None:
        """Get a trade by its ID."""
        cursor = await self.conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_trade(row) if row else None

    async def get_recent_trades(self, limit: int = 10) -> list[Trade]:
        """Get recent trades."""
        cursor = await self.conn.execute(
            "SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_trade(row) for row in rows]

    async def get_trades_since(self, since: datetime) -> list[Trade]:
        """Get trades since a given datetime."""
        cursor = await self.conn.execute(
            "SELECT * FROM trades WHERE entry_time >= ? ORDER BY entry_time DESC",
            (since.isoformat(),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_trade(row) for row in rows]

    async def count_trades_last_24h(self) -> int:
        """Count trades in the last 24 hours."""
        since = (utc_now() - timedelta(hours=24)).isoformat()
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM trades WHERE entry_time >= ?",
            (since,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_last_trade_time(self) -> datetime | None:
        """Get the time of the last trade."""
        cursor = await self.conn.execute(
            "SELECT entry_time FROM trades ORDER BY entry_time DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc)
        return None

    # Risk Snapshot Methods
    async def save_risk_snapshot(self, snapshot: RiskSnapshot) -> int:
        """Save a risk snapshot."""
        cursor = await self.conn.execute(
            """
            INSERT INTO risk_snapshots (
                timestamp, account_balance, total_exposure, unrealized_pnl,
                daily_pnl, weekly_pnl, drawdown_from_peak, trades_last_24h
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.timestamp.isoformat(),
                snapshot.account_balance,
                snapshot.total_exposure,
                snapshot.unrealized_pnl,
                snapshot.daily_pnl,
                snapshot.weekly_pnl,
                snapshot.drawdown_from_peak,
                snapshot.trades_last_24h,
            ),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_latest_risk_snapshot(self) -> RiskSnapshot | None:
        """Get the latest risk snapshot."""
        cursor = await self.conn.execute(
            "SELECT * FROM risk_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return self._row_to_risk_snapshot(row) if row else None

    async def get_peak_balance(self) -> float:
        """Get the peak account balance."""
        cursor = await self.conn.execute(
            "SELECT MAX(account_balance) FROM risk_snapshots"
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else 0.0

    # System Log Methods
    async def log(
        self,
        level: LogLevel,
        component: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Write a system log entry."""
        await self.conn.execute(
            """
            INSERT INTO system_logs (timestamp, level, component, message, data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                utc_now().isoformat(),
                level.value,
                component,
                message,
                json.dumps(data) if data else None,
            ),
        )
        await self.conn.commit()

    async def get_recent_logs(
        self,
        limit: int = 100,
        level: LogLevel | None = None,
        component: str | None = None,
    ) -> list[SystemLog]:
        """Get recent system logs."""
        query = "SELECT * FROM system_logs WHERE 1=1"
        params: list[Any] = []

        if level:
            query += " AND level = ?"
            params.append(level.value)
        if component:
            query += " AND component = ?"
            params.append(component)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = await self.conn.execute(query, params)
        rows = await cursor.fetchall()
        return [self._row_to_system_log(row) for row in rows]

    # Portfolio State
    async def get_portfolio_state(self, account_balance: float) -> PortfolioState:
        """Calculate the current portfolio state."""
        open_trades = await self.get_open_trades()
        trades_24h = await self.count_trades_last_24h()
        last_trade_time = await self.get_last_trade_time()
        peak_balance = await self.get_peak_balance()

        # Calculate hours since last trade
        if last_trade_time:
            delta = utc_now() - last_trade_time
            hours_since = delta.total_seconds() / 3600
        else:
            hours_since = float("inf")

        # Calculate exposure
        total_exposure = sum(t.size_usd for t in open_trades)

        # Calculate daily and weekly P&L
        daily_since = utc_now() - timedelta(days=1)
        weekly_since = utc_now() - timedelta(days=7)

        daily_trades = await self.get_trades_since(daily_since)
        weekly_trades = await self.get_trades_since(weekly_since)

        daily_pnl = sum(t.pnl_usd or 0 for t in daily_trades if t.status == TradeStatus.CLOSED)
        weekly_pnl = sum(t.pnl_usd or 0 for t in weekly_trades if t.status == TradeStatus.CLOSED)

        # Convert to percentages
        daily_pnl_pct = (daily_pnl / account_balance * 100) if account_balance > 0 else 0
        weekly_pnl_pct = (weekly_pnl / account_balance * 100) if account_balance > 0 else 0

        # Calculate drawdown from peak
        if peak_balance > 0:
            drawdown_pct = ((peak_balance - account_balance) / peak_balance) * 100
        else:
            drawdown_pct = 0

        return PortfolioState(
            account_balance=account_balance,
            total_exposure_usd=total_exposure,
            unrealized_pnl=0,  # This should be updated from exchange data
            daily_pnl_pct=daily_pnl_pct,
            weekly_pnl_pct=weekly_pnl_pct,
            total_drawdown_pct=drawdown_pct,
            trades_last_24h=trades_24h,
            hours_since_last_trade=hours_since,
            open_positions=open_trades,
            peak_balance=peak_balance,
        )

    # Performance Metrics
    async def get_performance_metrics(self) -> dict[str, Any]:
        """Calculate overall performance metrics."""
        cursor = await self.conn.execute(
            """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl_usd < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(pnl_usd) as total_pnl,
                AVG(pnl_pct) as avg_pnl_pct,
                MAX(pnl_usd) as best_trade,
                MIN(pnl_usd) as worst_trade,
                AVG(CASE WHEN pnl_usd > 0 THEN pnl_usd END) as avg_win,
                AVG(CASE WHEN pnl_usd < 0 THEN pnl_usd END) as avg_loss
            FROM trades
            WHERE status = 'CLOSED'
            """
        )
        row = await cursor.fetchone()

        total_trades = row["total_trades"] or 0
        winning = row["winning_trades"] or 0
        losing = row["losing_trades"] or 0

        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
        avg_win = row["avg_win"] or 0
        avg_loss = abs(row["avg_loss"] or 0)
        profit_factor = (avg_win * winning) / (avg_loss * losing) if losing > 0 and avg_loss > 0 else 0

        return {
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": win_rate,
            "total_pnl": row["total_pnl"] or 0,
            "avg_pnl_pct": row["avg_pnl_pct"] or 0,
            "best_trade": row["best_trade"] or 0,
            "worst_trade": row["worst_trade"] or 0,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
        }

    # Helper methods for row conversion
    def _row_to_agent_analysis(self, row: aiosqlite.Row) -> AgentAnalysis:
        """Convert a database row to AgentAnalysis."""
        return AgentAnalysis(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=timezone.utc),
            agent_id=row["agent_id"],
            asset=row["asset"],
            direction=Direction(row["direction"]),
            confidence=row["confidence"],
            reasoning=row["reasoning"],
            indicator_data=json.loads(row["indicator_data"]) if row["indicator_data"] else {},
            created_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc) if row["created_at"] else None,
        )

    def _row_to_consensus_record(self, row: aiosqlite.Row) -> ConsensusRecord:
        """Convert a database row to ConsensusRecord."""
        return ConsensusRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=timezone.utc),
            asset=row["asset"],
            ta_consensus_direction=Direction(row["ta_consensus_direction"]),
            our_trade_direction=Direction(row["our_trade_direction"]) if row["our_trade_direction"] else None,
            consensus_strength=row["consensus_strength"],
            avg_confidence=row["avg_confidence"],
            fade_signal=row["fade_signal"],
            agent_breakdown=json.loads(row["agent_breakdown"]),
            should_trade=bool(row["should_trade"]),
            trade_executed=bool(row["trade_executed"]),
            created_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc) if row["created_at"] else None,
        )

    def _row_to_trade(self, row: aiosqlite.Row) -> Trade:
        """Convert a database row to Trade."""
        return Trade(
            id=row["id"],
            consensus_id=row["consensus_id"],
            asset=row["asset"],
            direction=Direction(row["direction"]),
            entry_price=row["entry_price"],
            entry_time=datetime.fromisoformat(row["entry_time"]).replace(tzinfo=timezone.utc),
            exit_price=row["exit_price"],
            exit_time=datetime.fromisoformat(row["exit_time"]).replace(tzinfo=timezone.utc) if row["exit_time"] else None,
            size_usd=row["size_usd"],
            leverage=row["leverage"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            pnl_usd=row["pnl_usd"],
            pnl_pct=row["pnl_pct"],
            exit_reason=ExitReason(row["exit_reason"]) if row["exit_reason"] else None,
            status=TradeStatus(row["status"]),
            order_ids=json.loads(row["order_ids"]) if row["order_ids"] else [],
            created_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc) if row["created_at"] else None,
        )

    def _row_to_risk_snapshot(self, row: aiosqlite.Row) -> RiskSnapshot:
        """Convert a database row to RiskSnapshot."""
        return RiskSnapshot(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=timezone.utc),
            account_balance=row["account_balance"],
            total_exposure=row["total_exposure"],
            unrealized_pnl=row["unrealized_pnl"],
            daily_pnl=row["daily_pnl"],
            weekly_pnl=row["weekly_pnl"],
            drawdown_from_peak=row["drawdown_from_peak"],
            trades_last_24h=row["trades_last_24h"],
            created_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc) if row["created_at"] else None,
        )

    def _row_to_system_log(self, row: aiosqlite.Row) -> SystemLog:
        """Convert a database row to SystemLog."""
        return SystemLog(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]).replace(tzinfo=timezone.utc),
            level=LogLevel(row["level"]),
            component=row["component"],
            message=row["message"],
            data=json.loads(row["data"]) if row["data"] else {},
            created_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc) if row["created_at"] else None,
        )
