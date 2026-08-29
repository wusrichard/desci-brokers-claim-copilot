"""建示範帳號與一個案件,讓 demo 一開始就有東西可點。

    cd agent
    python3 -m backend.seed          # 冪等,重跑不會爆

帳號(密碼都是 demo1234):
    mai@demo.tw        移工 阮氏梅
    meiling@hongtai.tw 仲介承辦人 陳美玲(ECR 有效)
    zhihao@hongtai.tw  仲介承辦人 林志豪(ECR 已撤銷 → 代理關係驗證會失敗)
    sgs@audit.tw       稽核方 SGS 承辦

案件 WIC-DEMO-0001:阮氏梅已建案,並已授權陳美玲、林志豪協作(scope: claim_prep)。
"""

from datetime import datetime, timezone

from scenarios import claim_copilot as s

from . import auth
from .db import get_conn, init_db
from .identity import COLLAB_SCOPES, WORKER_SCOPES, default_expiry

PW = auth.hash_password("demo1234")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

USERS = [
    dict(email="mai@demo.tw", display_name="阮氏梅 Nguyen Thi Mai", role="worker",
         acting_for=None, org_lei=None, role_credential=None),
    dict(email="meiling@hongtai.tw", display_name="陳美玲", role="agency_officer",
         acting_for=s.AGENCY_NAME, org_lei=s.AGENCY_LEI, role_credential=s.ECR_ACTIVE),
    dict(email="zhihao@hongtai.tw", display_name="林志豪", role="agency_officer",
         acting_for=s.AGENCY_NAME, org_lei=s.AGENCY_LEI, role_credential=s.ECR_REVOKED),
    dict(email="sgs@audit.tw", display_name="SGS 稽核承辦", role="auditor",
         acting_for="SGS Taiwan", org_lei=None, role_credential=None),
]

CASE_ID = "WIC-DEMO-0001"


def _upsert_user(conn, u):
    row = conn.execute("SELECT id FROM users WHERE email=?", (u["email"],)).fetchone()
    if row:
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
    print("登入:mai@demo.tw / meiling@hongtai.tw / zhihao@hongtai.tw / sgs@audit.tw(密碼 demo1234)")


if __name__ == "__main__":
    main()
