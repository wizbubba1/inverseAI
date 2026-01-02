"""Configuration management for the Inverse Sentiment Trading System."""

from pathlib import Path
from typing import List

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RiskConfig(BaseSettings):
    """Risk management configuration."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # Position Limits
    max_position_size_usd: float = Field(default=1000, description="Maximum single position size")
    max_total_exposure_usd: float = Field(default=2000, description="Maximum total exposure across all positions")
    max_leverage: float = Field(default=5, description="Maximum leverage")

    # Drawdown Limits
    max_daily_drawdown_pct: float = Field(default=5, description="Pause trading if down this % in a day")
    max_weekly_drawdown_pct: float = Field(default=15, description="Pause trading if down this % in a week")
    max_total_drawdown_pct: float = Field(default=30, description="STOP trading if down this % from peak")

    # Trade Limits
    max_trades_per_day: int = Field(default=2, description="Maximum trades in 24h period")
    min_time_between_trades_hours: float = Field(default=4, description="Minimum hours between trades")
    min_hold_time_hours: float = Field(default=2, description="Minimum position hold time")

    # Stop Loss / Take Profit
    default_stop_loss_pct: float = Field(default=3, description="Default stop loss percentage")
    default_take_profit_pct: float = Field(default=6, description="Default take profit percentage")
    trailing_stop_enabled: bool = Field(default=True, description="Enable trailing stops")
    trailing_stop_activation_pct: float = Field(default=3, description="Activate trailing stop after this % profit")
    trailing_stop_distance_pct: float = Field(default=1.5, description="Trail by this percentage")


class ConsensusConfig(BaseSettings):
    """Consensus engine configuration."""

    model_config = SettingsConfigDict(env_prefix="CONSENSUS_", extra="ignore")

    min_agreement_pct: float = Field(default=0.8, description="Minimum agreement percentage (80%)")
    min_confidence: float = Field(default=0.6, description="Minimum average confidence (60%)")
    min_fade_signal: float = Field(default=60, description="Minimum fade signal strength (0-100)")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # API Keys
    openrouter_api_key: SecretStr = Field(description="OpenRouter API key for LLM access")
    discord_bot_token: SecretStr = Field(description="Discord bot token")
    discord_channel_id: str = Field(description="Discord channel ID for notifications")
    discord_admin_user_ids: str = Field(default="", description="Comma-separated admin user IDs")

    # Hyperliquid
    hyperliquid_private_key: SecretStr = Field(description="Wallet private key for Hyperliquid")
    hyperliquid_testnet: bool = Field(default=True, description="Use Hyperliquid testnet")

    # Configuration
    analysis_interval_hours: float = Field(default=4, description="Hours between analysis cycles")
    assets_to_trade: str = Field(default="BTC,ETH,SOL", description="Comma-separated assets to trade")
    log_level: str = Field(default="INFO", description="Logging level")
    database_path: str = Field(default="data/trader.db", description="SQLite database path")

    # LLM Configuration (OpenRouter)
    llm_model: str = Field(default="anthropic/claude-sonnet-4", description="OpenRouter model ID for TA agents")
    llm_max_tokens: int = Field(default=1024, description="Max tokens for LLM responses")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", description="OpenRouter API base URL")

    # Paper trading mode
    paper_trading: bool = Field(default=True, description="Enable paper trading (no real trades)")

    @property
    def assets_list(self) -> List[str]:
        """Get assets as a list."""
        return [a.strip().upper() for a in self.assets_to_trade.split(",") if a.strip()]

    @property
    def admin_ids(self) -> List[str]:
        """Get admin user IDs as a list."""
        if not self.discord_admin_user_ids:
            return []
        return [uid.strip() for uid in self.discord_admin_user_ids.split(",") if uid.strip()]

    @property
    def db_path(self) -> Path:
        """Get database path as Path object."""
        return Path(self.database_path)


# Global instances - lazy loaded
_settings: Settings | None = None
_risk_config: RiskConfig | None = None
_consensus_config: ConsensusConfig | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_risk_config() -> RiskConfig:
    """Get the global risk config instance."""
    global _risk_config
    if _risk_config is None:
        _risk_config = RiskConfig()
    return _risk_config


def get_consensus_config() -> ConsensusConfig:
    """Get the global consensus config instance."""
    global _consensus_config
    if _consensus_config is None:
        _consensus_config = ConsensusConfig()
    return _consensus_config
