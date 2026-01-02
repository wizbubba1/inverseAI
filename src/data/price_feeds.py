"""Price data fetching from various sources."""

from datetime import datetime, timezone
from typing import Any

import aiohttp
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)


class PriceData:
    """Container for OHLCV price data."""

    def __init__(self, df: pd.DataFrame, asset: str, timeframe: str):
        self.df = df
        self.asset = asset
        self.timeframe = timeframe

    @property
    def open(self) -> pd.Series:
        return self.df["open"]

    @property
    def high(self) -> pd.Series:
        return self.df["high"]

    @property
    def low(self) -> pd.Series:
        return self.df["low"]

    @property
    def close(self) -> pd.Series:
        return self.df["close"]

    @property
    def volume(self) -> pd.Series:
        return self.df["volume"]

    @property
    def current_price(self) -> float:
        return float(self.df["close"].iloc[-1])

    @property
    def timestamps(self) -> pd.Series:
        return self.df["timestamp"]

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Convert to list of dicts for LLM context."""
        records = []
        for _, row in self.df.tail(100).iterrows():
            records.append({
                "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": round(float(row["volume"]), 2),
            })
        return records


class PriceFeed:
    """Abstract base class for price feeds."""

    async def fetch_ohlcv(
        self,
        asset: str,
        timeframe: str = "4h",
        limit: int = 100,
    ) -> PriceData:
        raise NotImplementedError

    async def get_current_price(self, asset: str) -> float:
        raise NotImplementedError

    async def get_funding_rate(self, asset: str) -> float | None:
        raise NotImplementedError


class HyperliquidPriceFeed(PriceFeed):
    """Price feed from Hyperliquid API."""

    BASE_URL = "https://api.hyperliquid.xyz"
    TESTNET_URL = "https://api.hyperliquid-testnet.xyz"

    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    def __init__(self, testnet: bool = True):
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL

    async def fetch_ohlcv(
        self,
        asset: str,
        timeframe: str = "4h",
        limit: int = 100,
    ) -> PriceData:
        """Fetch OHLCV data from Hyperliquid."""
        interval = self.TIMEFRAME_MAP.get(timeframe, "4h")

        url = f"{self.base_url}/info"
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": asset,
                "interval": interval,
                "startTime": 0,  # Will get most recent
                "endTime": int(datetime.now(timezone.utc).timestamp() * 1000),
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    log.error(f"Hyperliquid API error: {response.status}")
                    raise Exception(f"Hyperliquid API error: {response.status}")

                data = await response.json()

        # Convert to DataFrame
        candles = data[-limit:] if len(data) > limit else data

        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "n_trades"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        return PriceData(df, asset, timeframe)

    async def get_current_price(self, asset: str) -> float:
        """Get current mid price from Hyperliquid."""
        url = f"{self.base_url}/info"
        payload = {"type": "allMids"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    raise Exception(f"Hyperliquid API error: {response.status}")

                data = await response.json()

        if asset in data:
            return float(data[asset])

        raise ValueError(f"Asset {asset} not found on Hyperliquid")

    async def get_funding_rate(self, asset: str) -> float | None:
        """Get current funding rate for a perpetual."""
        url = f"{self.base_url}/info"
        payload = {"type": "metaAndAssetCtxs"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    return None

                data = await response.json()

        # Find the asset in the response
        if len(data) >= 2:
            asset_ctxs = data[1]
            meta = data[0]

            for i, ctx in enumerate(asset_ctxs):
                if meta["universe"][i]["name"] == asset:
                    return float(ctx.get("funding", 0))

        return None


class BinancePriceFeed(PriceFeed):
    """Backup price feed from Binance API."""

    BASE_URL = "https://api.binance.com/api/v3"

    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    def _get_symbol(self, asset: str) -> str:
        """Convert asset to Binance symbol."""
        asset = asset.upper()
        if not asset.endswith("USDT"):
            return f"{asset}USDT"
        return asset

    async def fetch_ohlcv(
        self,
        asset: str,
        timeframe: str = "4h",
        limit: int = 100,
    ) -> PriceData:
        """Fetch OHLCV data from Binance."""
        symbol = self._get_symbol(asset)
        interval = self.TIMEFRAME_MAP.get(timeframe, "4h")

        url = f"{self.BASE_URL}/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    log.error(f"Binance API error: {response.status}")
                    raise Exception(f"Binance API error: {response.status}")

                data = await response.json()

        # Convert to DataFrame
        df = pd.DataFrame(
            data,
            columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore",
            ],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # Keep only needed columns
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        return PriceData(df, asset, timeframe)

    async def get_current_price(self, asset: str) -> float:
        """Get current price from Binance."""
        symbol = self._get_symbol(asset)
        url = f"{self.BASE_URL}/ticker/price"
        params = {"symbol": symbol}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise Exception(f"Binance API error: {response.status}")

                data = await response.json()

        return float(data["price"])

    async def get_funding_rate(self, asset: str) -> float | None:
        """Binance spot doesn't have funding rates."""
        return None


class MultiSourcePriceFeed(PriceFeed):
    """Price feed that falls back to backup sources."""

    def __init__(self, primary: PriceFeed, backups: list[PriceFeed]):
        self.primary = primary
        self.backups = backups

    async def fetch_ohlcv(
        self,
        asset: str,
        timeframe: str = "4h",
        limit: int = 100,
    ) -> PriceData:
        """Try primary, then backups."""
        try:
            return await self.primary.fetch_ohlcv(asset, timeframe, limit)
        except Exception as e:
            log.warning(f"Primary feed failed: {e}, trying backups")

        for backup in self.backups:
            try:
                return await backup.fetch_ohlcv(asset, timeframe, limit)
            except Exception as e:
                log.warning(f"Backup feed failed: {e}")

        raise Exception("All price feeds failed")

    async def get_current_price(self, asset: str) -> float:
        """Try primary, then backups."""
        try:
            return await self.primary.get_current_price(asset)
        except Exception:
            pass

        for backup in self.backups:
            try:
                return await backup.get_current_price(asset)
            except Exception:
                pass

        raise Exception("All price feeds failed")

    async def get_funding_rate(self, asset: str) -> float | None:
        """Try primary, then backups."""
        try:
            rate = await self.primary.get_funding_rate(asset)
            if rate is not None:
                return rate
        except Exception:
            pass

        for backup in self.backups:
            try:
                rate = await backup.get_funding_rate(asset)
                if rate is not None:
                    return rate
            except Exception:
                pass

        return None


def create_price_feed(testnet: bool = True) -> PriceFeed:
    """Create a price feed with fallback sources."""
    primary = HyperliquidPriceFeed(testnet=testnet)
    backups = [BinancePriceFeed()]
    return MultiSourcePriceFeed(primary, backups)
