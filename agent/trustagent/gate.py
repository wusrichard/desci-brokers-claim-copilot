"""機制 2/3/4/6 — 政策閘。

Agent 呼叫任何工具之前都要先過這裡。檢查順序本身就是設計聲明：
撤銷 > 到期 > 範圍 > 風險。撤銷排第一，因為它必須立即生效。
"""

from datetime import datetime, timezone
from typing import Optional

from .models import Decision, Grant, Tool


class PolicyGate:
    def __init__(self, grant: Optional[Grant] = None) -> None:
        self.grant = grant

    def check(self, tool: Tool, now: Optional[datetime] = None, confirmed: bool = False) -> Decision:
        now = now or datetime.now(timezone.utc)

        if self.grant is None:
            return Decision(False, Decision.NO_GRANT, "沒有任何有效授權，Agent 不代表任何人")

        if self.grant.is_revoked():
            return Decision(
                False,
                Decision.REVOKED,
                "授權已於 {} 撤銷，Agent 立即失去存取權".format(
                    self.grant.revoked_at.isoformat(timespec="seconds")
                ),
            )

        if self.grant.is_expired(now):
            return Decision(
                False,
                Decision.EXPIRED,
                "授權已於 {} 到期".format(self.grant.expires_at.isoformat(timespec="seconds")),
            )

        if not self.grant.covers(tool.required_scope):
            return Decision(
                False,
                Decision.OUT_OF_SCOPE,
                "本次授權未涵蓋 '{}'，超出 {} 的授權範圍".format(
                    tool.required_scope, self.grant.principal.display_name
                ),
            )

        if tool.is_high_risk() and not confirmed:
            return Decision(
                False,
                Decision.NEEDS_CONFIRMATION,
                "高風險動作，須經人工確認後才能執行",
            )

        return Decision(True, Decision.OK, "在授權範圍內")
