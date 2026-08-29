"""情境：移工職災保險 Claim Copilot（依 0829 Concept deck 主軸）。

流程 Verify → Understand → Match → Claim → Track → Record。


═══════════════════════════════════════════════════════════════════════
 ⚠️ 假資料聲明 — 交件與上台前務必讀完這一段
═══════════════════════════════════════════════════════════════════════

本檔案的工具函式**只有一個會做真實運算**，其餘全是寫死的固定值（fixture）。

  ✅ 真的：`understand_incident()`
     設定 OPENROUTER_API_KEY 後，會實際呼叫模型把母語敘述抽成結構化欄位。
     沒有金鑰或呼叫失敗時退回固定值，並在回傳的 `source` 欄位標明是哪一種。
     轉人工用**欄位完整性**判斷，不是信心分數門檻。

  ❌ 假的：其餘全部
     1. 沒有任何密碼學驗證被執行。
        `MockVerifier` 只是一張查表，回傳「這個 SAID 我認得」。
        它沒有重算 SAID、沒有驗簽章、沒有走信任鏈、沒有查撤銷紀錄。
        真正的驗證要換成 `VleiVerifier`，由 vlei-sandbox 執行。

     2. 保障項目清單是人工編寫的示意內容。
        但 `match_coverage()` 的**引用出處是真的**——從本地知識庫
        `knowledge/laws.json` 撈，並附知識庫版本與 sha256。
        知識庫未填時 citations 為空並註明原因，**不會編造條號**。

     3. 身份與聘僱關係、缺件清單、案件進度、送件結果，全部是固定值。

     4. 案號、公司名、人名、SAID 皆為虛構（LEI 的檢查碼則是有效格式）。

上述限制在 Demo Day 都可能被評審追問。**主動說明比被問出來好**——
評審扣的是「宣稱與實作不符」的分，不是「這是原型」的分。
規則第十節明訂「偽造 Demo 結果或數據」會取消資格，界線就在**有沒有講清楚**。

每個函式各自的假資料細節，寫在該函式的 docstring 裡，並登記於 FIXTURE_NOTES。
`run.py claim` 執行時會把這些標注一併印在畫面上，所以錄影裡也看得到。


═══════════════════════════════════════════════════════════════════════
 自訂名詞聲明
═══════════════════════════════════════════════════════════════════════

以下名稱是**本專案自行命名**的程式識別碼，不是 GLEIF、ISO 或 RBA 的標準術語，
講述時請不要當成業界規格：

  * scope 名稱 `claim_prep` / `employer_record` / `full_medical`
  * 決策碼 `ROLE_NOT_VERIFIED`（其餘決策碼同理）

沿用自外部來源、可以照講的名詞：

  * LEI / vLEI / LE 憑證 / ECR / OOR / QVI / SAID / ACDC / KERI / TEL — GLEIF 與 ISO 17442
  * Verify → Understand → Match → Claim → Track → Record — 0829 Concept deck
  * worker protection record — 0829 Concept deck 的用語（非業界標準術語）
  * Corppass 的 organization-to-person authorization — 三國比較研究引述新加坡制度
"""

import os
from datetime import datetime, timedelta, timezone

from trustagent import knowledge, llm
from trustagent import Grant, HIGH, LOW, MockVerifier, Principal, Tool

CASE_ID = "WIC-2026-0826-0117"          # [假資料] 虛構案號

# --- 法人與憑證 ---------------------------------------------------------
# [假資料] 以下公司名稱與 LEI 全部為虛構。
# 但 LEI 的「格式」是真的：20 字元，且已通過 ISO 17442-1 的 mod 97 檢查碼。
# 這一點很重要——vlei-sandbox 會拒絕未通過檢查碼的 LEI，
# 用隨手編的字串明天發憑證時會直接被擋下來。
AGENCY_NAME = "宏泰人力仲介股份有限公司"
AGENCY_LEI = "8945002HONGTAI00TW15"     # [假資料] 虛構法人，檢查碼有效
EMPLOYER_NAME = "晶宏電子股份有限公司"
EMPLOYER_LEI = "8945004JINGHONG0TW26"   # [假資料] 虛構法人，檢查碼有效
HOSPITAL_NAME = "仁德綜合醫院"
HOSPITAL_LEI = "8945001XYZTAIWAN0024"   # [假資料] 沿用原情境包，檢查碼已修正
INSURER_NAME = "富邦人壽"
INSURER_LEI = "8945003FUBONLIFE0T38"    # [假資料] 虛構法人，檢查碼有效

# ✅ 真的 SAID —— 由 vlei-sandbox 的 `issue` 指令實際產生。
# 信任鏈：GLEIF → QVI → 宏泰人力仲介 LE → 承辦人 ECR。
# 林志豪的 ECR 已用 `revoke` 撤銷（模擬離職），驗證時整條鏈會斷。
# 重建方式見 ../vlei-sandbox/，或 agent/README.md 的「重建憑證鏈」。
AGENCY_LE_SAID = "FJVxCV4Q6cnYBpzMFpNGcOR3S0GHr7VHW5P7K-lh3w3C"
ECR_ACTIVE = "FE0cGyO291Ljq9OwVUsmPtWk-zY1c9QKRNM0J_OslfQE"    # 陳美玲，在職
ECR_REVOKED = "FOWvN6Yzq-XhDSQZx5bgL9k3SvgX65wesZF2RUBfeqWa"    # 林志豪，已撤銷
HEALTHPASS_SAID = "EHp0142_healthpass_acdc_said"
DIAGNOSIS_SAID = "EDiag_0826_acdc_said"

# 永不外送：與本次職災無關的個人與醫療資料（個資法的比例原則）
LOCAL_ONLY = [
    "arc_number",
    "passport_number",
    "hbv_status",
    "hiv_result",
    "psychiatric_history",
    "unrelated_diagnoses",
    "family_medical_history",
]

# 每個工具的假資料標注。run.py 會把它印在畫面上，讓錄影裡也看得到。
FIXTURE_NOTES = {
    "verify_employment": "回傳固定值。未實際呼叫 vLEI 驗證，聘僱關係也未查任何來源系統。",
    "understand_incident": "有金鑰時為模型即時抽取；無金鑰時退回固定值（回傳的 source 欄位會標明是哪一種）。",
    "match_coverage": "保障項目為人工編寫示意；引用出處則來自本地知識庫（未填時 citations 為空，不編造條號）。",
    "list_missing_documents": "缺件清單為固定值，未與任何文件管理系統核對。",
    "track_status": "案件進度為固定值，未連接任何案件系統。",
    "build_protection_record": "紀錄內容為固定值；引用的憑證 SAID 亦為假值。",
    "submit_claim": "不會真的送件到任何保險公司，僅回傳一個成功訊息。",
    "read_full_medical_history": "回傳佔位字串，本來就不該被放行。",
}


# ============ 六步流程的工具 ============================================
# 提醒：以下每一個 handler 都只是回傳寫死的字典。
# 它們的價值在於「示範授權與攔截的行為」，不在於「計算出正確答案」。


def verify_employment():
    """1 Verify — 移工身份與聘僱關係、仲介與雇主法人。

    [假資料] 整個回傳值是固定的。
    真實版本應該做的事：
      - 用 VleiVerifier 驗證雇主與仲介的 LE 憑證，確認法人存在且憑證未撤銷
      - 向勞動部或雇主的人資系統查詢實際聘僱關係與在職狀態
    目前這兩件事都沒做，`verified_by` 欄位描述的是「將來會怎麼驗」，不是「剛剛驗過了」。
    """
    return {
        "worker": "阮氏梅 Nguyen Thi Mai",
        "employment_status": "在職",
        "employer": "{}（LEI {}）".format(EMPLOYER_NAME, EMPLOYER_LEI),
        "agency": "{}（LEI {}）".format(AGENCY_NAME, AGENCY_LEI),
        "contract_period": "2025-03-01 → 2028-02-29",
        "verified_by": "[假資料] 尚未實際驗證，接上 vlei-sandbox 後改為真實憑證鏈",
    }


# 這一格是整個作品裡「AI 真的在做事」的證據。
# 有金鑰時呼叫 OpenRouter 做真實抽取；沒有金鑰或呼叫失敗時退回固定值，
# 並在回傳值與畫面上明確標注是哪一種——Demo Day 網路不穩不會開天窗。

# 敘述刻意寫得完整（含年份），讓「順利路徑」能一次通過。
# 少了年份時模型會正確地回 null、規則會正確地轉人工——那是 run.py llm 第二個測試在示範的。
DEFAULT_STATEMENT = (
    "Ngày 26 tháng 8 năm 2026, lúc 2 giờ 20 chiều, "
    "tôi bị máy kẹp cổ tay phải khi đang vận hành máy SMT số 3 tại nhà máy."
)

# 必填欄位。少任何一項就轉人工——用欄位完整性判斷，不用信心分數門檻。
REQUIRED_FIELDS = ["incident_date", "body_part", "mechanism", "work_related"]

EXTRACTION_SYSTEM = """你是職災理賠的資料抽取助手。使用者會用他的母語（越南文、印尼文、泰文或中文）描述一起工作場所事故。

請只輸出 JSON，格式如下：
{
  "incident_date": "YYYY-MM-DD 或 null",
  "incident_time": "HH:MM 或 null",
  "location": "事故地點，或 null",
  "mechanism": "事故機轉，例如「機台夾傷」，或 null",
  "body_part": "受傷部位，或 null",
  "work_related": true / false / null,
  "uncertain_fields": ["敘述中沒有明確講到、你用推測填入的欄位名稱"],
  "summary_zh": "用繁體中文一句話摘要"
}

規則：
- 敘述中沒有明確提到的欄位一律填 null，不要猜測。
- 任何你不是從敘述直接讀到、而是推論出來的欄位，把欄位名放進 uncertain_fields。
- work_related 只有在敘述明確指出是在執行職務時發生，才填 true。"""


def understand_incident(lang="vi", raw=""):
    """2 Understand — 移工用母語描述事故，轉成結構化的理賠事件。

    這是本情境裡唯一會實際呼叫語言模型的函式。

    轉人工的判斷用**欄位完整性**，不用信心分數：
      必填欄位（事故日期、受傷部位、事故機轉、是否因執行職務）
      只要有任一項抽不到，或模型自己標記為推測而非讀取，就轉人工。

    這樣設計的原因是分數型門檻在問答時站不住——
    評審只要問「為什麼門檻是 0.9 不是 0.85」就沒有答案；
    欄位完整性則說得出口，也可以當場示範。

    沒有金鑰或呼叫失敗時，退回固定值並在 `source` 欄位標明。
    """
    statement = raw or DEFAULT_STATEMENT

    if not llm.is_available():
        return _fixture_extraction(lang, statement, "未設定 OPENROUTER_API_KEY，使用固定值")

    try:
        data = llm.chat_json(
            system=EXTRACTION_SYSTEM,
            user="描述語言：{}\n事故敘述：{}".format(lang, statement),
        )
    except llm.LLMError as exc:
        return _fixture_extraction(lang, statement, "模型呼叫失敗（{}），退回固定值".format(exc))

    structured = {k: data.get(k) for k in
                  ["incident_date", "incident_time", "location", "mechanism", "body_part", "work_related"]}
    uncertain = data.get("uncertain_fields") or []

    missing = [f for f in REQUIRED_FIELDS if structured.get(f) in (None, "")]
    guessed = [f for f in REQUIRED_FIELDS if f in uncertain]
    needs_review = bool(missing or guessed)

    reasons = []
    if missing:
        reasons.append("必填欄位抽取不到：" + "、".join(missing))
    if guessed:
        reasons.append("模型標記為推測而非讀取：" + "、".join(guessed))

    return {
        "source": "模型即時抽取（{}）".format(os.environ.get("OPENROUTER_MODEL") or llm.DEFAULT_MODEL),
        "input_lang": lang,
        "raw_statement": statement,
        "structured": structured,
        "summary_zh": data.get("summary_zh", ""),
        "needs_human_review": needs_review,
        "review_reason": "；".join(reasons) if reasons else "必填欄位齊全且皆為直接讀取",
    }


def _fixture_extraction(lang, statement, why):
    """[假資料] 沒有金鑰或呼叫失敗時的退路。回傳值會標明來源。"""
    return {
        "source": "[假資料] " + why,
        "input_lang": lang,
        "raw_statement": statement,
        "structured": {
            "incident_date": "2026-08-26",
            "incident_time": "14:20",
            "location": "SMT 產線 3 號機台",
            "mechanism": "機台夾傷",
            "body_part": "右手腕",
            "work_related": True,
        },
        "summary_zh": "移工操作 SMT 機台時右手腕遭夾傷",
        "needs_human_review": False,
        "review_reason": "[假資料] 未經實際判斷",
    }


def match_coverage():
    """3 Match — 比對職災、勞保與商業保險保障。

    保障清單本身仍是人工編寫的示意內容（見 FIXTURE_NOTES）。
    **但引用出處是真的**：從本地知識庫 `knowledge/laws.json` 撈，
    並附上知識庫版本與 sha256，任何人都能重算確認引用的是哪一份。

    知識庫還沒填條文時，citations 會是空的並註明原因——
    **不會編造條號**。這正是先前犯過的錯：填錯的法條比留空更傷。

    為什麼不在這裡上網查：交件是錄影，錄影只有一次；
    而且同一個問題不同時間得到不同答案就無法重現。
    線上同步屬於維運排程，不屬於推論路徑（見 knowledge/VERSION.md）。
    """
    kbs = knowledge.load_all()
    keywords = ["職業傷害", "職災", "門診治療", "住院", "醫療費用"]

    citations = []
    for kb in kbs.values():
        for entry in kb.find(keywords):
            citations.append(kb.cite(entry))

    result = {
        "matched": [
            {"scheme": "勞保職災醫療給付", "status": "適用", "note": "門診／住院醫療費用"},
            {"scheme": "勞保職災傷病給付", "status": "適用", "note": "不能工作期間的薪資補償"},
            {"scheme": "雇主團體傷害險", "status": "適用", "insurer": INSURER_NAME},
            {"scheme": "健保", "status": "部分適用", "note": "職災優先由職災保險給付"},
        ],
        "not_matched": [{"scheme": "商業失能險", "reason": "未達失能等級"}],
        "citations": citations,
    }

    if not citations:
        result["citation_note"] = (
            "[假資料] 知識庫尚未填入條文（knowledge/laws.json）。"
            "刻意不編造條號——填錯的法條比留空更傷。"
        )
    else:
        result["citation_source"] = "本地知識庫 v{}（離線，可重現）".format(
            kbs["laws"].version)
    return result


def list_missing_documents():
    """4 Claim — 列出已備與待補文件。

    [假資料] 清單為固定值，未與任何文件管理系統核對。
    真實版本應由已上傳文件與該險種必備文件清單做差集。
    """
    return {
        "case_id": CASE_ID,
        "ready": ["事故通報單", "出勤紀錄", "健檢適任證明"],
        "missing": ["職業傷病診斷書正本", "醫療費用收據", "雇主意外事故證明"],
        "next_action": "請醫院開立職業傷病診斷書",
    }


def track_status():
    """5 Track — 案件進度對移工透明（對應新加坡 EmPOWER 的做法）。

    [假資料] 進度為固定值，未連接任何案件系統。
    真實版本應讀取案件狀態機的當前節點與等待對象。
    """
    return {
        "case_id": CASE_ID,
        "stage": "文件準備中",
        "opened": "2026-08-26",
        "days_open": 3,
        "waiting_on": "醫院診斷書",
        "visible_to_worker": True,
    }


def build_protection_record():
    """6 Record — 產出 0829 Concept deck 所稱的 worker protection record。

    「worker protection record」是該 deck 的用語，不是 RBA 或 ISO 的標準名詞，
    講述時建議加一句說明，避免評審誤以為是既有規範。

    [假資料] 內容為固定值；evidence_credentials 列的 SAID 也是假值。
    真實版本應蒐集本案實際產生的憑證 SAID 清單。
    """
    return {
        "incident": "2026-08-26 機台夾傷",
        "claim": CASE_ID,
        "employer_response": "當日送醫、已通報",
        "corrective_action": "3 號機台加裝雙手啟動裝置",
        "evidence_credentials": [HEALTHPASS_SAID, DIAGNOSIS_SAID],
        "rba_pillars": ["Health & Safety", "Grievance Mechanism"],
        "contains_personal_data": False,
    }


def submit_claim(insurer=None):
    """不可逆動作：正式送出理賠申請。一律先攔截，等移工本人確認。

    [假資料] 不會真的送件給任何保險公司，只回傳一個成功訊息。
    這個函式的重點不在它做了什麼，而在「它被攔下來了」。
    """
    return {
        "submitted_to": insurer or INSURER_NAME,
        "case_id": CASE_ID,
        "irreversible": True,
        "note": "[假資料] 未實際送出任何申請",
    }


def read_full_medical_history():
    """授權範圍外：調閱與本次職災無關的完整病歷。

    [假資料] 回傳佔位字串。這個函式正常情況下永遠不會被執行到——
    它存在的目的就是被政策閘擋下來。
    """
    return {k: "（假資料佔位值）" for k in LOCAL_ONLY}


def build_tools():
    return [
        Tool("verify_employment", "1 Verify — 驗證身份與聘僱關係",
             "claim_prep", LOW, verify_employment),
        Tool("understand_incident", "2 Understand — 母語事故描述結構化",
             "claim_prep", LOW, understand_incident),
        Tool("match_coverage", "3 Match — 比對可申請的保障",
             "claim_prep", LOW, match_coverage),
        Tool("list_missing_documents", "4 Claim — 列缺件清單",
             "claim_prep", LOW, list_missing_documents),
        Tool("track_status", "5 Track — 查案件進度",
             "claim_prep", LOW, track_status),
        Tool("build_protection_record", "6 Record — 產出 worker protection record",
             "employer_record", LOW, build_protection_record),
        Tool("submit_claim", "正式送出理賠申請（不可逆）",
             "claim_prep", HIGH, submit_claim),
        Tool("read_full_medical_history", "調閱完整病歷（含無關診斷）",
             "full_medical", HIGH, read_full_medical_history),
    ]


# ============ 角色 ======================================================

def build_principal():
    """預設主體：移工本人。Agent 代表她，不代表雇主也不代表仲介。

    她沒有、也不會有 LEI——LEI 是法人識別碼，自然人不在適用範圍。
    她這一層是同意收據，不是 vLEI 憑證。這是刻意分層。
    """
    return Principal(
        id="worker:nguyen-thi-mai",
        display_name="阮氏梅 Nguyen Thi Mai",
        kind="person",
    )


def build_agency_officer(revoked=False):
    """仲介承辦人 — 代表仲介公司行動。

    對應新加坡 Corppass 的 organization-to-person authorization：
    驗證重點不是「這家公司是真的」，而是「這個人被公司授權處理本案」。

    revoked=True 模擬已離職、但帳號尚未回收的承辦人。
    """
    if revoked:
        return Principal(
            id="agency:lin-zhihao",
            display_name="林志豪",
            kind="person",
            acting_for=AGENCY_NAME,
            org_lei=AGENCY_LEI,
            role_credential=ECR_REVOKED,
        )
    return Principal(
        id="agency:chen-meiling",
        display_name="陳美玲",
        kind="person",
        acting_for=AGENCY_NAME,
        org_lei=AGENCY_LEI,
        role_credential=ECR_ACTIVE,
    )


def build_grant(principal, days_valid=90):
    """移工本人的授權：協助理賠，但不含與本次職災無關的病歷。"""
    return Grant(
        id="grant-" + CASE_ID.lower(),
        principal=principal,
        purpose="僅供本次職災理賠準備",
        scopes={"claim_prep", "employer_record"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=days_valid),
    )


def build_agency_grant(principal, days_valid=30):
    """仲介承辦人的授權比移工本人窄：可協助整理文件，碰不到雇主責任紀錄。"""
    return Grant(
        id="grant-agency-" + CASE_ID.lower(),
        principal=principal,
        purpose="仲介協助理賠文件整理",
        scopes={"claim_prep"},
        expires_at=datetime.now(timezone.utc) + timedelta(days=days_valid),
    )


SANDBOX_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vlei-sandbox")
)


def build_verifier():
    """優先使用真正的 vlei-sandbox；找不到才退回 MockVerifier。

    VleiVerifier 會實際執行 `vlei_sandbox.py verify --said <SAID>`，
    重算 SAID、驗簽章、檢查 LEI 檢查碼、查 TEL 撤銷狀態，並沿 edge 遞迴到信任根。
    退回 mock 時畫面會標明，不會假裝成真的驗證。
    """
    if os.path.isdir(SANDBOX_DIR):
        from trustagent import VleiVerifier
        return VleiVerifier(sandbox_dir=SANDBOX_DIR)
    return _build_mock_verifier()


def _build_mock_verifier():
    """[假資料] 找不到 sandbox 時的退路——只是一張查表，不做任何密碼學驗證。

    它「不會」重算 SAID、不會驗簽章、不會走信任鏈、不會查 TEL 撤銷紀錄。
    它唯一做的事是：這個字串在不在我的字典裡、有沒有被標記為已撤銷。

    要換成真的驗證，把這個函式改成：
        from trustagent import VleiVerifier
        return VleiVerifier(sandbox_dir="<vlei-sandbox 的路徑>")
    引擎其他部分不需要改動。
    """
    v = MockVerifier()
    v.register(ECR_ACTIVE, "{}（LEI {}）委任之理賠承辦人".format(AGENCY_NAME, AGENCY_LEI))
    v.register(ECR_REVOKED, "{} 前承辦人".format(AGENCY_NAME))
    v.register(HEALTHPASS_SAID, "{} — 職安健檢適任判定".format(HOSPITAL_NAME))
    v.register(DIAGNOSIS_SAID, "{} — 職業傷病診斷書".format(HOSPITAL_NAME))
    v.revoke(ECR_REVOKED)  # 已離職 → 角色憑證撤銷
    return v


SCENARIO = {
    "name": "移工職災保險 Claim Copilot",
    "case_id": CASE_ID,
    "credential_said": DIAGNOSIS_SAID,
    "local_only_fields": LOCAL_ONLY,
    "build_agency_officer": build_agency_officer,
    "build_agency_grant": build_agency_grant,
    "fixture_notes": FIXTURE_NOTES,
    "all_fixtures": True,  # 本情境所有回傳值皆為固定值
}
