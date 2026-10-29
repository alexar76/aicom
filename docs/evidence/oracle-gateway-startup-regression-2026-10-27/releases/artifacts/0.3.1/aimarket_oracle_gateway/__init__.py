"""AIMarket Oracle Gateway — a passthrough MCP server that exposes the ecosystem's
oracle capabilities (all 17 oracles — Platon, Chronos, Lumen, Murmuration, Landauer,
Fermat, Ablation, Lattice, Colony, Turing, Percola, Sortes, Gauss, Aestus, Betti,
Kantor, Fourier; 35 capability tools) as MCP tools so external AI agents can discover
and consume them. See README.md."""

from .gateway_core import CAPABILITIES, CapabilitySpec, GatewayError, OracleGateway

__all__ = ["OracleGateway", "CapabilitySpec", "CAPABILITIES", "GatewayError"]
__version__ = "0.3.1"
