"""情境：移工職安 Health Pass（現為理賠情境中的一項證據，非主軸）。

⚠️ 假資料聲明：本檔案所有工具函式回傳的都是寫死的固定值。
   沒有呼叫語言模型、沒有執行密碼學驗證、沒有讀取真實健檢報告。
   `_report_fingerprint()` 是唯一真的計算——它對合成報告檔算 sha256。
   詳見 FIXTURES.md。

情境：移工職安 Health Pass。

這個檔案是「換皮」的那一層——它只宣告 principal、grant、工具與資料。
引擎（trustagent/）完全不知道健檢是什麼。

要換成醫療理賠情境，複製這個檔案改內容即可，引擎一行不動。
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from trustagent import Grant, HIGH, LOW, MockVerifier, Principal, Tool

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "health_pass_scenario"))

CASE_ID = "HP-2026-0142"
HOSPITAL_LEI = "8945001XYZTAIWAN0024"   # [假資料] 虛構法人；檢查碼已修正為有效
CREDENTIAL_SAID = "EHp0142_healthpass_acdc_said"
DOCTOR_ECR_SAID = "EDoc_chen_ecr_said"

# 宣告式遮罩：哪些欄位永遠不得外送。刻意不讓 LLM 決定——規則不會幻覺。
LOCAL_ONLY = [
    "arc_number",
    "passport_number",
    "tb_xray_result",
    "hbv_status",
    "hiv_result",
    "medical_history",
    "blood_pressure",
    "vision_detail",
]


def _load_local_only():
    path = os.path.join(DATA, "local_only.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {k: "（合成值）" for k in LOCAL_ONLY}


def _report_fingerprint() -> str:
    path = os.path.join(DATA, "input.original.example.txt")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    return hashlib.sha256(b"synthetic-report").hexdigest()


# ---- 工具實作 ----------------------------------------------------------
# 每個 handler 都只回傳「這個角色有權看到的東西」。


def read_green_light():
    """稽核方拿得到的全部內容。注意：沒有任何一個檢查值。"""
    return {
        "case_id": CASE_ID,
        "fitness_verdict": "適合高溫作業環境",
        "no_notifiable_disease": True,
        "check_date": "2026-08-20",
        "next_due_date": "2027-08-20",
        "issuing_hospital_LEI": HOSPITAL_LEI,
        "report_sha256": _report_fingerprint()[:16] + "...",
        "status_light": "GREEN",
    }


def explain_to_worker(lang: str = "vi"):
    """移工端：用母語解釋被判定了什麼、這張綠燈會給誰看。"""
    texts = {
        "vi": "Kết quả khám sức khỏe của bạn: đủ điều kiện làm việc môi trường nhiệt độ cao. "
              "Chỉ kết luận này được chia sẻ với kiểm toán viên — hồ sơ bệnh án không rời khỏi nhà máy.",
        "zh": "你的健檢結果：適合高溫作業環境。稽核員只會看到這個結論，病歷不會離開工廠。",
    }
    return {"lang": lang, "message": texts.get(lang, texts["zh"])}


def aggregate_for_brand():
    """品牌戰情室：聚合值，無個人。數字來自憑證狀態，不是模型估計。"""
    return {
        "suppliers_scanned": 45,
        "green_coverage": "88%",
        "amber_cases": 1,
        "contains_personal_data": False,
    }


def read_raw_report():
    """授權範圍外：調閱原始病歷。scope 就擋掉了，不必談風險。"""
    return _load_local_only()


def share_with_new_auditor(auditor: str = "SGS-TW-0417"):
    """授權範圍內、但高風險：把綠燈揭露給一個新的稽核方。

    這是不可逆動作——揭露出去就收不回來，所以即使在授權範圍內
    也一律先攔截，等人工確認。這一格才是機制 4 的正身。
    """
    return {"disclosed_to": auditor, "payload": "GREEN + hash + expiry", "irreversible": True}


def build_tools():
    return [
        Tool(
            name="read_green_light",
            description="讀取綠燈判定（稽核用）",
            required_scope="rba_audit",
            risk=LOW,
            handler=read_green_light,
        ),
        Tool(
            name="explain_to_worker",
            description="用移工母語解釋權益",
            required_scope="worker_self",
            risk=LOW,
            handler=explain_to_worker,
        ),
        Tool(
            name="aggregate_for_brand",
            description="品牌 ESG 戰情室聚合狀態",
            required_scope="rba_audit",
            risk=LOW,
            handler=aggregate_for_brand,
        ),
        Tool(
            name="share_with_new_auditor",
            description="把綠燈揭露給新的稽核方（不可逆）",
            required_scope="rba_audit",
            risk=HIGH,
            handler=share_with_new_auditor,
        ),
        Tool(
            name="read_raw_report",
            description="調閱原始健檢報告（含敏感醫療資料）",
            required_scope="raw_medical",
            risk=HIGH,
            handler=read_raw_report,
        ),
    ]


def build_principal():
    return Principal(id="worker:nguyen-thi-mai", display_name="阮氏梅 Nguyen Thi Mai", kind="person")


def build_grant(principal, days_valid: int = 365):
    """移工本人勾選的授權：範圍 + 期限。注意 raw_medical 不在裡面。"""
    return Grant(
        id="grant-hp-0142",
        principal=principal,
        purpose="僅供 RBA 職安稽核查驗",
        scopes={"rba_audit", "worker_self"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=days_valid),
    )


def build_verifier():
    v = MockVerifier()
    v.register(CREDENTIAL_SAID, "仁德綜合醫院（LEI {}）".format(HOSPITAL_LEI))
    v.register(DOCTOR_ECR_SAID, "陳志明 醫師 ECR")
    return v


SCENARIO = {
    "name": "移工職安 Health Pass",
    "case_id": CASE_ID,
    "credential_said": CREDENTIAL_SAID,
    "doctor_ecr_said": DOCTOR_ECR_SAID,
    "build_principal": build_principal,
    "build_grant": build_grant,
    "build_tools": build_tools,
    "build_verifier": build_verifier,
    "local_only_fields": LOCAL_ONLY,
}
