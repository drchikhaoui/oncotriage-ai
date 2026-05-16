"""Shared FastAPI dependencies."""
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

_http_basic = HTTPBasic()


def require_clinician(credentials: HTTPBasicCredentials = Depends(_http_basic)) -> str:
    correct_user = secrets.compare_digest(
        credentials.username.encode(), settings.clinician_user.encode()
    )
    correct_pass = secrets.compare_digest(
        credentials.password.encode(), settings.clinician_password.encode()
    )
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid clinician credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
