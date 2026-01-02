"""Consensus engine for aggregating TA agent signals and calculating fade signal."""

from src.config import get_consensus_config
from src.data.models import AgentOutput, ConsensusResult, Direction
from src.utils.logging import get_logger

log = get_logger(__name__)


class ConsensusEngine:
    """Engine for calculating consensus from TA agent outputs.

    This is the core of the inverse sentiment strategy:
    1. Aggregate all TA agent signals
    2. Calculate consensus direction and strength
    3. Generate a "fade signal" when consensus is strong
    4. Recommend trading the OPPOSITE direction of the TA consensus
    """

    def __init__(self):
        self.config = get_consensus_config()

    def calculate(self, agent_outputs: list[AgentOutput]) -> ConsensusResult:
        """Calculate consensus from agent outputs.

        Returns a ConsensusResult with:
        - should_trade: Whether conditions are met for a fade trade
        - ta_consensus_direction: What the TA agents collectively recommend
        - our_trade_direction: The INVERSE of ta_consensus_direction
        - fade_signal: Strength of the fade signal (0-100)
        """
        if not agent_outputs:
            return ConsensusResult(
                should_trade=False,
                reason="No agent outputs to analyze",
            )

        # Count directions
        long_count = sum(1 for a in agent_outputs if a.direction == Direction.LONG)
        short_count = sum(1 for a in agent_outputs if a.direction == Direction.SHORT)
        neutral_count = sum(1 for a in agent_outputs if a.direction == Direction.NEUTRAL)

        total_agents = len(agent_outputs)
        total_directional = long_count + short_count

        agent_breakdown = {
            "long": long_count,
            "short": short_count,
            "neutral": neutral_count,
            "total": total_agents,
        }

        log.info(
            "Agent breakdown",
            long=long_count,
            short=short_count,
            neutral=neutral_count,
        )

        # If no directional signals, no trade
        if total_directional == 0:
            return ConsensusResult(
                should_trade=False,
                reason="All agents neutral - no directional signal",
                agent_breakdown=agent_breakdown,
            )

        # Calculate bias percentages (excluding neutrals)
        long_bias = long_count / total_directional
        short_bias = short_count / total_directional

        log.info(
            "Bias calculation",
            long_bias=f"{long_bias:.1%}",
            short_bias=f"{short_bias:.1%}",
        )

        # Determine consensus direction and strength
        if long_bias >= self.config.min_agreement_pct:
            consensus_direction = Direction.LONG
            consensus_strength = long_bias
            consensus_agents = [a for a in agent_outputs if a.direction == Direction.LONG]
        elif short_bias >= self.config.min_agreement_pct:
            consensus_direction = Direction.SHORT
            consensus_strength = short_bias
            consensus_agents = [a for a in agent_outputs if a.direction == Direction.SHORT]
        else:
            # No strong consensus
            return ConsensusResult(
                should_trade=False,
                reason=f"No strong consensus: {long_bias:.0%} long, {short_bias:.0%} short (need {self.config.min_agreement_pct:.0%}+)",
                ta_consensus_direction=Direction.LONG if long_bias > short_bias else Direction.SHORT,
                consensus_strength=max(long_bias, short_bias),
                avg_confidence=sum(a.confidence for a in agent_outputs) / len(agent_outputs),
                fade_signal=0,
                agent_breakdown=agent_breakdown,
            )

        # Calculate average confidence of consensus group
        avg_confidence = sum(a.confidence for a in consensus_agents) / len(consensus_agents)

        log.info(
            "Consensus found",
            direction=consensus_direction.value,
            strength=f"{consensus_strength:.1%}",
            avg_confidence=f"{avg_confidence:.1%}",
        )

        # Check confidence threshold
        if avg_confidence < self.config.min_confidence:
            return ConsensusResult(
                should_trade=False,
                reason=f"Confidence too low: {avg_confidence:.0%} (need {self.config.min_confidence:.0%}+)",
                ta_consensus_direction=consensus_direction,
                consensus_strength=consensus_strength,
                avg_confidence=avg_confidence,
                fade_signal=0,
                agent_breakdown=agent_breakdown,
            )

        # Calculate fade signal strength (0-100)
        # Higher when: more agreement + higher confidence
        fade_signal = consensus_strength * avg_confidence * 100

        log.info("Fade signal calculated", fade_signal=f"{fade_signal:.1f}/100")

        # Check fade signal threshold
        if fade_signal < self.config.min_fade_signal:
            return ConsensusResult(
                should_trade=False,
                reason=f"Fade signal too weak: {fade_signal:.1f} (need {self.config.min_fade_signal}+)",
                ta_consensus_direction=consensus_direction,
                consensus_strength=consensus_strength,
                avg_confidence=avg_confidence,
                fade_signal=fade_signal,
                agent_breakdown=agent_breakdown,
            )

        # THE INVERSE: Our trade direction is OPPOSITE of TA consensus
        our_direction = Direction.SHORT if consensus_direction == Direction.LONG else Direction.LONG

        log.info(
            "TRADE SIGNAL",
            ta_consensus=consensus_direction.value,
            our_trade=our_direction.value,
            fade_signal=f"{fade_signal:.1f}/100",
        )

        return ConsensusResult(
            should_trade=True,
            reason=f"Strong {consensus_direction.value} consensus ({consensus_strength:.0%}) with {avg_confidence:.0%} confidence -> FADE to {our_direction.value}",
            ta_consensus_direction=consensus_direction,
            our_trade_direction=our_direction,
            consensus_strength=consensus_strength,
            avg_confidence=avg_confidence,
            fade_signal=fade_signal,
            agent_breakdown=agent_breakdown,
        )

    def get_agent_summary(self, agent_outputs: list[AgentOutput]) -> str:
        """Generate a human-readable summary of agent signals."""
        if not agent_outputs:
            return "No agent signals available"

        lines = ["## TA Agent Signals", ""]

        # Group by direction
        by_direction: dict[Direction, list[AgentOutput]] = {
            Direction.LONG: [],
            Direction.SHORT: [],
            Direction.NEUTRAL: [],
        }

        for output in agent_outputs:
            by_direction[output.direction].append(output)

        # LONG agents
        if by_direction[Direction.LONG]:
            lines.append(f"### LONG ({len(by_direction[Direction.LONG])} agents)")
            for agent in by_direction[Direction.LONG]:
                lines.append(f"- **{agent.agent_id}**: {agent.confidence:.0%} confidence")
                lines.append(f"  - {agent.reasoning}")
            lines.append("")

        # SHORT agents
        if by_direction[Direction.SHORT]:
            lines.append(f"### SHORT ({len(by_direction[Direction.SHORT])} agents)")
            for agent in by_direction[Direction.SHORT]:
                lines.append(f"- **{agent.agent_id}**: {agent.confidence:.0%} confidence")
                lines.append(f"  - {agent.reasoning}")
            lines.append("")

        # NEUTRAL agents
        if by_direction[Direction.NEUTRAL]:
            lines.append(f"### NEUTRAL ({len(by_direction[Direction.NEUTRAL])} agents)")
            for agent in by_direction[Direction.NEUTRAL]:
                lines.append(f"- **{agent.agent_id}**: {agent.reasoning}")
            lines.append("")

        return "\n".join(lines)
