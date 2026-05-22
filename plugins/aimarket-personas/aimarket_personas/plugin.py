"""aimarket-personas plugin — Auto-generated AI agent personas — chat-native discovery."""

from aimarket_hub.plugin import HubPlugin
from aimarket_personas.agent_personas import PersonaGenerator


class PersonasPlugin(HubPlugin):
    name = "aimarket-personas"
    version = "2.0.0"
    description = "Auto-generated AI agent personas — chat-native discovery"
    homepage = "https://github.com/ai-factory/aimarket-personas"
    category = "tooling"

    def __init__(self):
        super().__init__()
        self._generator = PersonaGenerator(seed=42)

    def register_routes(self, router):
        
        from pydantic import BaseModel, Field

        class GenerateRequest(BaseModel):
            capability_id: str = Field(..., min_length=2)
            product_id: str = Field(..., min_length=2)
            description: str = Field("")

        @router.post("/personas/generate")
        async def generate_persona(body: GenerateRequest):
            persona = self._generator.generate(body.capability_id, body.product_id, body.description)
            return persona.discovery_entry()

        @router.get("/personas/names")
        async def list_names():
            return {"names": ["Lyra", "Nova", "Atlas", "Vega", "Orion", "Zara", "Kai",
                              "Rune", "Sage", "Echo", "Neon", "Aria", "Cairo", "Indie",
                              "Juno", "Pixel", "Delta", "Lumen", "Quark", "Terra"]}

    def get_manifest_extension(self):
        return {"personas": {"enabled": True, "chat_native": True}}
