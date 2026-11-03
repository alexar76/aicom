"""Route groups of the hub app, one module per area.

Each module has one ``register(...)`` that ``aimarket_hub.api.create_app`` calls in
route order, passing the app state its routes read as keyword arguments.
"""
