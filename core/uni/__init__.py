"""UNI — unified credit ledger for Factory, Market, Mesh, and Hub."""

from core.uni.config import uni_enabled
from core.uni.wallet import UniWalletService

__all__ = ["UniWalletService", "uni_enabled", "get_uni_wallet"]


def get_uni_wallet() -> UniWalletService:
    return UniWalletService()
