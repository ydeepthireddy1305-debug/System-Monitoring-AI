import getpass

from backend.auth.dependencies import get_user_by_username
from backend.auth.security import hash_password
from backend.database import get_connection


def main() -> None:
    username = input("Admin username: ").strip()
    email = input("Admin email: ").strip()

    password = getpass.getpass("Admin password: ")
    confirm_password = getpass.getpass(
        "Confirm password: "
    )

    if password != confirm_password:
        raise ValueError("Passwords do not match.")

    if len(password) < 8:
        raise ValueError(
            "Password must be at least 8 characters."
        )

    if get_user_by_username(username):
        raise ValueError(
            f"User '{username}' already exists."
        )

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
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
                    (%s, %s, %s, 'ADMIN', TRUE)
                """,
                (
                    username,
                    email or None,
                    hash_password(password),
                ),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    print(
        f"Admin user '{username}' created successfully."
    )


if __name__ == "__main__":
    main()