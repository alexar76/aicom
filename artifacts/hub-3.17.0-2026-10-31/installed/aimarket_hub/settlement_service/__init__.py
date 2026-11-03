"""VerifiedSettlementService's methods, one mixin per area. ``aimarket_hub.verified_settlement``
defines the service from them; import it from there. The mixins read that module's settings and
helpers at call time (``vs.<name>``), so a value set or patched on it reaches them.
"""
