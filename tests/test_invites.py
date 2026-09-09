from app.core.invites import (
    INVITE_ALPHABET,
    INVITE_CODE_LENGTH,
    generate_invite_code,
)


def test_generate_invite_code_uses_expected_length_and_alphabet() -> None:
    invite_code = generate_invite_code()

    assert len(invite_code) == INVITE_CODE_LENGTH
    assert set(invite_code) <= set(INVITE_ALPHABET)
