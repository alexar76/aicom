"""The phases of POST /invoke, by branch and stage. ``aimarket_hub.hub_routes.invoke`` holds the
route, the request reading and the per-call state, and calls ``_invoke_local`` /
``_invoke_federated`` from here.

The phases read the channel-ledger functions as ``invoke.<name>`` at call time, so a value
patched on ``aimarket_hub.hub_routes.invoke`` reaches them. Every part imports its
neighbours after its own code: any of these modules may be imported first.
"""
