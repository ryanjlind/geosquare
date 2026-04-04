from app.core.db import get_conn
import re

USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9]{3,15}$')


def is_username_valid(username: str) -> bool:
    return bool(USERNAME_REGEX.fullmatch(username))


def is_username_available(username: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM Users WHERE Username = ?",
            (username,)
        )
        return cur.fetchone() is None


def set_username(user_id: int, username: str) -> tuple[bool, str | None]:
    if not is_username_valid(username):
        return False, 'Invalid username'

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT 1 FROM Users WHERE Username = ?",
            (username,)
        )
        if cur.fetchone():
            return False, 'Username taken'

        cur.execute(
            "UPDATE Users SET Username = ? WHERE UserId = ?",
            (username, user_id)
        )
        conn.commit()

    return True, None