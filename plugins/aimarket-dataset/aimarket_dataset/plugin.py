"""aimarket-dataset plugin — Weekly anonymized invocation corpus exporter — open data for researchers."""

from aimarket_hub.plugin import HubPlugin
from aimarket_dataset.dataset_exporter import export_dataset


class DatasetPlugin(HubPlugin):
    name = "aimarket-dataset"
    version = "2.0.0"
    description = "Weekly anonymized invocation corpus exporter — open data for researchers"
    homepage = "https://github.com/ai-factory/aimarket-dataset"
    category = "tooling"

    def __init__(self):
        super().__init__()
        

    def register_routes(self, router):
        
        @router.post("/dataset/export")
        async def trigger_export(week_number: int = None):
            from aimarket_dataset.dataset_exporter import export_dataset
            from aimarket_hub.database import HubDatabase
            db = HubDatabase()
            path = export_dataset(db, week_number=week_number)
            return {"exported": str(path)}

    def get_manifest_extension(self):
        return {"dataset": {"format": "JSONL", "license": "CC-BY 4.0", "anonymization": "SHA-256"}}
