def normalize_username(username: str) -> str:
    """Приводит имя пользователя к каноническому виду."""
    if any(character.isspace() for character in username):
        raise ValueError("Имя пользователя не должно содержать пробельные символы")

    return username.casefold()
