"""Core types: 代表誰、授權、工具、決策。

這一層刻意不知道任何情境。健檢綠燈或醫療理賠，用的都是同一組型別。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

LOW = "low"
HIGH = "high"


@dataclass(frozen=True)
class Principal:
    """機制 1 — Agent 代表誰。

    acting_for 是新加坡 Corppass 模式的對應：承辦人不是以自己的名義行動，
    而是「代表某個組織」。驗證的重點因此不只是「這家公司是真的」，
    而是「這個人**確實被那家公司授權**處理這件事」——role_credential 就是那張憑證。
    """

    id: str
    display_name: str
    kind: str = "person"
    acting_for: Optional[str] = None       # 代表哪個組織（顯示名）
    org_lei: Optional[str] = None          # 該組織的 LEI
    role_credential: Optional[str] = None  # 證明代理關係的 ECR 憑證 SAID

    @property
    def is_delegated(self) -> bool:
        return self.acting_for is not None

    def __str__(self) -> str:
        if self.is_delegated:
            return "{}（代表 {}）<{}>".format(self.display_name, self.acting_for, self.id)
        return "{} <{}>".format(self.display_name, self.id)


@dataclass
class Grant:
    """機制 2 — 授權範圍與期限；機制 6 — 撤銷。

    scopes 是這次授權放行的資料/用途標籤。工具要求的 scope 不在裡面就不放行。
    """

    id: str
    principal: Principal
    purpose: str
    scopes: Set[str]
    expires_at: datetime
    revoked_at: Optional[datetime] = None

    def revoke(self, now: Optional[datetime] = None) -> None:
        self.revoked_at = now or datetime.now(timezone.utc)

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or datetime.now(timezone.utc)) >= self.expires_at

    def covers(self, scope: str) -> bool:
        return scope in self.scopes


@dataclass
class Tool:
    """機制 3 — 可執行動作。

    每個工具自己宣告需要什麼 scope、風險多高。高風險工具一律先攔截。
    """

    name: str
    description: str
    required_scope: str
    risk: str = LOW
    handler: Optional[Callable[..., Any]] = None

    def is_high_risk(self) -> bool:
        return self.risk == HIGH


@dataclass
class Decision:
    """政策閘的判定結果。code 會原樣寫進稽核紀錄。"""

    allowed: bool
    code: str
    reason: str

    OK = "OK"
    NO_GRANT = "NO_GRANT"
    REVOKED = "GRANT_REVOKED"
    EXPIRED = "GRANT_EXPIRED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    NEEDS_CONFIRMATION = "NEEDS_HUMAN_CONFIRMATION"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    ROLE_NOT_VERIFIED = "ROLE_NOT_VERIFIED"
    VERIFIER_UNAVAILABLE = "VERIFIER_UNAVAILABLE"


@dataclass
class ActionResult:
    """一次 act() 的完整結果，含決策、回傳值與稽核收據序號。"""

    tool: str
    decision: Decision
    value: Any = None
    receipt_seq: Optional[int] = None

    @property
    def blocked(self) -> bool:
        return not self.decision.allowed
