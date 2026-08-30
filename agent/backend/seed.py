"""建示範帳號與一個案件,讓 demo 一開始就有東西可點。

    cd agent
    python3 -m backend.seed          # 冪等,重跑不會爆

帳號(密碼都是 demo1234):
    mai@demo.tw        移工 阮氏梅
    meiling@hongtai.tw 仲介承辦人 陳美玲(ECR 有效)
    zhihao@hongtai.tw  仲介承辦人 林志豪(ECR 已撤銷 → 代理關係驗證會失敗)
    taka@jinghong.tw   雇主 Migrant Worker Manager Taka(ECR 有效)

案件 WIC-DEMO-0001:阮氏梅已建案；仲介獲理賠協作權，Taka 獲雇主案件參與權。
"""

from datetime import datetime, timezone

from scenarios import migrant_claim as s

from . import auth
from .db import get_conn, init_db
from .identity import COLLAB_SCOPES, EMPLOYER_SCOPES, WORKER_SCOPES, default_expiry

PW = auth.hash_password("demo1234")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

USERS = [
    dict(email="mai@demo.tw", display_name="阮氏梅 Nguyen Thi Mai", role="worker",
         acting_for=None, org_lei=None, role_credential=None),
    dict(email="meiling@hongtai.tw", display_name="陳美玲", role="agency_officer",
         acting_for=s.AGENCY_NAME, org_lei=s.AGENCY_LEI, role_credential=s.ECR_ACTIVE),
    dict(email="zhihao@hongtai.tw", display_name="林志豪", role="agency_officer",
         acting_for=s.AGENCY_NAME, org_lei=s.AGENCY_LEI, role_credential=s.ECR_REVOKED),
    dict(email="taka@jinghong.tw", display_name=s.TAKA_NAME, role="employer_officer",
         acting_for=s.EMPLOYER_NAME, org_lei=s.EMPLOYER_LEI, role_credential=s.TAKA_ECR),
]

CASE_ID = "WIC-DEMO-0001"


def _upsert_user(conn, u):
    row = conn.execute("SELECT id FROM users WHERE email=?", (u["email"],)).fetchone()
    if row:
        # sandbox 重建後 SAID 會改變；每次 seed 都同步角色與當前憑證，避免舊帳號失效。
        conn.execute(
            "UPDATE users SET display_name=?,role=?,acting_for=?,org_lei=?,role_credential=? "
            "WHERE id=?",
            (u["display_name"], u["role"], u["acting_for"], u["org_lei"],
             u["role_credential"], row["id"]),
        )
        return row["id"]
    cur = conn.execute(
        "INSERT INTO users(email,password,display_name,role,acting_for,org_lei,"
        "role_credential,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (u["email"], PW, u["display_name"], u["role"], u["acting_for"],
         u["org_lei"], u["role_credential"], NOW),
    )
    return cur.lastrowid


def main():
    init_db()
    conn = get_conn()
    try:
        ids = {u["email"]: _upsert_user(conn, u) for u in USERS}

        if not conn.execute("SELECT 1 FROM cases WHERE id=?", (CASE_ID,)).fetchone():
            conn.execute(
                "INSERT INTO cases(id,worker_user_id,title,status,created_at) VALUES (?,?,?,?,?)",
                (CASE_ID, ids["mai@demo.tw"], "移工職災理賠(示範案)", "OPEN", NOW),
            )

        grants = [
            ("grant-" + CASE_ID.lower(), ids["mai@demo.tw"],
             "僅供本次職災理賠準備", WORKER_SCOPES, 90),
            ("grant-{}-meiling".format(CASE_ID.lower()), ids["meiling@hongtai.tw"],
             "協助理賠文件整理", COLLAB_SCOPES, 30),
            ("grant-{}-zhihao".format(CASE_ID.lower()), ids["zhihao@hongtai.tw"],
             "協助理賠文件整理", COLLAB_SCOPES, 30),
            ("grant-{}-taka".format(CASE_ID.lower()), ids["taka@jinghong.tw"],
             "雇主確認聘僱並提供員工保險與事故證據", EMPLOYER_SCOPES, 30),
        ]
        for gid, uid, purpose, scopes, days in grants:
            conn.execute(
                "INSERT OR IGNORE INTO grants(id,case_id,user_id,purpose,scopes,expires_at) "
                "VALUES (?,?,?,?,?,?)",
                (gid, CASE_ID, uid, purpose, ",".join(sorted(scopes)), default_expiry(days)),
            )
        conn.commit()
    finally:
        conn.close()

    print("seed 完成。案件:", CASE_ID)
    print("登入:mai@demo.tw / meiling@hongtai.tw / zhihao@hongtai.tw / "
          "taka@jinghong.tw(密碼 demo1234)")


if __name__ == "__main__":
    main()
