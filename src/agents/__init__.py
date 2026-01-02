"""Technical Analysis Agent Swarm."""

from src.agents.base_agent import BaseAgent
from src.agents.rsi_agent import RSIAgent
from src.agents.ma_crossover_agent import MACrossoverAgent
from src.agents.support_resistance_agent import SupportResistanceAgent
from src.agents.macd_agent import MACDAgent
from src.agents.bollinger_agent import BollingerAgent
from src.agents.volume_profile_agent import VolumeProfileAgent
from src.agents.fibonacci_agent import FibonacciAgent
from src.agents.trendline_agent import TrendlineAgent
from src.agents.ichimoku_agent import IchimokuAgent
from src.agents.chart_pattern_agent import ChartPatternAgent

__all__ = [
    "BaseAgent",
    "RSIAgent",
    "MACrossoverAgent",
    "SupportResistanceAgent",
    "MACDAgent",
    "BollingerAgent",
    "VolumeProfileAgent",
    "FibonacciAgent",
    "TrendlineAgent",
    "IchimokuAgent",
    "ChartPatternAgent",
]


def create_all_agents() -> list[BaseAgent]:
    """Create all 10 TA agents."""
    return [
        RSIAgent(),
        MACrossoverAgent(),
        SupportResistanceAgent(),
        MACDAgent(),
        BollingerAgent(),
        VolumeProfileAgent(),
        FibonacciAgent(),
        TrendlineAgent(),
        IchimokuAgent(),
        ChartPatternAgent(),
    ]
