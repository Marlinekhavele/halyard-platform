"""Password hashing with bcrypt."""

import bcrypt


def hash_password(password: str) -> str:
    """Hashes a password with a fresh salt.

    Args:
        password: The plain-text password.

    Returns:
        The bcrypt hash.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Checks a password against a stored hash.

    Args:
        password: The plain-text password.
        hashed: The stored bcrypt hash.

    Returns:
        True if they match; False if not or if the hash is malformed.
    """
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False
