"""不需要 FastAPI 的相容性自我測試。

證明三件事:
  1. SqliteAuditLog 能直接塞進沒有改動過的 TrustAgent
  2. 稽核鏈跨「連線關掉再打開」仍然驗得過(= 真的持久化,不是記憶體)
  3. run.py claim 的判定結果,透過 DB 層跑出來一模一樣

    cd agent
    python3 -m backend.selftest
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 用臨時 DB,不碰 app.db
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["CLAIM_DB_PATH"] = _tmp.name

from scenarios import migrant_claim as s          # noqa: E402
from trustagent import Grant, Principal, TrustAgent  # noqa: E402

from backend.audit_store import SqliteAuditLog, load_audit_key  # noqa: E402
from backend.db import get_conn, init_db          # noqa: E402
from backend.identity import default_expiry       # noqa: E402

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
_score = [0, 0]


def check(label, cond):
    _score[0 if cond else 1] += 1
    print("  {}  {}".format(PASS if cond else FAIL, label))


def worker_agent(conn, case_id):
    p = Principal(id="worker:1", display_name="阮氏梅 Nguyen Thi Mai", kind="person")
    g = Grant(id="g-w", principal=p, purpose="理賠準備",
              scopes={"claim_prep", "employer_record"},
              expires_at=_dt(default_expiry(90)))
    a = TrustAgent(p, g, verifier=s.build_verifier(),
                   audit=SqliteAuditLog(conn, case_id, key=load_audit_key()))
    a.register_all(s.build_tools())
    return a


def officer_agent(conn, case_id, revoked):
    p = Principal(
        id="agency:2", display_name="林志豪" if revoked else "陳美玲", kind="person",
        acting_for=s.AGENCY_NAME, org_lei=s.AGENCY_LEI,
        role_credential=s.ECR_REVOKED if revoked else s.ECR_ACTIVE,
    )
    g = Grant(id="g-o", principal=p, purpose="文件整理", scopes={"claim_prep"},
              expires_at=_dt(default_expiry(30)))
    a = TrustAgent(p, g, verifier=s.build_verifier(),
                   audit=SqliteAuditLog(conn, case_id, key=load_audit_key()))
    a.register_all(s.build_tools())
    return a


def _dt(text):
    from datetime import datetime
    return datetime.fromisoformat(text)


def main():
    init_db()
    case_id = "WIC-TEST-0001"
    conn = get_conn()

    print("\n── 移工六步流程(對照 run.py claim)──")
    w = worker_agent(conn, case_id)
    check("1 verify_employment 放行", w.act("verify_employment").decision.allowed)
    check("2 understand_incident 放行", w.act("understand_incident", lang="vi").decision.allowed)
    check("3 match_coverage 放行", w.act("match_coverage").decision.allowed)
    check("4 list_missing_documents 放行", w.act("list_missing_documents").decision.allowed)
    check("5 track_status 放行", w.act("track_status").decision.allowed)
    check("6 build_protection_record 放行", w.act("build_protection_record").decision.allowed)

    r = w.act("submit_claim")
    check("submit_claim 先被攔(NEEDS_HUMAN_CONFIRMATION)",
          r.blocked and r.decision.code == "NEEDS_HUMAN_CONFIRMATION")
    check("submit_claim 帶 confirmed=True 後放行",
          w.act("submit_claim", confirmed=True).decision.allowed)

    r = w.act("read_full_medical_history")
    check("read_full_medical_history 被擋(OUT_OF_SCOPE)",
          r.blocked and r.decision.code == "OUT_OF_SCOPE")

    print("\n── 仲介承辦人授權(Corppass 模式)──")
    o = officer_agent(conn, case_id, revoked=False)
    check("在職承辦人 list_missing_documents 放行", o.act("list_missing_documents").decision.allowed)
    r = o.act("build_protection_record")
    check("在職承辦人 build_protection_record 被擋(scope 較窄)",
          r.blocked and r.decision.code == "OUT_OF_SCOPE")

    ro = officer_agent(conn, case_id, revoked=True)
    r = ro.act("list_missing_documents")
    check("已離職承辦人被擋(ROLE_NOT_VERIFIED)",
          r.blocked and r.decision.code == "ROLE_NOT_VERIFIED")

    print("\n── 稽核鏈:持久化 + 竄改偵測 ──")
    ok, _, msg = w.audit.verify()
    check("竄改前 verify PASS：" + msg, ok)

    conn.close()                                    # ← 關掉連線
    conn2 = get_conn()                              # ← 重新打開(模擬另一個 session)
    fresh = SqliteAuditLog(conn2, case_id, key=load_audit_key())
    ok, _, msg = fresh.verify()
    check("關閉連線再開,鏈仍然 PASS(= 真的存進 DB):" + msg, ok)
    n_before = len(fresh.entries)

    victim = next(e.seq for e in fresh.entries if not e.allowed)
    fresh.tamper(seq=victim, field_name="code", new_value="OK")
    fresh.tamper(seq=victim, field_name="allowed", new_value=True)
    ok, bad, msg = fresh.verify()
    check("把第 {} 筆攔截紀錄改成放行後,verify FAIL:{}".format(victim, msg),
          (not ok) and bad == victim)
    check("竄改沒有增加筆數(唯附加)", len(fresh.entries) == n_before)

    print("\n── 機制 6:撤銷 ──")
    w2 = worker_agent(conn2, case_id)             # 用還開著的連線重建 agent
    w2.grant.revoke()                             # 模擬「重新讀到已撤銷的 grant」
    r = w2.act("track_status")
    check("授權撤銷後,原本放行的工具立即失效(GRANT_REVOKED)",
          r.blocked and r.decision.code == "GRANT_REVOKED")
    conn2.close()

    print("\n{} 通過 / {} 失敗".format(_score[0], _score[1]))
    os.unlink(_tmp.name)
    for suffix in ("-wal", "-shm"):
        p = _tmp.name + suffix
        if os.path.exists(p):
            os.unlink(p)
    return 1 if _score[1] else 0


if __name__ == "__main__":
    sys.exit(main())
