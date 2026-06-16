# -*- coding: utf-8 -*-
"""
加密模块

提供 AES-256-GCM 加密/解密、PBKDF2 密钥派生和 argon2 密码哈希功能。
"""

import os
import base64
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)

# AES-256-GCM 加密
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    logger.warning('cryptography 库未安装，加密功能不可用。请运行: pip install cryptography')

# Argon2 密码哈希
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    HAS_ARGON2 = True
except ImportError:
    HAS_ARGON2 = False
    logger.warning('argon2-cffi 库未安装，使用 PBKDF2 作为密码哈希替代方案')


class NoteEncryption:
    """AES-256-GCM 加密引擎"""

    SALT_LENGTH = 16  # 字节
    KEY_LENGTH = 32   # 256 bits
    PBKDF2_ITERATIONS = 480000

    @staticmethod
    def is_available() -> bool:
        return HAS_CRYPTOGRAPHY

    # ── 密钥派生 ──────────────────────────────────────────

    @classmethod
    def derive_key(cls, password: str, salt: bytes) -> bytes:
        """
        使用 PBKDF2-HMAC-SHA256 从密码派生 256-bit 密钥

        Args:
            password: 用户密码
            salt: 随机盐值

        Returns:
            32 字节密钥
        """
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError('cryptography 库未安装')

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=cls.KEY_LENGTH,
            salt=salt,
            iterations=cls.PBKDF2_ITERATIONS,
        )
        return kdf.derive(password.encode('utf-8'))

    @classmethod
    def generate_salt(cls) -> bytes:
        """生成随机盐值"""
        return os.urandom(cls.SALT_LENGTH)

    # ── 加密/解密 ──────────────────────────────────────────

    @classmethod
    def encrypt_content(cls, plaintext: str, password: str) -> dict:
        """
        加密内容

        Args:
            plaintext: 明文内容
            password: 用户密码

        Returns:
            dict: {
                'encrypted': base64 编码的密文,
                'salt': base64 编码的盐值,
                'key_hash': 密码验证哈希
            }
        """
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError('cryptography 库未安装')

        salt = cls.generate_salt()
        key = cls.derive_key(password, salt)

        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

        # 组合 nonce + ciphertext 一起存储
        combined = nonce + ciphertext

        return {
            'encrypted': base64.b64encode(combined).decode('ascii'),
            'salt': base64.b64encode(salt).decode('ascii'),
            'key_hash': cls.hash_password(password, salt),
        }

    @classmethod
    def decrypt_content(cls, encrypted: str, salt_b64: str, password: str) -> str:
        """
        解密内容

        Args:
            encrypted: base64 编码的密文（含 nonce）
            salt_b64: base64 编码的盐值
            password: 用户密码

        Returns:
            解密后的明文

        Raises:
            ValueError: 密码错误或数据损坏
        """
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError('cryptography 库未安装')

        try:
            salt = base64.b64decode(salt_b64)
            key = cls.derive_key(password, salt)

            combined = base64.b64decode(encrypted)
            nonce = combined[:12]
            ciphertext = combined[12:]

            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        except Exception as e:
            raise ValueError(f'解密失败: {e}')

    # ── 密码哈希 ──────────────────────────────────────────

    @classmethod
    def hash_password(cls, password: str, salt: bytes) -> str:
        """
        生成密码验证哈希

        优先使用 argon2id，回退到 PBKDF2

        Returns:
            哈希字符串
        """
        if HAS_ARGON2:
            ph = PasswordHasher()
            return ph.hash(password)
        else:
            # PBKDF2 回退
            dk = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                cls.PBKDF2_ITERATIONS,
                dklen=32
            )
            return base64.b64encode(dk).decode('ascii')

    @classmethod
    def verify_password(cls, password: str, hash_str: str, salt: bytes = None) -> bool:
        """
        验证密码

        Args:
            password: 待验证密码
            hash_str: 存储的哈希字符串
            salt: 盐值（PBKDF2 模式需要）

        Returns:
            True 表示密码正确
        """
        if HAS_ARGON2 and hash_str.startswith('$argon2'):
            try:
                ph = PasswordHasher()
                return ph.verify(hash_str, password)
            except VerifyMismatchError:
                return False
            except Exception:
                return False
        else:
            # PBKDF2 回退
            if salt is None:
                return False
            dk = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                cls.PBKDF2_ITERATIONS,
                dklen=32
            )
            computed = base64.b64encode(dk).decode('ascii')
            return hmac.compare_digest(computed, hash_str)

    @classmethod
    def hash_master_password(cls, password: str) -> dict:
        """
        哈希主密码

        Returns:
            dict: {'hash': str, 'salt': base64_str}
        """
        salt = cls.generate_salt()
        hash_str = cls.hash_password(password, salt)
        return {
            'hash': hash_str,
            'salt': base64.b64encode(salt).decode('ascii'),
        }
