"""Contraseñas y tokens de sesión, con la biblioteca estándar.

``scrypt`` es memory-hard y viene en ``hashlib``: alcanza para guardar contraseñas sin
sumar una dependencia. Los tokens son opacos y se guardan hasheados, así que una copia de
la base no sirve para hacerse pasar por nadie, y cerrar sesión es borrar una fila.
"""

import hashlib
import hmac
import secrets

# Parámetros de scrypt: ~16 MB de memoria por verificación.
_N, _R, _P = 2**14, 8, 1
_SALT_BYTES = 16
_KEY_BYTES = 32
TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """``scrypt$<salt>$<clave>``, con la sal por contraseña."""

    salt = secrets.token_bytes(_SALT_BYTES)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_BYTES)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Comparación en tiempo constante; un hash ilegible es simplemente un fallo."""

    try:
        algorithm, salt_hex, key_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(key_hex)
    except ValueError:
        return False
    candidate = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=len(expected)
    )
    return hmac.compare_digest(candidate, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """El token viaja una sola vez; en la base queda solo su hash."""

    return hashlib.sha256(token.encode()).hexdigest()
