import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class CryptoHelper:
    def __init__(self, key_str: str):
        if not key_str:
            raise ValueError("Encryption key must not be empty.")
        # Hash the key string using SHA-256 to ensure a 32-byte (256-bit) key
        self.key = hashlib.sha256(key_str.encode('utf-8')).digest()

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        # 12-byte IV for GCM mode
        iv = os.urandom(12)
        encryptor = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv),
            backend=default_backend()
        ).encryptor()
        
        ciphertext = encryptor.update(plaintext.encode('utf-8')) + encryptor.finalize()
        # Concat IV, Tag (16 bytes), and Ciphertext, then encode in base64
        encrypted_bytes = iv + encryptor.tag + ciphertext
        return base64.b64encode(encrypted_bytes).decode('utf-8')

    def decrypt(self, ciphertext_b64: str) -> str:
        if not ciphertext_b64:
            return ""
        try:
            encrypted_bytes = base64.b64decode(ciphertext_b64.encode('utf-8'))
            iv = encrypted_bytes[:12]
            tag = encrypted_bytes[12:28]
            ciphertext = encrypted_bytes[28:]
            
            decryptor = Cipher(
                algorithms.AES(self.key),
                modes.GCM(iv, tag),
                backend=default_backend()
            ).decryptor()
            
            decrypted_bytes = decryptor.update(ciphertext) + decryptor.finalize()
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")
