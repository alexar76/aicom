"""Framework adapters for the AWR/2 emitter.

Each module here bridges one agent framework's callback or middleware surface to
`awr_emitter.emit_receipt`. They are deliberately duck-typed against the framework rather
than importing it, so this package has no dependency on any framework and importing it
never pulls one in: an adapter you do not use costs nothing.
"""
