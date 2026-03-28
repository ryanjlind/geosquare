import uuid

def create_user(cur):
    username = f'anon_{uuid.uuid4().hex[:12]}'

    cur.execute("""
        INSERT INTO dbo.Users (Username)
        OUTPUT inserted.UserId
        VALUES (?)
    """, username)

    return cur.fetchone()

def get_user_by_id(cur, user_id: int):
    cur.execute("""
        SELECT TOP 1
            UserId
        FROM dbo.Users
        WHERE UserId = ?
    """, user_id)
    return cur.fetchone()
