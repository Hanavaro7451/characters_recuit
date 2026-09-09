import secrets
import string

INVITE_ALPHABET = string.ascii_letters + string.digits
INVITE_CODE_LENGTH = 10


def generate_invite_code() -> str:
    return "".join(
        secrets.choice(INVITE_ALPHABET) for position in range(INVITE_CODE_LENGTH)
    )
