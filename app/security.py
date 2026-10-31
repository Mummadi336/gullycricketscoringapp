import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


_USERNAME_VARIABLE = "GULLYSCORE_USERNAME"
_PASSWORD_VARIABLE = "GULLYSCORE_PASSWORD"
_basic_auth = HTTPBasic()


def _configured_credentials() -> tuple[str, str]:
    username = os.environ.get(_USERNAME_VARIABLE, "")
    password = os.environ.get(_PASSWORD_VARIABLE, "")
    if not username.strip() or len(password) < 16:
        raise RuntimeError(
            "Set GULLYSCORE_USERNAME and a GULLYSCORE_PASSWORD of at least "
            "16 characters before starting GullyScore."
        )
    return username, password


def validate_auth_configuration() -> None:
    _configured_credentials()


def require_api_auth(
    credentials: HTTPBasicCredentials = Depends(_basic_auth),
) -> str:
    try:
        expected_username, expected_password = _configured_credentials()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        ) from error

    username_valid = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        expected_username.encode("utf-8"),
    )
    password_valid = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        expected_password.encode("utf-8"),
    )
    if not (username_valid and password_valid):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
