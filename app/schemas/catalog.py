from pydantic import BaseModel, ConfigDict


class CatalogVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    ruleset: str
    content_version: str
    name: str
    description: str
    source_title: str
    source_url: str
    license_name: str
    attribution: str
    available_for_selection: bool


class BackgroundVersionResponse(CatalogVersionResponse):
    ability_one: str
    ability_two: str
    ability_three: str
    allow_plus_two_plus_one: bool
    allow_plus_one_each: bool
