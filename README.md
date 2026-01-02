# Inverse Sentiment AI Trading System

An autonomous AI trading system that exploits the systematic failures of technical analysis (TA) based trading. The system deploys a swarm of AI agents that trade using traditional TA methods, aggregates their consensus sentiment, and executes trades in the **OPPOSITE** direction.

## Core Thesis

TA-based AI trading is not randomly wrong—it is **SYSTEMATICALLY** wrong in predictable ways:

- **75%+ long bias**: TA agents are systematically biased toward long positions
- **~32% win rates**: Below random chance (50%), indicating negative skill
- **Overconfidence correlation**: Higher confidence often means worse performance

By identifying and inverting these systematic errors, we can generate positive alpha.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DISCORD INTERFACE                                  │
│  Commands: /status /balance /positions /history /analysis /agents /pause    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR SERVICE                                │
│  - Coordinates all agents on configurable schedule (e.g., every 4 hours)    │
│  - Aggregates signals from TA swarm                                         │
│  - Applies trade filters                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│   TA AGENT SWARM     │  │   CONSENSUS ENGINE   │  │   RISK MANAGER       │
│   (10 Agents)        │  │                      │  │                      │
│                      │  │  - Aggregates votes  │  │  - Position limits   │
│   RSI, MACD, MA,     │  │  - Calculates bias % │  │  - Drawdown checks   │
│   Bollinger, etc.    │  │  - Fade signal       │  │  - VETO POWER        │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TRADE EXECUTOR                                      │
│  - Connects to Hyperliquid via API                                          │
│  - Executes inverse of consensus direction                                  │
│  - Manages stop losses and take profits                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## TA Agents

The system runs 10 specialized TA agents, each using a different methodology:

1. **RSI Agent** - Relative Strength Index (oversold/overbought)
2. **MA Crossover Agent** - 9/21 EMA crossovers
3. **Support/Resistance Agent** - Horizontal S/R levels
4. **MACD Agent** - MACD line crossovers
5. **Bollinger Band Agent** - Band touches for mean reversion
6. **Volume Profile Agent** - High-volume zones
7. **Fibonacci Agent** - Fib retracement levels
8. **Trend Line Agent** - Diagonal trend lines
9. **Ichimoku Agent** - Full Ichimoku cloud system
10. **Chart Pattern Agent** - Classic patterns (H&S, double tops, etc.)

## Trade Logic

1. **Consensus Required**: At least 8/10 agents (80%) must agree on direction
2. **Confidence Threshold**: Average confidence must be ≥ 60%
3. **Fade Signal**: Combined strength must be ≥ 60/100
4. **Inverse Trade**: Execute the OPPOSITE of TA consensus
5. **Risk Checks**: All trades must pass risk manager approval

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd inverse-sentiment-trader

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
```

## Configuration

Edit `.env` with your settings:

```bash
# Required API Keys
OPENROUTER_API_KEY=your_openrouter_api_key
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id
HYPERLIQUID_PRIVATE_KEY=your_wallet_private_key

# LLM Model (via OpenRouter)
# See https://openrouter.ai/models for options
LLM_MODEL=anthropic/claude-sonnet-4

# Trading Settings
HYPERLIQUID_TESTNET=true  # Start with testnet!
PAPER_TRADING=true        # Start with paper trading!
ANALYSIS_INTERVAL_HOURS=4
ASSETS_TO_TRADE=BTC,ETH,SOL

# Risk Settings
MAX_POSITION_SIZE_USD=1000
MAX_LEVERAGE=5
MAX_DAILY_DRAWDOWN_PCT=5
```

## Supported LLM Models (via OpenRouter)

The system uses [OpenRouter](https://openrouter.ai) for LLM access, giving you flexibility to choose models:

| Model | Cost | Notes |
|-------|------|-------|
| `anthropic/claude-sonnet-4` | ~$3/1M tokens | Recommended - best balance |
| `anthropic/claude-3.5-sonnet` | ~$3/1M tokens | Great performance |
| `anthropic/claude-3-haiku` | ~$0.25/1M tokens | Budget option |
| `google/gemini-flash-1.5` | ~$0.075/1M tokens | Very cheap |
| `openai/gpt-4o-mini` | ~$0.15/1M tokens | Good budget option |

## Running

```bash
# Start the system
python -m src.main

# Or with explicit module
python src/main.py
```

## Discord Commands

| Command | Description |
|---------|-------------|
| `/status` | System status, last/next analysis time |
| `/balance` | Account balance and margin |
| `/positions` | Open positions with P&L |
| `/history [n]` | Last n trades (default 10) |
| `/performance` | Win rate, total P&L, metrics |
| `/agents` | Latest TA agent signals |
| `/consensus` | Latest consensus analysis |
| `/pause` | Pause trading (admin) |
| `/resume` | Resume trading (admin) |
| `/config` | View risk configuration |
| `/analyze [asset]` | Force analysis for asset |

## Risk Management

The Risk Manager has **VETO POWER** over all trades:

- **Position Limits**: Max $1,000 per trade, $2,000 total exposure
- **Leverage Cap**: Maximum 5x (half of what TA agents typically use)
- **Drawdown Limits**:
  - Daily: -5% → pause trading
  - Weekly: -15% → pause trading
  - Total: -30% → stop trading entirely
- **Trade Frequency**: Max 2 trades/day, 4 hours between trades
- **Auto SL/TP**: 3% stop loss, 6% take profit (2:1 R:R)
- **Trailing Stops**: Activate at 3% profit, trail by 1.5%

## Development

```bash
# Run tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Type checking (optional)
mypy src/
```

## Project Structure

```
inverse-sentiment-trader/
├── src/
│   ├── agents/           # 10 TA agents
│   ├── consensus/        # Consensus engine
│   ├── data/             # Database, price feeds, indicators
│   ├── discord_bot/      # Discord bot & notifications
│   ├── execution/        # Trade execution, Hyperliquid client
│   ├── risk/             # Risk manager
│   ├── utils/            # Logging, helpers
│   ├── config.py         # Configuration
│   └── main.py           # Entry point
├── tests/                # Test suite
├── data/                 # SQLite database (created at runtime)
├── .env.example          # Environment template
├── requirements.txt      # Dependencies
└── README.md
```

## Warnings

1. **NEVER** commit private keys or API keys
2. **ALWAYS** start with testnet and paper trading
3. **START** with small capital you can afford to lose
4. **MONITOR** closely - this is experimental
5. **HAVE** a manual kill switch ready (`/pause` command)
6. **EXPECT** bugs and losses initially

## Deployment Checklist

- [ ] Run paper trading for 2+ weeks
- [ ] Run on Hyperliquid testnet for 1+ week
- [ ] Start with maximum $500 capital
- [ ] Monitor Discord multiple times per day
- [ ] Set up alerts for critical notifications
- [ ] Have manual intervention plan ready

## License

MIT License - Use at your own risk. This is experimental software.

## Disclaimer

This software is for educational and research purposes. Trading involves substantial risk of loss. Past performance is not indicative of future results. The authors are not responsible for any financial losses incurred through the use of this software.
