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
        expect("前端首頁", client.get("/").status_code == 200)
        status = client.get("/api/status").json()
        expect("vLEI sandbox 已連接", status["verifier"] == "vlei-sandbox")

        mai = token(client, "mai@demo.tw")
        cases = client.get("/cases", headers=headers(mai))
        expect("移工能列出案件", cases.status_code == 200 and cases.json())
        case_id = cases.json()[0]["case_id"]

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

        sgs = token(client, "sgs@audit.tw")
        denied = client.get("/cases/" + case_id, headers=headers(sgs))
        expect("未授權稽核方不能讀案件", denied.status_code == 403)

        audit = client.get("/cases/{}/audit".format(case_id), headers=headers(mai)).json()
        expect("稽核鏈竄改前 PASS", audit["verify"]["ok"])
        victim = next(e["seq"] for e in audit["entries"] if not e["allowed"])
        tampered = client.post(
            "/cases/{}/audit/tamper".format(case_id), headers=headers(mai),
            json={"seq": victim, "field": "code", "value": "TAMPERED"},
        ).json()
        expect("竄改後 FAIL", not tampered["verify"]["ok"])

    print("\nAPI 整合測試全部通過")


if __name__ == "__main__":
    try:
        main()
    finally:
        for suffix in ("", "-wal", "-shm"):
            path = _tmp.name + suffix
            if os.path.exists(path):
                os.unlink(path)
