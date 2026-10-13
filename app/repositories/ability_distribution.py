from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ability_distribution import AbilityDistribution
from app.schemas.ability_distribution import BonusChoice, PlusTwoPlusOneChoice


class AbilityDistributionRepository:
    """Хранить назначение результатов отдельно от неизменяемых бросков."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, character_id: int) -> AbilityDistribution | None:
        query = select(AbilityDistribution).where(
            AbilityDistribution.character_id == character_id
        )
        return (await self.session.scalars(query)).one_or_none()

    async def save(
        self,
        *,
        character_id: int,
        roll_set_id: int,
        assignments: dict[str, int],
        choice: BonusChoice,
    ) -> AbilityDistribution:
        row = await self.get(character_id)
        if row is None:
            row = AbilityDistribution(
                character_id=character_id, roll_set_id=roll_set_id
            )
            self.session.add(row)
        for ability, result_id in assignments.items():
            setattr(row, f"{ability.lower()}_result_id", result_id)
        row.pattern = choice.pattern
        row.plus_two = (
            choice.plus_two if isinstance(choice, PlusTwoPlusOneChoice) else None
        )
        row.plus_one = (
            choice.plus_one if isinstance(choice, PlusTwoPlusOneChoice) else None
        )
        await self.session.flush()
        return row
