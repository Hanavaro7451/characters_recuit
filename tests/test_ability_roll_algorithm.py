import pytest

from app.services.ability_roll import generate_rolls, score_dice


def test_equal_minima_drop_only_the_first_minimum():
    dropped_index, total = score_dice((2, 2, 5, 6))

    assert dropped_index == 0
    assert total == 13


@pytest.mark.parametrize(
    ("dice", "expected"),
    [
        ((1, 1, 1, 1), (0, 3)),
        ((6, 6, 6, 6), (0, 18)),
    ],
)
def test_score_dice_handles_extreme_rolls(dice, expected):
    assert score_dice(dice) == expected


def test_generator_consumes_exactly_twenty_four_server_rolls_in_six_groups():
    values = iter(
        (
            1, 1, 2, 4,
            6, 6, 6, 6,
            1, 2, 3, 4,
            2, 2, 2, 5,
            3, 4, 5, 6,
            1, 1, 1, 1,
        )
    )
    consumed = 0

    def roll_die() -> int:
        nonlocal consumed
        consumed += 1
        return next(values)

    outcomes = generate_rolls(roll_die)

    assert consumed == 24
    assert len(outcomes) == 6
    assert [outcome.position for outcome in outcomes] == list(range(1, 7))
    assert [outcome.dice for outcome in outcomes] == [
        (1, 1, 2, 4),
        (6, 6, 6, 6),
        (1, 2, 3, 4),
        (2, 2, 2, 5),
        (3, 4, 5, 6),
        (1, 1, 1, 1),
    ]
    assert [outcome.dropped_index for outcome in outcomes] == [0, 0, 0, 0, 0, 0]
    assert [outcome.total for outcome in outcomes] == [7, 18, 9, 9, 15, 3]


@pytest.mark.parametrize(
    "dice",
    [(), (1, 2, 3), (1, 2, 3, 7), (0, 2, 3, 4)],
)
def test_score_dice_rejects_values_outside_four_d6(dice):
    with pytest.raises(ValueError):
        score_dice(dice)
