from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from backend.auth.dependencies import (
    get_current_user,
    get_user_by_username,
    require_roles,
)
from backend.auth.schemas import (
    TokenResponse,
    UserCreate,
    UserResponse,
)
from backend.auth.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from backend.database import get_connection


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/token",
    response_model=TokenResponse,
)
def login(
    form_data: Annotated[
        OAuth2PasswordRequestForm,
        Depends(),
    ],
):
    user = get_user_by_username(
        form_data.username
    )

    if user is None:
        verify_password(
            form_data.password,
            DUMMY_PASSWORD_HASH,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if not verify_password(
        form_data.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    access_token = create_access_token(
        user_id=user["id"],
        role=user["role"],
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user=Depends(get_current_user),
):
    return current_user


@router.post(
    "/users",
    response_model=UserResponse,
    dependencies=[
        Depends(require_roles("ADMIN"))
    ],
)
def create_user(
    user_data: UserCreate,
):
    connection = get_connection()

    try:
        with connection.cursor(dictionary=True) as cursor:

            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (user_data.username,),
            )

            if cursor.fetchone():
                raise HTTPException(
                    status_code=409,
                    detail="Username already exists.",
                )

            if user_data.email:
                cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE email = %s
                    LIMIT 1
                    """,
                    (user_data.email,),
                )

                if cursor.fetchone():
                    raise HTTPException(
                        status_code=409,
                        detail="Email already exists.",
                    )

            password_hash_value = hash_password(
                user_data.password
            )

            cursor.execute(
                """
                INSERT INTO users
                    (
                        username,
                        email,
                        password_hash,
                        role,
                        is_active
                    )
                VALUES
                    (%s, %s, %s, %s, TRUE)
                """,
                (
                    user_data.username,
                    user_data.email,
                    password_hash_value,
                    user_data.role,
                ),
            )

            user_id = cursor.lastrowid

        connection.commit()

        return {
            "id": user_id,
            "username": user_data.username,
            "email": user_data.email,
            "role": user_data.role,
            "is_active": True,
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()