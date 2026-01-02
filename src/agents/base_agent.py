"""Base class for Technical Analysis agents."""

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import anthropic

from src.config import get_settings
from src.data.indicators import TechnicalIndicators
from src.data.models import AgentOutput, Direction
from src.data.price_feeds import PriceData
from src.utils.helpers import extract_json_from_text, utc_now
from src.utils.logging import get_logger

log = get_logger(__name__)


class BaseAgent(ABC):
    """Base class for all TA agents.

    Each agent uses a specific technical analysis methodology to generate
    trading signals. Agents should genuinely try to make profitable trades
    using their methodology - they should NOT know they're being inversed.
    """

    def __init__(self):
        self.settings = get_settings()
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique identifier for this agent."""
        pass

    @property
    @abstractmethod
    def methodology_name(self) -> str:
        """Name of the TA methodology this agent uses."""
        pass

    @property
    @abstractmethod
    def methodology_description(self) -> str:
        """Detailed description of the TA methodology."""
        pass

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=self.settings.anthropic_api_key.get_secret_value()
            )
        return self._client

    def build_prompt(
        self,
        asset: str,
        price_data: PriceData,
        indicators: TechnicalIndicators,
    ) -> str:
        """Build the analysis prompt for the LLM."""
        # Get recent OHLCV data as context
        ohlcv_context = self._format_ohlcv(price_data)

        # Get indicator context specific to this agent
        indicator_context = self.get_indicator_context(indicators)

        # Get additional methodology-specific context
        extra_context = self.get_extra_context(indicators)

        prompt = f"""You are a professional technical analysis trader specializing in {self.methodology_name}.

Your job is to analyze the current market data for {asset} and provide a trading recommendation based SOLELY on {self.methodology_name} principles.

## Your Methodology
{self.methodology_description}

## Current Market Data (4-hour candles, most recent last)
{ohlcv_context}

## Calculated Indicator Values
{indicator_context}

{extra_context}

## Your Task
Analyze the data using ONLY your assigned methodology. Do not consider fundamentals, news, or other technical methods.

Provide your recommendation in the following JSON format:
{{
  "agent_id": "{self.agent_id}",
  "asset": "{asset}",
  "timestamp": "{utc_now().isoformat()}",
  "direction": "LONG" or "SHORT" or "NEUTRAL",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<2-3 sentences explaining your analysis>",
  "key_levels": {{
    "entry": <suggested entry price>,
    "stop_loss": <suggested stop loss>,
    "take_profit": <suggested take profit>
  }},
  "indicators": {{
    // relevant indicator values you used
  }}
}}

Be decisive. If your methodology gives a signal, take it. Only output NEUTRAL if there is genuinely no signal present.
Respond with ONLY the JSON object, no additional text."""

        return prompt

    def _format_ohlcv(self, price_data: PriceData) -> str:
        """Format OHLCV data for the prompt."""
        records = price_data.to_dict_list()

        # Only show last 20 candles in detail to save tokens
        recent = records[-20:]
        lines = ["timestamp | open | high | low | close | volume"]
        lines.append("-" * 60)

        for r in recent:
            lines.append(
                f"{r['timestamp']} | {r['open']} | {r['high']} | {r['low']} | {r['close']} | {r['volume']}"
            )

        return "\n".join(lines)

    @abstractmethod
    def get_indicator_context(self, indicators: TechnicalIndicators) -> str:
        """Get the indicator values relevant to this agent's methodology."""
        pass

    def get_extra_context(self, indicators: TechnicalIndicators) -> str:
        """Override to provide additional context specific to methodology."""
        return ""

    async def analyze(
        self,
        asset: str,
        price_data: PriceData,
        indicators: TechnicalIndicators,
    ) -> AgentOutput:
        """Run analysis and return trading signal."""
        prompt = self.build_prompt(asset, price_data, indicators)

        try:
            response = await self.client.messages.create(
                model=self.settings.llm_model,
                max_tokens=self.settings.llm_max_tokens,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            # Extract text content
            content = response.content[0].text

            # Parse JSON from response
            output_dict = extract_json_from_text(content)

            if not output_dict:
                log.error(f"Agent {self.agent_id} returned invalid JSON: {content}")
                return self._neutral_output(asset, "Failed to parse LLM response")

            # Validate and convert to AgentOutput
            return AgentOutput(
                agent_id=self.agent_id,
                asset=asset,
                timestamp=utc_now(),
                direction=Direction(output_dict.get("direction", "NEUTRAL")),
                confidence=float(output_dict.get("confidence", 0.5)),
                reasoning=output_dict.get("reasoning", "No reasoning provided"),
                key_levels=output_dict.get("key_levels", {}),
                indicators=output_dict.get("indicators", {}),
            )

        except anthropic.APIError as e:
            log.error(f"API error in agent {self.agent_id}: {e}")
            return self._neutral_output(asset, f"API error: {str(e)}")
        except Exception as e:
            log.error(f"Error in agent {self.agent_id}: {e}")
            return self._neutral_output(asset, f"Error: {str(e)}")

    def _neutral_output(self, asset: str, reason: str) -> AgentOutput:
        """Return a neutral output when analysis fails."""
        return AgentOutput(
            agent_id=self.agent_id,
            asset=asset,
            timestamp=utc_now(),
            direction=Direction.NEUTRAL,
            confidence=0.0,
            reasoning=f"Analysis failed: {reason}",
            key_levels={},
            indicators={},
        )
