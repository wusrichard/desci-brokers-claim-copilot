"""機制 5 — 稽核追溯。

雜湊鏈式的唯附加紀錄：每一筆都含前一筆的雜湊，改任何一個欄位都會讓
該筆以後的鏈全部對不上。這讓 `verify` 與 `tamper` 兩個 demo 動作不需要
依賴任何外部套件——現場錄影時少一個會壞的東西。

有 `cryptography` 時額外加上 Ed25519 簽章；沒有也能跑，只是少一層。
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:  # 可選：有就簽章，沒有就只有雜湊鏈
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    _HAS_ED25519 = True
except Exception:  # pragma: no cover - 環境沒有 cryptography
    _HAS_ED25519 = False

GENESIS = "0" * 64


def _canonical(payload: Dict[str, Any]) -> bytes:
    """穩定序列化——排序鍵、不留空白。雜湊必須可重算，順序不能浮動。"""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class Entry:
    seq: int
    ts: str
    principal: str
    tool: str
    code: str
    allowed: bool
    detail: Dict[str, Any] = field(default_factory=dict)
    prev: str = GENESIS
    hash: str = ""
    sig: Optional[str] = None

    def body(self) -> Dict[str, Any]:
        """參與雜湊的部分——不含 hash 與 sig 本身。"""
        return {
            "seq": self.seq,
            "ts": self.ts,
            "principal": self.principal,
            "tool": self.tool,
            "code": self.code,
            "allowed": self.allowed,
            "detail": self.detail,
            "prev": self.prev,
        }

    def compute_hash(self) -> str:
        return hashlib.sha256(_canonical(self.body())).hexdigest()


class AuditLog:
    """唯附加的稽核紀錄。被擋下的嘗試也要留——那才是攔截有效的證據。"""

    def __init__(self) -> None:
        self.entries: List[Entry] = []
        self._key = Ed25519PrivateKey.generate() if _HAS_ED25519 else None

    @property
    def signed(self) -> bool:
        return self._key is not None

    def public_key_hex(self) -> Optional[str]:
        if self._key is None:
            return None
        raw = self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    def append(
        self,
        principal: str,
        tool: str,
        code: str,
        allowed: bool,
        detail: Optional[Dict[str, Any]] = None,
    ) -> Entry:
        prev = self.entries[-1].hash if self.entries else GENESIS
        entry = Entry(
            seq=len(self.entries) + 1,
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            principal=principal,
            tool=tool,
            code=code,
            allowed=allowed,
            detail=detail or {},
            prev=prev,
        )
        entry.hash = entry.compute_hash()
        if self._key is not None:
            entry.sig = self._key.sign(bytes.fromhex(entry.hash)).hex()
        self.entries.append(entry)
        return entry

    def verify(self) -> Tuple[bool, Optional[int], str]:
        """重走整條鏈。回傳 (是否完好, 第一個壞掉的序號, 說明)。"""
        prev = GENESIS
        for entry in self.entries:
            if entry.prev != prev:
                return False, entry.seq, "第 {} 筆的 prev 與前一筆的雜湊對不上".format(entry.seq)
            recomputed = entry.compute_hash()
            if recomputed != entry.hash:
                return False, entry.seq, "第 {} 筆內容被改過（雜湊重算不符）".format(entry.seq)
            prev = entry.hash
        return True, None, "全部 {} 筆完好".format(len(self.entries))

    def tamper(self, seq: int, field_name: str = "code", new_value: Any = "OK") -> bool:
        """故意竄改一筆，用來現場演示驗證會擋下來。只改內容、不重算雜湊。"""
        for entry in self.entries:
            if entry.seq == seq:
                setattr(entry, field_name, new_value)
                return True
        return False

    def to_json(self) -> str:
        return json.dumps([asdict(e) for e in self.entries], ensure_ascii=False, indent=2)
