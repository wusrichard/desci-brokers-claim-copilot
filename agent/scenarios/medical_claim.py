"""情境：個人醫療理賠協作 Agent。

⚠️ 假資料聲明：所有回傳值皆為寫死的固定值，未呼叫模型、未做密碼學驗證。詳見 FIXTURES.md。

存在的目的是證明引擎與情境確實分離——這個檔案跟 health_pass.py 結構完全相同，
只是換了角色、換了 scope、換了工具。trustagent/ 底下一行都沒改。
"""

from datetime import datetime, timedelta, timezone

from trustagent import Grant, HIGH, LOW, MockVerifier, Principal, Tool

CASE_ID = "CLM-2026-0810"
HOSPITAL_LEI = "8945001XYZTAIWAN0024"   # [假資料] 虛構法人；檢查碼有效
CREDENTIAL_SAID = "EClm0810_diagnosis_acdc_said"

LOCAL_ONLY = ["id_number", "full_medical_history", "unrelated_diagnoses", "psych_records"]


def read_claim_draft():
    return {
        "case_id": CASE_ID,
        "policy_matched": ["住院日額 A", "手術定額 B"],
        "estimated_amount": "NT$ 48,000",
        "missing_documents": ["診斷證明正本", "費用收據"],
        "status": "DRAFT",
    }


def compare_policy_terms():
    return {"clauses_checked": 12, "conflicts": 0, "cited_sources": ["A-3.2", "B-5.1"]}


def submit_to_insurer(insurer: str = "XX 人壽"):
    """不可逆：正式送件。一律先攔截等保戶確認。"""
    return {"submitted_to": insurer, "irreversible": True}


def read_full_history():
    """授權外：調閱完整病歷（含與本次理賠無關的部分）。"""
    return {k: "（合成值）" for k in LOCAL_ONLY}


def build_tools():
    return [
        Tool("read_claim_draft", "產出理賠草案與缺件清單", "claim_prep", LOW, read_claim_draft),
        Tool("compare_policy_terms", "比對保單條款", "claim_prep", LOW, compare_policy_terms),
        Tool("submit_to_insurer", "正式送出理賠申請（不可逆）", "claim_prep", HIGH, submit_to_insurer),
        Tool("read_full_history", "調閱完整病歷", "full_medical", HIGH, read_full_history),
    ]


def build_principal():
    return Principal(id="policyholder:wang-da-ming", display_name="王大明", kind="person")


def build_grant(principal, days_valid: int = 30):
    return Grant(
        id="grant-clm-0810",
        principal=principal,
        purpose="僅本次住院診斷與收據",
        scopes={"claim_prep"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=days_valid),
    )


def build_verifier():
    v = MockVerifier()
    v.register(CREDENTIAL_SAID, "仁德綜合醫院（LEI {}）".format(HOSPITAL_LEI))
    return v


SCENARIO = {
    "name": "個人醫療理賠協作 Agent",
    "case_id": CASE_ID,
    "credential_said": CREDENTIAL_SAID,
    "local_only_fields": LOCAL_ONLY,
}
