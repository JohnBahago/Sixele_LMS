from datetime import datetime
from pydantic import BaseModel, Field

class SettingDefinition(BaseModel):
    key: str
    category: str
    label: str
    description: str
    value: object
    value_type: str
    editable: bool = True
    updated_at: datetime | None = None

class SettingUpdate(BaseModel):
    value: object

class SettingsResponse(BaseModel):
    settings: list[SettingDefinition]
