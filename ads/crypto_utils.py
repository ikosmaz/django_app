import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _build_key():
    raw_key = getattr(settings, 'MESSAGE_ENCRYPTION_KEY', None)
    key_source = raw_key or settings.SECRET_KEY

    digest = hashlib.sha256(key_source.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet():
    return Fernet(_build_key())


def encrypt_text(plain_text):
    token = _fernet().encrypt(plain_text.encode('utf-8'))
    return token.decode('utf-8')


def decrypt_text(cipher_text):
    try:
        plain = _fernet().decrypt(cipher_text.encode('utf-8'))
        return plain.decode('utf-8')
    except (InvalidToken, AttributeError, ValueError):
        return '[Unreadable encrypted message]'
