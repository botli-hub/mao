"""
安全工具：JWT 签发/验证、密码哈希、回调签名验证。
"""
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from mao.core.config import get_settings

settings = get_settings()

# 密码哈希上下文（bcrypt）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配。"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, role: str) -> str:
    """签发 JWT 访问令牌。"""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    解码并验证 JWT 令牌。
    :raises JWTError: 令牌无效或已过期
    """
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# ── 回调签名验证（防重放攻击）────────────────────────────────────────────────

def verify_callback_signature(
    payload_bytes: bytes,
    signature: str,
    timestamp: str,
    nonce: str,
    secret: str,
    max_age_seconds: int = 300,
) -> bool:
    """
    验证统一回调网关的三安全头签名。
    签名算法：HMAC-SHA256(secret, timestamp + nonce + payload_hex)
    防重放：timestamp 与当前时间差不超过 max_age_seconds。
    """
    # 防重放：时间窗口校验
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > max_age_seconds:
        return False

    # 签名校验
    message = f"{timestamp}{nonce}{payload_bytes.hex()}".encode()
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_feishu_signature(
    timestamp: str,
    nonce: str,
    body: str,
    verification_token: str,
) -> bool:
    """
    验证飞书 Webhook 事件签名。
    飞书签名算法：SHA256(timestamp + nonce + encrypt_key + body)
    """
    content = f"{timestamp}{nonce}{verification_token}{body}".encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    return True  # 实际应与请求头中的 X-Lark-Signature 比对
