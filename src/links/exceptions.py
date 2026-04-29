from fastapi import HTTPException, status


class LinkException(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code=status_code, detail=detail)


class NotUniqueAliasError(LinkException):
    """Ошибка при попытке использовать уже занятый alias."""

    def __init__(self, alias: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Custom alias '{alias}' already exists. "
                "Please choose another one."
            ),
        )


class LinkExpiredError(LinkException):
    """Ошибка при истечении срока действия ссылки."""

    def __init__(self, short_code: str):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail=f"Link '{short_code}' has expired and is no longer available.",
        )
