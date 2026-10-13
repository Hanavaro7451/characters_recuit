from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Ability = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]
ABILITIES: tuple[Ability, ...] = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


class Assignments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    STR: int = Field(gt=0)
    DEX: int = Field(gt=0)
    CON: int = Field(gt=0)
    INT: int = Field(gt=0)
    WIS: int = Field(gt=0)
    CHA: int = Field(gt=0)

    @model_validator(mode="after")
    def unique_results(self) -> "Assignments":
        if len(set(self.model_dump().values())) != 6:
            raise ValueError("Каждый результат можно назначить только один раз")
        return self


class PlusTwoPlusOneChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: Literal["plus_two_plus_one"]
    plus_two: Ability
    plus_one: Ability

    @model_validator(mode="after")
    def distinct_targets(self) -> "PlusTwoPlusOneChoice":
        if self.plus_two == self.plus_one:
            raise ValueError("Цели бонусов должны различаться")
        return self


class PlusOneEachChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern: Literal["plus_one_each"]


BonusChoice = PlusTwoPlusOneChoice | PlusOneEachChoice


class AbilityDistributionSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0)
    assignments: Assignments
    bonus_choice: BonusChoice = Field(discriminator="pattern")


class BonusSource(BaseModel):
    type: Literal["background"] = "background"
    catalog_version_id: int
    name: str


class AbilityValueResponse(BaseModel):
    ability: Ability
    roll_result_id: int | None
    base_value: int | None
    bonus: int | None
    bonus_source: BonusSource | None
    total: int | None
    modifier: int | None


class AbilityDistributionResponse(BaseModel):
    character_id: int
    character_version: int
    has_rolls: bool
    assignment_complete: bool
    bonus_complete: bool
    complete: bool
    bonus_choice: BonusChoice | None
    abilities: list[AbilityValueResponse] = Field(min_length=6, max_length=6)
