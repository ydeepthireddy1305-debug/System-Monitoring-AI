import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash


load_dotenv()


AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY")

if not AUTH_SECRET_KEY:
    raise RuntimeError(
        "AUTH_SECRET_KEY is missing from the environment."
    )


AUTH_ALGORITHM = os.getenv(
    "AUTH_ALGORITHM",
    "HS256",
)

AUTH_ACCESS_TOKEN_MINUTES = int(
    os.getenv(
        "AUTH_ACCESS_TOKEN_MINUTES",
        "30",
    )
)


password_hash = PasswordHash.recommended()


DUMMY_PASSWORD_HASH = password_hash.hash(
    "monitoring-system-dummy-password"
)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(
    user_id: int,
    role: str,
) -> str:
    now = datetime.now(timezone.utc)

    expires_at = now + timedelta(
        minutes=AUTH_ACCESS_TOKEN_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        AUTH_SECRET_KEY,
        algorithm=AUTH_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            AUTH_SECRET_KEY,
            algorithms=[AUTH_ALGORITHM],
        )
    except InvalidTokenError as exc:
        raise ValueError(
            "Invalid or expired access token."
        ) from exc