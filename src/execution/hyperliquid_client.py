"""Hyperliquid exchange client wrapper."""

import json
import time
from typing import Any

import aiohttp
from eth_account import Account
from eth_account.messages import encode_typed_data

from src.config import get_settings
from src.utils.logging import get_logger

log = get_logger(__name__)


class HyperliquidClient:
    """Client for interacting with the Hyperliquid exchange API.

    Supports both testnet and mainnet.
    Handles wallet signing and order execution.
    """

    MAINNET_API = "https://api.hyperliquid.xyz"
    TESTNET_API = "https://api.hyperliquid-testnet.xyz"

    def __init__(self, private_key: str | None = None, testnet: bool = True):
        """Initialize the Hyperliquid client.

        Args:
            private_key: Wallet private key for signing transactions
            testnet: Whether to use testnet (default True)
        """
        settings = get_settings()

        if private_key:
            self._private_key = private_key
        else:
            self._private_key = settings.hyperliquid_private_key.get_secret_value()

        self.testnet = testnet if testnet is not None else settings.hyperliquid_testnet
        self.base_url = self.TESTNET_API if self.testnet else self.MAINNET_API

        # Create account from private key
        self._account = Account.from_key(self._private_key)
        self.address = self._account.address

        log.info(
            "Hyperliquid client initialized",
            address=self.address[:10] + "...",
            testnet=self.testnet,
        )

    async def _post(self, endpoint: str, payload: dict) -> dict:
        """Make a POST request to the API."""
        url = f"{self.base_url}{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    log.error(f"API error: {response.status} - {text}")
                    raise Exception(f"API error: {response.status} - {text}")

                return await response.json()

    async def get_account_state(self) -> dict[str, Any]:
        """Get account state including balances and positions."""
        payload = {
            "type": "clearinghouseState",
            "user": self.address,
        }

        return await self._post("/info", payload)

    async def get_account_balance(self) -> float:
        """Get account balance in USD."""
        state = await self.get_account_state()

        # Extract margin summary
        margin_summary = state.get("marginSummary", {})
        account_value = float(margin_summary.get("accountValue", 0))

        return account_value

    async def get_open_positions(self) -> list[dict]:
        """Get all open positions."""
        state = await self.get_account_state()

        positions = []
        for position in state.get("assetPositions", []):
            pos = position.get("position", {})
            size = float(pos.get("szi", 0))

            if size != 0:
                positions.append({
                    "asset": pos.get("coin"),
                    "size": size,
                    "entry_price": float(pos.get("entryPx", 0)),
                    "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                    "leverage": float(pos.get("leverage", {}).get("value", 1)),
                    "liquidation_price": float(pos.get("liquidationPx", 0)) if pos.get("liquidationPx") else None,
                })

        return positions

    async def get_all_mids(self) -> dict[str, float]:
        """Get current mid prices for all assets."""
        payload = {"type": "allMids"}
        return await self._post("/info", payload)

    async def get_meta(self) -> dict[str, Any]:
        """Get exchange metadata including available assets."""
        payload = {"type": "meta"}
        return await self._post("/info", payload)

    def _sign_order(self, order_action: dict, nonce: int) -> dict:
        """Sign an order action using EIP-712 typed data signing."""
        # Hyperliquid uses EIP-712 for signing
        domain = {
            "name": "HyperliquidSignTransaction",
            "version": "1",
            "chainId": 421614 if self.testnet else 42161,  # Arbitrum Sepolia / Arbitrum One
            "verifyingContract": "0x0000000000000000000000000000000000000000",
        }

        # Build the message to sign
        message = {
            "action": order_action,
            "nonce": nonce,
        }

        # Note: This is a simplified signing implementation
        # The actual Hyperliquid SDK handles this more robustly
        typed_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "HyperliquidTransaction": [
                    {"name": "action", "type": "string"},
                    {"name": "nonce", "type": "uint64"},
                ],
            },
            "primaryType": "HyperliquidTransaction",
            "domain": domain,
            "message": {
                "action": json.dumps(order_action, separators=(",", ":")),
                "nonce": nonce,
            },
        }

        signable_message = encode_typed_data(full_message=typed_data)
        signed = self._account.sign_message(signable_message)

        return {
            "r": hex(signed.r),
            "s": hex(signed.s),
            "v": signed.v,
        }

    async def place_order(
        self,
        asset: str,
        is_buy: bool,
        size: float,
        price: float | None = None,
        order_type: str = "MARKET",
        reduce_only: bool = False,
        leverage: float | None = None,
    ) -> dict[str, Any]:
        """Place an order on Hyperliquid.

        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            is_buy: True for buy/long, False for sell/short
            size: Order size in USD
            price: Limit price (required for limit orders)
            order_type: "MARKET" or "LIMIT"
            reduce_only: Whether this is a reduce-only order
            leverage: Desired leverage (will be set if provided)

        Returns:
            Order response from the exchange
        """
        # Set leverage if specified
        if leverage:
            await self.set_leverage(asset, leverage)

        # Get current price for market orders
        if order_type == "MARKET" and price is None:
            mids = await self.get_all_mids()
            price = float(mids.get(asset, 0))
            if price == 0:
                raise ValueError(f"Could not get price for {asset}")

            # Add slippage for market orders
            if is_buy:
                price = price * 1.001  # 0.1% slippage
            else:
                price = price * 0.999

        nonce = int(time.time() * 1000)

        # Build order action
        order_action = {
            "type": "order",
            "orders": [{
                "a": self._get_asset_index(asset),  # Asset index
                "b": is_buy,  # is_buy
                "p": str(round(price, 2)),  # price
                "s": str(round(size, 4)),  # size
                "r": reduce_only,  # reduce_only
                "t": {
                    "limit": {"tif": "Ioc"}  # Immediate or cancel for market
                } if order_type == "MARKET" else {
                    "limit": {"tif": "Gtc"}  # Good til cancelled for limit
                },
            }],
            "grouping": "na",
        }

        # Sign the order
        signature = self._sign_order(order_action, nonce)

        # Build the request
        payload = {
            "action": order_action,
            "nonce": nonce,
            "signature": signature,
        }

        log.info(
            "Placing order",
            asset=asset,
            is_buy=is_buy,
            size=size,
            price=price,
            order_type=order_type,
        )

        response = await self._post("/exchange", payload)

        if response.get("status") == "err":
            raise Exception(f"Order failed: {response.get('response')}")

        return response

    async def place_trigger_order(
        self,
        asset: str,
        trigger_price: float,
        is_buy: bool,
        size: float,
        order_type: str = "STOP_MARKET",
    ) -> dict[str, Any]:
        """Place a trigger order (stop loss or take profit).

        Args:
            asset: Asset symbol
            trigger_price: Price at which to trigger
            is_buy: Direction of the triggered order
            size: Order size
            order_type: "STOP_MARKET" or "TAKE_PROFIT_MARKET"
        """
        nonce = int(time.time() * 1000)

        # Get current price for slippage
        mids = await self.get_all_mids()
        current_price = float(mids.get(asset, trigger_price))

        # Set execution price with slippage
        if is_buy:
            limit_price = trigger_price * 1.01  # 1% slippage for stop
        else:
            limit_price = trigger_price * 0.99

        trigger_type = "tp" if order_type == "TAKE_PROFIT_MARKET" else "sl"

        order_action = {
            "type": "order",
            "orders": [{
                "a": self._get_asset_index(asset),
                "b": is_buy,
                "p": str(round(limit_price, 2)),
                "s": str(round(size, 4)),
                "r": True,  # Reduce only
                "t": {
                    "trigger": {
                        "triggerPx": str(round(trigger_price, 2)),
                        "isMarket": True,
                        "tpsl": trigger_type,
                    }
                },
            }],
            "grouping": "na",
        }

        signature = self._sign_order(order_action, nonce)

        payload = {
            "action": order_action,
            "nonce": nonce,
            "signature": signature,
        }

        log.info(
            "Placing trigger order",
            asset=asset,
            type=order_type,
            trigger_price=trigger_price,
            is_buy=is_buy,
            size=size,
        )

        response = await self._post("/exchange", payload)

        if response.get("status") == "err":
            raise Exception(f"Trigger order failed: {response.get('response')}")

        return response

    async def set_leverage(self, asset: str, leverage: float) -> dict:
        """Set leverage for an asset."""
        nonce = int(time.time() * 1000)

        action = {
            "type": "updateLeverage",
            "asset": self._get_asset_index(asset),
            "isCross": True,
            "leverage": int(leverage),
        }

        signature = self._sign_order(action, nonce)

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
        }

        return await self._post("/exchange", payload)

    async def cancel_all_orders(self, asset: str | None = None) -> dict:
        """Cancel all open orders, optionally filtered by asset."""
        nonce = int(time.time() * 1000)

        if asset:
            action = {
                "type": "cancel",
                "cancels": [{"a": self._get_asset_index(asset), "o": 0}],  # 0 = all orders
            }
        else:
            action = {
                "type": "cancelAll",
            }

        signature = self._sign_order(action, nonce)

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
        }

        return await self._post("/exchange", payload)

    async def close_position(self, asset: str) -> dict | None:
        """Close an open position for an asset."""
        positions = await self.get_open_positions()

        for pos in positions:
            if pos["asset"] == asset:
                size = abs(pos["size"])
                is_buy = pos["size"] < 0  # If short, we need to buy to close

                return await self.place_order(
                    asset=asset,
                    is_buy=is_buy,
                    size=size,
                    order_type="MARKET",
                    reduce_only=True,
                )

        return None  # No position to close

    def _get_asset_index(self, asset: str) -> int:
        """Get the numeric index for an asset.

        This is a simplified mapping - the actual SDK fetches this from the meta endpoint.
        """
        # Common asset indices (these may need to be updated from meta endpoint)
        asset_map = {
            "BTC": 0,
            "ETH": 1,
            "SOL": 4,
            "DOGE": 5,
            "AVAX": 7,
            "MATIC": 8,
            "LTC": 9,
            "LINK": 10,
            "ARB": 11,
            "OP": 12,
        }

        return asset_map.get(asset.upper(), 0)

    async def get_order_status(self, order_id: str) -> dict | None:
        """Get status of a specific order."""
        payload = {
            "type": "orderStatus",
            "user": self.address,
            "oid": order_id,
        }

        try:
            return await self._post("/info", payload)
        except Exception:
            return None

    async def get_fills(self, limit: int = 100) -> list[dict]:
        """Get recent fills for the account."""
        payload = {
            "type": "userFills",
            "user": self.address,
        }

        response = await self._post("/info", payload)
        return response[:limit] if response else []
