from app.models.catalog import BackgroundCatalog
from app.schemas.ability_distribution import (
    PlusOneEachChoice,
    PlusTwoPlusOneChoice,
)
from app.services.ability_distribution import (
    calculate_abilities,
    validate_bonus_choice,
)


def background(
    *,
    allow_plus_two_plus_one: bool = True,
    allow_plus_one_each: bool = True,
) -> BackgroundCatalog:
    return BackgroundCatalog(
        id=41,
        name="Предыстория для теста",
        ability_one="STR",
        ability_two="DEX",
        ability_three="CON",
        allow_plus_two_plus_one=allow_plus_two_plus_one,
        allow_plus_one_each=allow_plus_one_each,
    )


def test_equal_roll_totals_remain_distinct_results_and_plus_two_plus_one_applies_once():
    assignments = {
        "STR": 101,
        "DEX": 102,
        "CON": 103,
        "INT": 104,
        "WIS": 105,
        "CHA": 106,
    }
    totals = {101: 18, 102: 18, 103: 9, 104: 10, 105: 12, 106: 14}
    choice = PlusTwoPlusOneChoice(
        pattern="plus_two_plus_one", plus_two="STR", plus_one="DEX"
    )

    result = calculate_abilities(assignments, totals, choice, background())

    assert [item.ability for item in result] == [
        "STR",
        "DEX",
        "CON",
        "INT",
        "WIS",
        "CHA",
    ]
    assert [item.roll_result_id for item in result] == [101, 102, 103, 104, 105, 106]
    assert [item.base_value for item in result] == [18, 18, 9, 10, 12, 14]
    assert [item.bonus for item in result] == [2, 1, 0, 0, 0, 0]
    assert [item.total for item in result] == [20, 19, 9, 10, 12, 14]
    assert result[0].bonus_source.catalog_version_id == 41
    assert result[2].bonus_source is None


def test_plus_one_each_targets_only_the_three_background_abilities():
    choice = PlusOneEachChoice(pattern="plus_one_each")
    assignments = {
        ability: 201 + index
        for index, ability in enumerate(("STR", "DEX", "CON", "INT", "WIS", "CHA"))
    }

    result = calculate_abilities(
        assignments,
        {result_id: 10 for result_id in assignments.values()},
        choice,
        background(),
    )

    assert [item.bonus for item in result] == [1, 1, 1, 0, 0, 0]
    assert [item.total for item in result] == [11, 11, 11, 10, 10, 10]
    assert all(item.bonus_source is not None for item in result[:3])
    assert all(item.bonus_source is None for item in result[3:])


def test_negative_modifiers_use_floor_division():
    assignments = {
        ability: index + 1
        for index, ability in enumerate(("STR", "DEX", "CON", "INT", "WIS", "CHA"))
    }
    totals = {1: 9, 2: 8, 3: 7, 4: 10, 5: 11, 6: 12}
    choice = PlusTwoPlusOneChoice(
        pattern="plus_two_plus_one", plus_two="STR", plus_one="DEX"
    )

    result = calculate_abilities(assignments, totals, choice, background())

    assert [item.modifier for item in result] == [0, -1, -2, 0, 0, 1]


def test_unsupported_bonus_patterns_and_targets_are_rejected():
    only_plus_two = background(allow_plus_two_plus_one=True, allow_plus_one_each=False)
    only_plus_one_each = background(
        allow_plus_two_plus_one=False, allow_plus_one_each=True
    )

    assert not validate_bonus_choice(
        PlusOneEachChoice(pattern="plus_one_each"), only_plus_two
    )
    assert not validate_bonus_choice(
        PlusTwoPlusOneChoice(
            pattern="plus_two_plus_one", plus_two="STR", plus_one="DEX"
        ),
        only_plus_one_each,
    )
    assert not validate_bonus_choice(
        PlusTwoPlusOneChoice(
            pattern="plus_two_plus_one", plus_two="INT", plus_one="STR"
        ),
        background(),
    )


def test_missing_background_leaves_assignment_values_without_calculated_bonus():
    assignments = {
        ability: index + 1
        for index, ability in enumerate(("STR", "DEX", "CON", "INT", "WIS", "CHA"))
    }
    choice = PlusOneEachChoice(pattern="plus_one_each")

    result = calculate_abilities(
        assignments, {index: 15 for index in assignments.values()}, choice, None
    )

    assert all(item.roll_result_id is not None for item in result)
    assert all(item.base_value == 15 for item in result)
    assert all(item.bonus is None for item in result)
    assert all(item.total is None for item in result)
    assert all(item.modifier is None for item in result)
