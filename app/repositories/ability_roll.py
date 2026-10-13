from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ability_roll import AbilityRollResult, AbilityRollSet
from app.services.ability_roll import RollOutcome


class AbilityRollRepository:
    """Чтение неизменяемого набора и атомарная вставка шести результатов."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, character_id: int) -> AbilityRollSet | None:
        query = (
            select(AbilityRollSet)
            .where(AbilityRollSet.character_id == character_id)
            .options(selectinload(AbilityRollSet.results))
        )
        return (await self.session.scalars(query)).one_or_none()

    async def create(
        self, character_id: int, outcomes: list[RollOutcome]
    ) -> AbilityRollSet:
        roll_set = AbilityRollSet(character_id=character_id)
        roll_set.results = [
            AbilityRollResult(
                position=outcome.position,
                die_one=outcome.dice[0],
                die_two=outcome.dice[1],
                die_three=outcome.dice[2],
                die_four=outcome.dice[3],
                dropped_index=outcome.dropped_index,
                total=outcome.total,
            )
            for outcome in outcomes
        ]
        self.session.add(roll_set)
        await self.session.flush()
        return roll_set
