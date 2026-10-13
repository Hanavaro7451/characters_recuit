from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import ArchiveReason, CharacterStatus
from app.schemas.catalog import BackgroundVersionResponse, CatalogVersionResponse


class CharacterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    species_id: int = Field(gt=0)
    class_catalog_id: int = Field(gt=0)
    background_id: int = Field(gt=0)


class CharacterPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    species_id: int | None = Field(default=None, gt=0)
    class_catalog_id: int | None = Field(default=None, gt=0)
    background_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_changes(self) -> "CharacterPatch":
        changed = self.model_fields_set - {"expected_version"}
        if not changed:
            raise ValueError("Укажите хотя бы одно поле для изменения")
        if any(getattr(self, key) is None for key in changed):
            raise ValueError("Редактируемые поля не могут быть null")
        return self


class CharacterResponse(BaseModel):
    id: int
    campaign_id: int
    owner_user_id: int
    name: str
    status: CharacterStatus
    archive_reason: ArchiveReason | None
    level: int
    version: int
    species: CatalogVersionResponse | None
    character_class: CatalogVersionResponse | None
    background: BackgroundVersionResponse | None
    legacy_race: str | None
    legacy_character_class: str | None
