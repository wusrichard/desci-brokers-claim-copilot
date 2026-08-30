"""HTTP API 端到端整合測試；使用臨時 SQLite，不碰 Demo 資料。"""

import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["CLAIM_DB_PATH"] = _tmp.name

from fastapi.testclient import TestClient  # noqa: E402
from backend import seed  # noqa: E402
from backend.server import app  # noqa: E402


def expect(label, condition):
    if not condition:
        raise AssertionError(label)
    print("  PASS ", label)


def token(client, email):
    response = client.post("/login", json={"email": email, "password": "demo1234"})
    expect("{} 登入".format(email), response.status_code == 200)
    return response.json()["token"]


def headers(value):
    return {"Authorization": "Bearer " + value}


def main():
    seed.main()
    with TestClient(app) as client:
        home = client.get("/")
        expect("前端首頁", home.status_code == 200)
        expect("CSP 與 anti-clickjacking 標頭存在",
               "default-src 'self'" in home.headers.get("content-security-policy", "")
               and home.headers.get("x-frame-options") == "DENY")
        status = client.get("/api/status").json()
        expect("vLEI sandbox 已連接", status["verifier"] == "vlei-sandbox")
        expect("Demo 模式保留竄改展示", status["tamper_demo_enabled"])

        weak = client.post("/register", json={
            "email": "weak@example.test", "password": "short",
            "display_name": "Weak", "role": "worker",
        })
        expect("公開註冊拒絕弱密碼", weak.status_code == 400)
        retired_role = client.post("/register", json={
            "email": "retired-auditor@example.test", "password": "demo-password-123",
            "display_name": "Retired Auditor", "role": "auditor",
        })
        expect("auditor 角色已停用，不能建立新帳號", retired_role.status_code == 400)

        for _ in range(8):
            last_bad = client.post("/login", json={
                "email": "rate-limit@example.test", "password": "wrong"
            })
        limited = client.post("/login", json={
            "email": "rate-limit@example.test", "password": "wrong"
        })
        expect("登入失敗節流", last_bad.status_code == 401 and limited.status_code == 429)

        mai = token(client, "mai@demo.tw")
        cases = client.get("/cases", headers=headers(mai))
        expect("移工能列出案件", cases.status_code == 200 and cases.json())
        case_id = cases.json()[0]["case_id"]

        no_csrf = client.post(
            "/cases/{}/act".format(case_id), json={"tool": "verify_employment"}
        )
        expect("Cookie 認證的變更請求沒有 CSRF token 會被擋", no_csrf.status_code == 403)
        csrf = client.cookies.get("csrf_token")
        with_csrf = client.post(
            "/cases/{}/act".format(case_id),
            headers={"X-CSRF-Token": csrf}, json={"tool": "verify_employment"},
        )
        expect("正確 CSRF token 可通過", with_csrf.status_code == 200)

        case = client.get("/cases/" + case_id, headers=headers(mai)).json()
        expect("案件回傳 scopes 與 capabilities", bool(case["grant"]) and bool(case["capabilities"]))

        action = client.post(
            "/cases/{}/act".format(case_id), headers=headers(mai),
            json={"tool": "verify_employment"},
        ).json()
        expect("移工 Verify 放行", action["allowed"])

        blocked = client.post(
            "/cases/{}/act".format(case_id), headers=headers(mai),
            json={"tool": "submit_claim"},
        ).json()
        expect("送件先要求人工確認", blocked["code"] == "NEEDS_HUMAN_CONFIRMATION")
        confirmed = client.post(
            "/cases/{}/act".format(case_id), headers=headers(mai),
            json={"tool": "submit_claim", "confirmed": True},
        ).json()
        expect("本人確認後放行", confirmed["allowed"])

        escalated = client.post(
            "/cases/{}/grants".format(case_id), headers=headers(mai),
            json={"email": "meiling@hongtai.tw", "scopes": ["full_medical"]},
        )
        expect("不能把不可委派的 full_medical scope 授權給協作者", escalated.status_code == 400)

        meiling = token(client, "meiling@hongtai.tw")
        ok = client.post(
            "/cases/{}/act".format(case_id), headers=headers(meiling),
            json={"tool": "list_missing_documents"},
        ).json()
        expect("有效 ECR 承辦人放行", ok["allowed"])
        narrow = client.post(
            "/cases/{}/act".format(case_id), headers=headers(meiling),
            json={"tool": "build_protection_record"},
        ).json()
        expect("承辦人 scope 越界被擋", narrow["code"] == "OUT_OF_SCOPE")

        zhihao = token(client, "zhihao@hongtai.tw")
        revoked = client.post(
            "/cases/{}/act".format(case_id), headers=headers(zhihao),
            json={"tool": "list_missing_documents"},
        ).json()
        expect("撤銷 ECR 承辦人被擋", revoked["code"] == "ROLE_NOT_VERIFIED")

        taka = token(client, "taka@jinghong.tw")
        taka_case = client.get("/cases/" + case_id, headers=headers(taka))
        expect("Taka 可進入雇主案件頁", taka_case.status_code == 200)
        taka_case = taka_case.json()
        expect("Taka 以晶宏電子 Migrant Worker Manager 身分行動",
               taka_case["acting_as"]["acting_for"] == "晶宏電子股份有限公司"
               and bool(taka_case["acting_as"]["role_credential"]))
        for tool_name in (
            "confirm_worker_employment",
            "submit_employer_incident_report",
            "submit_insurance_enrollment_record",
            "track_employer_tasks",
        ):
            employer_action = client.post(
                "/cases/{}/act".format(case_id), headers=headers(taka),
                json={"tool": tool_name},
            ).json()
            expect("Taka 可執行 {}".format(tool_name), employer_action["allowed"])
        employer_blocked = client.post(
            "/cases/{}/act".format(case_id), headers=headers(taka),
            json={"tool": "submit_claim", "confirmed": True},
        ).json()
        expect("Taka 不能代表移工正式送件", employer_blocked["code"] == "OUT_OF_SCOPE")
        medical_blocked = client.post(
            "/cases/{}/act".format(case_id), headers=headers(taka),
            json={"tool": "read_full_medical_history", "confirmed": True},
        ).json()
        expect("Taka 不能查看完整病歷", medical_blocked["code"] == "OUT_OF_SCOPE")
        expect("Taka 不是案件本人，不能讀完整可驗證操作鏈",
               client.get("/cases/{}/audit".format(case_id),
                          headers=headers(taka)).status_code == 403)
        expect("仲介承辦人也不能讀完整可驗證操作鏈",
               client.get("/cases/{}/audit".format(case_id),
                          headers=headers(meiling)).status_code == 403)

        employer_scope_escalation = client.post(
            "/cases/{}/grants".format(case_id), headers=headers(mai),
            json={"email": "meiling@hongtai.tw", "scopes": ["employer_insurance"]},
        )
        expect("案件本人不能把雇主平台權限委派給仲介",
               employer_scope_escalation.status_code == 400)
        employer_claim_escalation = client.post(
            "/cases/{}/grants".format(case_id), headers=headers(mai),
            json={"email": "taka@jinghong.tw", "scopes": ["claim_prep"]},
        )
        expect("一般 Grant 不能把移工理賠權限改發給雇主",
               employer_claim_escalation.status_code == 400)

        meiling_case = client.get("/cases/" + case_id, headers=headers(meiling)).json()
        revoked_grant = client.post(
            "/grants/{}/revoke".format(meiling_case["grant"]["id"]), headers=headers(mai)
        )
        expect("案件本人可撤銷協作者 Grant", revoked_grant.status_code == 200)
        expect("Grant 撤銷後協作者立即失去案件讀取權",
               client.get("/cases/" + case_id, headers=headers(meiling)).status_code == 403)

        audit = client.get("/cases/{}/audit".format(case_id), headers=headers(mai)).json()
        expect("可驗證操作鏈竄改前 PASS", audit["verify"]["ok"])
        taka_entry = next(
            e for e in audit["entries"]
            if e["principal"].startswith("Taka") and e["allowed"]
        )
        expect("Taka 成功操作也留下公司、ECR 與 Verifier 證據",
               taka_entry["detail"]["delegation"]["acting_for"] == "晶宏電子股份有限公司"
               and taka_entry["detail"]["delegation"]["role_credential"]
               and taka_entry["detail"]["delegation"]["verifier"] == "vlei-sandbox")
        expect("操作紀錄已啟用 Ed25519 簽章與驗簽",
               audit["signed"] and "Ed25519" in audit["verify"]["message"])
        victim = next(e["seq"] for e in audit["entries"] if not e["allowed"])
        tampered = client.post(
            "/cases/{}/audit/tamper".format(case_id), headers=headers(mai),
            json={"seq": victim, "field": "code", "value": "TAMPERED"},
        ).json()
        expect("竄改後 FAIL", not tampered["verify"]["ok"])

        csrf = client.cookies.get("csrf_token")
        expect("登出也受 CSRF 保護",
               client.post("/logout").status_code == 403
               and client.post("/logout", headers={"X-CSRF-Token": csrf}).status_code == 200)

    print("\nAPI 整合測試全部通過")


if __name__ == "__main__":
    try:
        main()
    finally:
        for suffix in ("", "-wal", "-shm"):
            path = _tmp.name + suffix
            if os.path.exists(path):
                os.unlink(path)
