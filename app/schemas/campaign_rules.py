from pydantic import BaseModel, Field


class CampaignRuleUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)
    changes: dict[str, int | float]


class CampaignRuleRestore(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)
