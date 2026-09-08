##教师账号认证：pbkdf2 口令哈希 + HMAC-SHA256 签名的 Bearer Token。
##刻意零第三方依赖（不引 python-jose），签名/验签/过期全部用标准库实现，
##既便于代码审查，也让"认证到底怎么工作"在项目里一眼可读。
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from fastapi import Header, HTTPException

##--------------------------------------------------------------------------
## 口令哈希（pbkdf2，每次带随机盐；存储格式自描述，便于以后换算法）
##--------------------------------------------------------------------------

_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return "{0}${1}${2}${3}".format(
        _PBKDF2_ALGO,
        iterations,
        _b64(salt),
        _b64(digest),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, hash_b64 = stored.split("$", 3)
        if algo != _PBKDF2_ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _unb64(salt_b64),
            int(iterations),
        )
        return hmac.compare_digest(digest, _unb64(hash_b64))
    except (ValueError, TypeError):
        return False


##--------------------------------------------------------------------------
## Token：仿 JWT 形态，header.payload.signature，HS256
##--------------------------------------------------------------------------

_TOKEN_HEADER = {"alg": "HS256", "typ": "JWT"}


class TokenError(ValueError):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(signing_input: str, secret: str) -> bytes:
    return hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()


def create_token(
    payload: dict[str, Any],
    *,
    secret: str,
    ttl_seconds: int,
) -> str:
    now = int(time.time())
    body = {
        **payload,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    header_json = json.dumps(
        _TOKEN_HEADER, separators=(",", ":"), ensure_ascii=False
    )
    payload_json = json.dumps(
        body, separators=(",", ":"), ensure_ascii=False
    )
    signing_input = "{0}.{1}".format(
        _b64(header_json.encode("utf-8")),
        _b64(payload_json.encode("utf-8")),
    )
    signature = _sign(signing_input, secret)
    return "{0}.{1}".format(signing_input, _b64(signature))


def verify_token(token: str, *, secret: str) -> dict[str, Any]:
    """验签 + 过期校验。任何一步失败都抛 TokenError。"""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
        header_raw = _unb64(header_b64)
        payload_raw = _unb64(payload_b64)
        signature = _unb64(signature_b64)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise TokenError("token 格式错误") from exc

    signing_input = "{0}.{1}".format(header_b64, payload_b64)
    expected = _sign(signing_input, secret)
    if not hmac.compare_digest(expected, signature):
        raise TokenError("token 签名校验失败")

    try:
        header = json.loads(header_raw)
        payload = json.loads(payload_raw)
    except (ValueError, TypeError) as exc:
        raise TokenError("token 载荷不是合法 JSON") from exc

    if header.get("alg") != "HS256":
        raise TokenError("不支持的签名算法")

    expires_at = int(payload.get("exp", 0))
    if expires_at <= int(time.time()):
        raise TokenError("token 已过期")

    return payload


##--------------------------------------------------------------------------
## FastAPI 依赖：从 Authorization: Bearer <token> 取出教师身份
##--------------------------------------------------------------------------

def create_require_teacher(
    secret_provider: Any,
) -> Any:
    """按 app 配置注入 secret 的鉴权依赖工厂。

    secret_provider 可以是可调用（如 lambda: settings.auth_secret），
    也可以直接传字符串；每次请求动态取，便于测试换 secret。
    """

    def dependency(
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=401,
                detail="缺少 Authorization: Bearer <token>",
            )

        secret = (
            secret_provider() if callable(secret_provider) else secret_provider
        )

        try:
            payload = verify_token(
                authorization.split(" ", 1)[1].strip(),
                secret=secret,
            )
        except TokenError as exc:
            raise HTTPException(
                status_code=401,
                detail=str(exc),
            ) from exc

        if payload.get("role") != "teacher":
            raise HTTPException(
                status_code=403,
                detail="该接口仅教师可访问",
            )
        return payload

    return dependency
