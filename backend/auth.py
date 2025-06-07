# auth.py
import bcrypt

# In-memory user store for demo; replace with PostgreSQL in production
users = {}

def register_user(username: str, password: str) -> bool:
    if username in users:
        return False
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    users[username] = hashed
    return True

def authenticate_user(username: str, password: str) -> bool:
    if username not in users:
        return False
    return bcrypt.checkpw(password.encode(), users[username])
