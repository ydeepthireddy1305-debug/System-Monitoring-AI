from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from backend.auth.security import decode_access_token
from backend.database import get_connection


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/token"
)


def get_user_by_id(user_id: int) -> dict | None:
    connection = get_connection()

    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    email,
                    password_hash,
                    role,
                    is_active
                FROM users
                WHERE id = %s
                LIMIT 1
                """,
                (user_id,),
            )

            return cursor.fetchone()

    finally:
        connection.close()


def get_user_by_username(username: str) -> dict | None:
    connection = get_connection()

    try:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    email,
                    password_hash,
                    role,
                    is_active
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (username,),
            )

            return cursor.fetchone()

    finally:
        connection.close()


async def get_current_user(
    token: Annotated[
        str,
        Depends(oauth2_scheme),
    ],
) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    try:
        payload = decode_access_token(token)

        subject = payload.get("sub")

        if subject is None:
            raise credentials_exception

        user_id = int(subject)

    except (ValueError, TypeError):
        raise credentials_exception

    user = get_user_by_id(user_id)

    if user is None:
        raise credentials_exception

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    return user


def require_roles(
    *allowed_roles: str,
) -> Callable:

    async def role_checker(
        current_user: Annotated[
            dict,
            Depends(get_current_user),
        ],
    ) -> dict:

        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )

        return current_user

    return role_checker