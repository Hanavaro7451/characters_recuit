from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ability_roll import AbilityRollSet


class AbilityRollGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AbilityRollResultResponse(BaseModel):
    id: int
    position: int = Field(ge=1, le=6)
    dice: list[int] = Field(min_length=4, max_length=4)
    dropped_index: int = Field(ge=0, le=3)
    total: int = Field(ge=3, le=18)


class AbilityRollSetResponse(BaseModel):
    id: int
    character_id: int
    generated_at: datetime
    results: list[AbilityRollResultResponse] = Field(min_length=6, max_length=6)

    @classmethod
    def from_model(cls, roll_set: AbilityRollSet) -> "AbilityRollSetResponse":
        """Подготовить сохранённый набор без дополнительных полей модели."""
        return cls(
            id=roll_set.id,
            character_id=roll_set.character_id,
            generated_at=roll_set.generated_at,
            results=[
                AbilityRollResultResponse(
                    id=result.id,
                    position=result.position,
                    dice=result.dice,
                    dropped_index=result.dropped_index,
                    total=result.total,
                )
                for result in roll_set.results
            ],
        )
