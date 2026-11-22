from pydantic import BaseModel, ConfigDict
from typing import Optional

class LocalizationBase(BaseModel):
    identifier: str
    ru: str
    eng: str
    webpage: str

class LocalizationCreate(LocalizationBase):
    pass

class Localization(LocalizationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
