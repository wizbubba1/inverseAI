"""Tests for the consensus engine."""

import pytest
from datetime import datetime, timezone

from src.consensus.engine import ConsensusEngine
from src.data.models import AgentOutput, Direction


@pytest.fixture
def consensus_engine():
    """Create a consensus engine for testing."""
    return ConsensusEngine()


def create_agent_output(
    agent_id: str,
    direction: Direction,
    confidence: float = 0.7,
) -> AgentOutput:
    """Helper to create agent outputs for testing."""
    return AgentOutput(
        agent_id=agent_id,
        asset="BTC",
        timestamp=datetime.now(timezone.utc),
        direction=direction,
        confidence=confidence,
        reasoning="Test reasoning",
        key_levels={},
        indicators={},
    )


class TestConsensusEngine:
    """Test cases for ConsensusEngine."""

    def test_no_agents_returns_no_trade(self, consensus_engine):
        """Test that empty agent list returns no trade signal."""
        result = consensus_engine.calculate([])
        assert result.should_trade is False
        assert "No agent outputs" in result.reason

    def test_all_neutral_returns_no_trade(self, consensus_engine):
        """Test that all neutral agents returns no trade signal."""
        agents = [
            create_agent_output(f"agent_{i}", Direction.NEUTRAL)
            for i in range(10)
        ]
        result = consensus_engine.calculate(agents)
        assert result.should_trade is False
        assert "All agents neutral" in result.reason

    def test_strong_long_consensus_triggers_short_trade(self, consensus_engine):
        """Test that 80%+ LONG consensus triggers SHORT trade (inverse)."""
        agents = [
            create_agent_output(f"agent_{i}", Direction.LONG, 0.8)
            for i in range(8)
        ]
        agents.extend([
            create_agent_output(f"agent_{i}", Direction.SHORT, 0.6)
            for i in range(8, 10)
        ])

        result = consensus_engine.calculate(agents)

        assert result.should_trade is True
        assert result.ta_consensus_direction == Direction.LONG
        assert result.our_trade_direction == Direction.SHORT
        assert result.consensus_strength >= 0.8

    def test_strong_short_consensus_triggers_long_trade(self, consensus_engine):
        """Test that 80%+ SHORT consensus triggers LONG trade (inverse)."""
        agents = [
            create_agent_output(f"agent_{i}", Direction.SHORT, 0.8)
            for i in range(8)
        ]
        agents.extend([
            create_agent_output(f"agent_{i}", Direction.LONG, 0.6)
            for i in range(8, 10)
        ])

        result = consensus_engine.calculate(agents)

        assert result.should_trade is True
        assert result.ta_consensus_direction == Direction.SHORT
        assert result.our_trade_direction == Direction.LONG
        assert result.consensus_strength >= 0.8

    def test_weak_consensus_no_trade(self, consensus_engine):
        """Test that 60% agreement does not trigger trade."""
        agents = [
            create_agent_output(f"agent_{i}", Direction.LONG, 0.8)
            for i in range(6)
        ]
        agents.extend([
            create_agent_output(f"agent_{i}", Direction.SHORT, 0.8)
            for i in range(6, 10)
        ])

        result = consensus_engine.calculate(agents)

        assert result.should_trade is False
        assert "No strong consensus" in result.reason

    def test_low_confidence_no_trade(self, consensus_engine):
        """Test that high agreement but low confidence does not trigger trade."""
        agents = [
            create_agent_output(f"agent_{i}", Direction.LONG, 0.3)  # Low confidence
            for i in range(9)
        ]
        agents.append(create_agent_output("agent_9", Direction.SHORT, 0.3))

        result = consensus_engine.calculate(agents)

        assert result.should_trade is False
        assert "Confidence too low" in result.reason

    def test_fade_signal_calculation(self, consensus_engine):
        """Test that fade signal is calculated correctly."""
        # 90% agreement with 80% confidence = 72 fade signal
        agents = [
            create_agent_output(f"agent_{i}", Direction.LONG, 0.8)
            for i in range(9)
        ]
        agents.append(create_agent_output("agent_9", Direction.SHORT, 0.5))

        result = consensus_engine.calculate(agents)

        # 9/10 = 90% agreement, 80% confidence
        # fade_signal = 0.9 * 0.8 * 100 = 72
        assert result.fade_signal >= 70
        assert result.fade_signal <= 75

    def test_agent_breakdown_correct(self, consensus_engine):
        """Test that agent breakdown is correctly calculated."""
        agents = [
            create_agent_output("agent_1", Direction.LONG, 0.8),
            create_agent_output("agent_2", Direction.LONG, 0.7),
            create_agent_output("agent_3", Direction.LONG, 0.9),
            create_agent_output("agent_4", Direction.SHORT, 0.6),
            create_agent_output("agent_5", Direction.NEUTRAL, 0.5),
        ]

        result = consensus_engine.calculate(agents)

        assert result.agent_breakdown["long"] == 3
        assert result.agent_breakdown["short"] == 1
        assert result.agent_breakdown["neutral"] == 1

    def test_perfect_consensus_high_fade_signal(self, consensus_engine):
        """Test that 100% consensus with high confidence gives maximum fade signal."""
        agents = [
            create_agent_output(f"agent_{i}", Direction.LONG, 1.0)
            for i in range(10)
        ]

        result = consensus_engine.calculate(agents)

        assert result.should_trade is True
        assert result.fade_signal == 100
        assert result.consensus_strength == 1.0
        assert result.avg_confidence == 1.0


class TestConsensusEdgeCases:
    """Edge case tests for consensus engine."""

    def test_single_agent(self, consensus_engine):
        """Test behavior with single agent."""
        agents = [create_agent_output("agent_1", Direction.LONG, 0.9)]

        result = consensus_engine.calculate(agents)

        # Single agent is 100% consensus
        assert result.ta_consensus_direction == Direction.LONG
        assert result.consensus_strength == 1.0

    def test_exactly_80_percent_agreement(self, consensus_engine):
        """Test exactly 80% agreement threshold."""
        agents = [
            create_agent_output(f"agent_{i}", Direction.LONG, 0.8)
            for i in range(8)
        ]
        agents.extend([
            create_agent_output(f"agent_{i}", Direction.SHORT, 0.8)
            for i in range(8, 10)
        ])

        result = consensus_engine.calculate(agents)

        # Exactly 80% should trigger
        assert result.ta_consensus_direction == Direction.LONG
        assert result.consensus_strength == 0.8

    def test_mixed_confidence_levels(self, consensus_engine):
        """Test with varying confidence levels."""
        agents = [
            create_agent_output("agent_1", Direction.LONG, 1.0),
            create_agent_output("agent_2", Direction.LONG, 0.9),
            create_agent_output("agent_3", Direction.LONG, 0.8),
            create_agent_output("agent_4", Direction.LONG, 0.7),
            create_agent_output("agent_5", Direction.LONG, 0.6),
            create_agent_output("agent_6", Direction.LONG, 0.5),
            create_agent_output("agent_7", Direction.LONG, 0.4),
            create_agent_output("agent_8", Direction.LONG, 0.3),
            create_agent_output("agent_9", Direction.SHORT, 0.9),
            create_agent_output("agent_10", Direction.NEUTRAL, 0.5),
        ]

        result = consensus_engine.calculate(agents)

        # 8/9 directional = 88.9% LONG
        # Average LONG confidence = (1.0+0.9+0.8+0.7+0.6+0.5+0.4+0.3)/8 = 0.65
        assert result.ta_consensus_direction == Direction.LONG
        assert 0.60 <= result.avg_confidence <= 0.70
