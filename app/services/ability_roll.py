import secrets
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RollOutcome:
    position: int
    dice: tuple[int, int, int, int]
    dropped_index: int
    total: int


def score_dice(dice: tuple[int, int, int, int]) -> tuple[int, int]:
    """Отбросить первый минимальный кубик и сложить остальные три."""
    if len(dice) != 4 or any(die < 1 or die > 6 for die in dice):
        raise ValueError("Нужны четыре значения D6")
    dropped_index = dice.index(min(dice))
    return dropped_index, sum(dice) - dice[dropped_index]


def generate_rolls(roll_die: Callable[[], int] | None = None) -> list[RollOutcome]:
    """Сгенерировать шесть независимых групп на сервере."""
    if roll_die is None:
        def roll_die() -> int:
            return secrets.randbelow(6) + 1
    outcomes: list[RollOutcome] = []
    for position in range(1, 7):
        dice = (roll_die(), roll_die(), roll_die(), roll_die())
        dropped_index, total = score_dice(dice)
        outcomes.append(RollOutcome(position, dice, dropped_index, total))
    return outcomes
