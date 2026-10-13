from app.models.catalog import BackgroundCatalog
from app.schemas.ability_distribution import (
    ABILITIES,
    AbilityValueResponse,
    BonusChoice,
    BonusSource,
    PlusOneEachChoice,
    PlusTwoPlusOneChoice,
)


def validate_bonus_choice(
    choice: BonusChoice | None, background: BackgroundCatalog | None
) -> bool:
    """Проверить выбор против закреплённой версии предыстории."""
    if choice is None or background is None:
        return False
    targets = {background.ability_one, background.ability_two, background.ability_three}
    if isinstance(choice, PlusOneEachChoice):
        return background.allow_plus_one_each
    return (
        background.allow_plus_two_plus_one
        and choice.plus_two != choice.plus_one
        and choice.plus_two in targets
        and choice.plus_one in targets
    )


def calculate_abilities(
    assignments: dict[str, int],
    roll_totals: dict[int, int],
    choice: BonusChoice | None,
    background: BackgroundCatalog | None,
) -> list[AbilityValueResponse]:
    """Вычислить базу и поддерживаемый стартовый бонус без накопления прибавок."""
    complete_choice = validate_bonus_choice(choice, background)
    bonuses: dict[str, int] = {ability: 0 for ability in ABILITIES}
    if complete_choice and background is not None:
        if isinstance(choice, PlusTwoPlusOneChoice):
            bonuses[choice.plus_two] = 2
            bonuses[choice.plus_one] = 1
        elif isinstance(choice, PlusOneEachChoice):
            for ability in (
                background.ability_one,
                background.ability_two,
                background.ability_three,
            ):
                bonuses[ability] = 1
    values: list[AbilityValueResponse] = []
    for ability in ABILITIES:
        result_id = assignments.get(ability)
        base = roll_totals.get(result_id) if result_id is not None else None
        bonus = bonuses[ability] if complete_choice and base is not None else None
        total = base + bonus if base is not None and bonus is not None else None
        values.append(
            AbilityValueResponse(
                ability=ability,
                roll_result_id=result_id,
                base_value=base,
                bonus=bonus,
                bonus_source=(
                    BonusSource(catalog_version_id=background.id, name=background.name)
                    if bonus and background is not None
                    else None
                ),
                total=total,
                modifier=(total - 10) // 2 if total is not None else None,
            )
        )
    return values
