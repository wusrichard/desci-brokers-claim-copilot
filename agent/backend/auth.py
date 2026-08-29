"""最小認證 — 只用標準庫,刻意不引入 passlib / PyJWT。

理由與 trustagent.llm 相同:維持「clone 下來就能讀懂」的性質。
密碼用 pbkdf2-hmac-sha256 加鹽;session token 是 base64(payload) + HMAC 簽章。
夠一天的 demo 用,不是為了扛production。
"""

import base64
import hashlib
import hmac
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS_DIR = os.path.join(HERE, ".secrets")
SECRET_PATH = os.path.join(SECRETS_DIR, "server_secret")

PBKDF2_ROUNDS = 200_000
TOKEN_TTL_SECONDS = 12 * 3600


# ---- server secret（簽 token 用）------------------------------------------
def server_secret() -> bytes:
    os.makedirs(SECRETS_DIR, exist_ok=True)
    if not os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "w", encoding="utf-8") as fh:
            fh.write(os.urandom(32).hex())
    with open(SECRET_PATH, encoding="utf-8") as fh:
        return bytes.fromhex(fh.read().strip())


# ---- 密碼 ----------------------------------------------------------------
def hash_password(plain: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex() + "$" + dk.hex()


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS
    )
    return hmac.compare_digest(dk.hex(), dk_hex)


# ---- session token -----------------------------------------------------
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def make_token(user_id: int) -> str:
    payload = json.dumps({"uid": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS})
    body = _b64u(payload.encode("utf-8"))
    sig = _b64u(hmac.new(server_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


def read_token(token: str):
    """回傳 user_id;無效或過期回傳 None。"""
    try:
        body, sig = token.split(".")
        expected = _b64u(
            hmac.new(server_secret(), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64u_decode(body))
        if payload["exp"] < time.time():
            return None
        return int(payload["uid"])
    except Exception:
        return None
