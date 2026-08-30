"""把六項機制組起來的執行迴圈。

TrustAgent 不知道自己在做健檢還是理賠——情境由外面注入。
換情境 = 換一組 tools + grant + 資料，引擎一行不動。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit import AuditLog
from .gate import PolicyGate
from .models import ActionResult, Decision, Grant, Principal, Tool
from .verifier import Verifier


class TrustAgent:
    def __init__(
        self,
        principal: Principal,
        grant: Optional[Grant] = None,
        verifier: Optional[Verifier] = None,
        audit: Optional[AuditLog] = None,
    ) -> None:
        self.principal = principal
        self.grant = grant
        self.gate = PolicyGate(grant)
        self.verifier = verifier
        self.audit = audit or AuditLog()
        self.tools: Dict[str, Tool] = {}
        self._delegation_evidence: Dict[str, Any] = {}

    # ---- 機制 3：工具註冊 ----------------------------------------------
    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def register_all(self, tools: List[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def capabilities(self) -> List[Tool]:
        return sorted(self.tools.values(), key=lambda t: (t.risk == "high", t.name))

    # ---- 機制 6：撤銷 --------------------------------------------------
    def revoke_grant(self) -> None:
        if self.grant is not None:
            self.grant.revoke()
            self.audit.append(
                str(self.principal), "-", "GRANT_REVOKED_BY_PRINCIPAL", False,
                {"grant": self.grant.id},
            )

    # ---- 出處驗證 ------------------------------------------------------
    def verify_provenance(self, said: str):
        if self.verifier is None:
            return None
        result = self.verifier.verify(said)
        self.audit.append(
            str(self.principal),
            "verify_provenance",
            "PROVENANCE_OK" if result.ok else "PROVENANCE_FAIL",
            result.ok,
            {"said": said, "verifier": self.verifier.name, "detail": result.detail},
        )
        return result

    # ---- 組織對個人授權（Corppass 模式）---------------------------------
    def _check_delegation(self) -> Optional[Decision]:
        """代表組織行動的人，其代理關係必須先被憑證證明。

        這一步刻意排在政策閘之前：連「你是誰的人」都還沒確認，
        談授權範圍沒有意義。
        """
        p = self.principal
        self._delegation_evidence = {}
        if not p.is_delegated:
            return None
        if self.verifier is None or not p.role_credential:
            return Decision(
                False, Decision.ROLE_NOT_VERIFIED,
                "{} 宣稱代表 {}，但沒有可驗證的角色憑證".format(p.display_name, p.acting_for),
            )
        result = self.verifier.verify(p.role_credential)
        self._delegation_evidence = {
            "acting_for": p.acting_for,
            "org_lei": p.org_lei,
            "role_credential": p.role_credential,
            "verifier": self.verifier.name,
            "verification_detail": result.detail,
        }
        if result.unavailable:
            return Decision(
                False, Decision.VERIFIER_UNAVAILABLE,
                "目前無法驗證 {} 代表 {} 的角色；為保護案件已拒絕代理操作：{}".format(
                    p.display_name, p.acting_for, result.detail
                ),
            )
        if not result.ok:
            return Decision(
                False, Decision.ROLE_NOT_VERIFIED,
                "{} 的角色憑證驗證失敗：{}".format(p.display_name, result.detail),
            )
        return None

    # ---- 主迴圈：每次動作都先過閘、後留紀錄 ------------------------------
    def act(self, tool_name: str, confirmed: bool = False, **kwargs: Any) -> ActionResult:
        tool = self.tools.get(tool_name)

        if tool is None:
            decision = Decision(False, Decision.UNKNOWN_TOOL, "沒有註冊這個工具")
            entry = self.audit.append(str(self.principal), tool_name, decision.code, False,
                                      {"reason": decision.reason})
            return ActionResult(tool_name, decision, None, entry.seq)

        decision = self._check_delegation()
        if decision is not None:
            entry = self.audit.append(str(self.principal), tool_name, decision.code, False,
                                      {"reason": decision.reason,
                                       "acting_for": self.principal.acting_for,
                                       "role_credential": self.principal.role_credential,
                                       "verifier": getattr(self.verifier, "name", "none")})
            return ActionResult(tool_name, decision, None, entry.seq)

        decision = self.gate.check(tool, confirmed=confirmed)

        detail: Dict[str, Any] = {
            "scope": tool.required_scope,
            "risk": tool.risk,
            "reason": decision.reason,
        }
        if self._delegation_evidence:
            detail["delegation"] = dict(self._delegation_evidence)
        if confirmed:
            detail["human_confirmed"] = True

        # 被擋下來的嘗試「也要」進紀錄——那是攔截有效的證據
        if not decision.allowed:
            entry = self.audit.append(str(self.principal), tool_name, decision.code, False, detail)
            return ActionResult(tool_name, decision, None, entry.seq)

        value = tool.handler(**kwargs) if tool.handler else None
        detail["result_keys"] = sorted(value.keys()) if isinstance(value, dict) else None
        entry = self.audit.append(str(self.principal), tool_name, decision.code, True, detail)
        return ActionResult(tool_name, decision, value, entry.seq)
