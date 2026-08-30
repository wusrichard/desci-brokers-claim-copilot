"""User 資料列 → trustagent 的 Principal / Grant,並組出一個 TrustAgent。

現在的 CLI:build_principal() 永遠回傳阮氏梅,build_agency_officer() 寫死兩個人。
後端:誰登入,Principal 就是誰;授權從 grants 表讀。

情境仍然用 scenarios.migrant_claim(主線),工具、驗證器都照它的。
"""

from datetime import datetime, timedelta, timezone

from trustagent import Grant, Principal, TrustAgent
from scenarios import migrant_claim

from .audit_store import SqliteAuditLog, load_audit_key

WORKER_SCOPES = {"claim_prep", "employer_record"}   # 移工本人的預設授權
COLLAB_SCOPES = {"claim_prep"}                      # 協作者(仲介承辦人)預設較窄
EMPLOYER_SCOPES = {                                  # 雇主只處理公司掌握的資料
    "employment_confirm",
    "employer_evidence",
    "employer_insurance",
    "case_status_limited",
}
DELEGATABLE_SCOPES = {"claim_prep"}                # 只委派理賠協作；操作紀錄限本人


def _parse_dt(text):
    if not text:
        return None
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def principal_from_user(row) -> Principal:
    """組織承辦人會帶 acting_for / org_lei / ECR → 每次操作先驗代理關係。"""
    return Principal(
        id="{}:{}".format(row["role"], row["id"]),
        display_name=row["display_name"],
        kind="person",
        acting_for=row["acting_for"],
        org_lei=row["org_lei"],
        role_credential=row["role_credential"],
    )


def grant_from_row(row, principal: Principal) -> Grant:
    return Grant(
        id=row["id"],
        principal=principal,
        purpose=row["purpose"],
        scopes=set(row["scopes"].split(",")) if row["scopes"] else set(),
        expires_at=_parse_dt(row["expires_at"]),
        revoked_at=_parse_dt(row["revoked_at"]),
    )


def build_agent(conn, case_id: str, user_row, grant_row) -> TrustAgent:
    """每個 request 現組一個 agent:呼叫者的 Principal + 他在本案的 Grant + 本案的稽核鏈。

    grant_row 為 None 時,agent.grant 為 None → 政策閘回 NO_GRANT(引擎自己處理)。
    """
    principal = principal_from_user(user_row)
    grant = grant_from_row(grant_row, principal) if grant_row else None
    agent = TrustAgent(
        principal=principal,
        grant=grant,
        verifier=migrant_claim.build_verifier(),
        audit=SqliteAuditLog(conn, case_id, key=load_audit_key()),
    )
    agent.register_all(migrant_claim.build_tools())
    return agent


def default_expiry(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
