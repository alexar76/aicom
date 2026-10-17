"""The pieces behind ``vercel_fullstack_adapter``: finding the app, requirements, env, and the
source patches a generated product gets before it is bundled.

``web.backend.services.vercel_fullstack_adapter`` re-exports every name here and builds the
bundle in ``build_vercel_bundle``; import from there."""
