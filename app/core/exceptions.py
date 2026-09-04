class AppError(Exception):
    """Базовая ошибка приложения"""

    status_code = 400

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ConflictError(AppError):
    """Ошибка конфликта состояния"""

    status_code = 409
