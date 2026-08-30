"""FastAPI 應用 — 把 run.py 在程式碼裡做的事,變成大家連得進來的 HTTP 端點。

啟動:
    cd agent
    pip install -r backend/requirements.txt
    python3 -m backend.seed          # 建示範帳號與一個案件(選用)
    uvicorn backend.server:app --reload --port 8000

互動式 API 文件:http://localhost:8000/docs

端點對照(CLI → API):
    run.py claim 的六步 act()      →  POST /cases/{id}/act
    build_agent() 內建的授權        →  POST /cases            (建案時自動給移工授權)
    「移工授權仲介承辦人」           →  POST /cases/{id}/grants
    run.py verify                  →  POST /cases/{id}/audit/verify
    run.py tamper                  →  POST /cases/{id}/audit/tamper
    run.py audit                   →  GET  /cases/{id}/audit
    機制 6 撤銷                     →  POST /grants/{id}/revoke
"""

import os
import secrets
import sys
from datetime import datetime, timezone

# 允許 `uvicorn backend.server:app` 從 agent/ 目錄啟動時找到 trustagent / scenarios
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scenarios import migrant_claim

from . import auth
from . import security
from .db import get_conn, init_db
from .identity import (
    COLLAB_SCOPES,
    DELEGATABLE_SCOPES,
    WORKER_SCOPES,
    build_agent,
    default_expiry,
)

app = FastAPI(title="Migrant Insurance Infrastructure — 後端骨架", version="0.1.0")
ACTIVE_ROLES = {"worker", "agency_officer", "employer_officer"}
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=security.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    allow_credentials=True,
)


@app.middleware("http")
async def security_boundary(request: Request, call_next):
    """所有 HTTP 請求共用的大小限制、CSRF 與瀏覽器安全標頭。"""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            too_large = int(content_length) > security.MAX_BODY_BYTES
        except ValueError:
            too_large = True
        if too_large:
            response = JSONResponse({"detail": "請求內容過大"}, status_code=413)
            security.add_security_headers(response)
            return response
    try:
        security.enforce_csrf(request)
    except HTTPException as exc:
        response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        security.add_security_headers(response)
        return response
    response = await call_next(request)
    security.add_security_headers(response)
    return response


@app.on_event("startup")
def _startup():
    init_db()


# ============ 認證相依 ==================================================
def current_user(
    authorization: str = Header(default=""),
    session: str = Cookie(default=""),
):
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:]
    elif session:
        token = session
    uid = auth.read_token(token) if token else None
    if uid is None:
        raise HTTPException(401, "請先登入")
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(401, "帳號不存在")
    if row["role"] not in ACTIVE_ROLES:
        raise HTTPException(403, "此角色已停用")
    return dict(row)


# ============ 請求/回應模型 ============================================
class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str
    role: str = "worker"                 # worker | agency_officer | employer_officer
    acting_for: str = ""                 # 組織承辦人才填
    org_lei: str = ""
    role_credential: str = ""            # ECR 憑證 SAID(對應 MockVerifier 認得的值)


class LoginIn(BaseModel):
    email: str
    password: str


class CaseIn(BaseModel):
    title: str = "移工職災理賠"


class GrantIn(BaseModel):
    email: str                          # 要授權給誰
    scopes: list = None                 # 預設 {"claim_prep"}
    days_valid: int = 30


class ActIn(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    confirmed: bool = False


class TamperIn(BaseModel):
    seq: int
    field: str = "code"
    value: str = "OK"


# ============ 認證端點 ================================================
@app.post("/register")
def register(body: RegisterIn):
    if not security.ALLOW_PUBLIC_REGISTRATION:
        raise HTTPException(404, "此環境未開放公開註冊")
    if body.role not in ACTIVE_ROLES:
        raise HTTPException(400, "role 必須是 worker / agency_officer / employer_officer")
    if len(body.password) < 10:
        raise HTTPException(400, "密碼至少需要 10 個字元")
    email = body.email.strip().lower()
    if not email or "@" not in email or len(email) > 254:
        raise HTTPException(400, "email 格式不正確")
    conn = get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
        if exists:
            raise HTTPException(409, "這個 email 已註冊")
        cur = conn.execute(
            "INSERT INTO users(email,password,display_name,role,acting_for,org_lei,"
            "role_credential,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                email,
                auth.hash_password(body.password),
                body.display_name,
                body.role,
                body.acting_for or None,
                body.org_lei or None,
                body.role_credential or None,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        uid = cur.lastrowid
    finally:
        conn.close()
    return {"id": uid, "email": email, "role": body.role}


@app.post("/login")
def login(body: LoginIn, response: Response, request: Request):
    email = body.email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    rate_key = "{}:{}".format(client_ip, email)
    security.check_login_rate_limit(rate_key)
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    finally:
        conn.close()
    if row is None or not auth.verify_password(body.password, row["password"]):
        raise HTTPException(401, "email 或密碼錯誤")
    security.clear_login_attempts(rate_key)
    token = auth.make_token(row["id"])
    csrf_token = auth.make_csrf_token()
    response.set_cookie(
        "session", token, httponly=True, secure=security.COOKIE_SECURE,
        samesite="strict", max_age=auth.TOKEN_TTL_SECONDS, path="/",
    )
    response.set_cookie(
        "csrf_token", csrf_token, httponly=False, secure=security.COOKIE_SECURE,
        samesite="strict", max_age=auth.TOKEN_TTL_SECONDS, path="/",
    )
    # token 保留給 curl／API client；瀏覽器前端只使用 HttpOnly Cookie。
    return {"token": token, "csrf_token": csrf_token, "user": _public_user(dict(row))}


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie("session", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"ok": True}


@app.get("/me")
def me(user: dict = Depends(current_user)):
    return _public_user(user)


def _public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "acting_for": row["acting_for"],
        "org_lei": row["org_lei"],
        "role_credential": row["role_credential"],
    }


# ============ 案件 ====================================================
@app.post("/cases")
def create_case(body: CaseIn, user: dict = Depends(current_user)):
    """移工建案。建案的同時自動發給自己一張授權(對應 build_agent 內建的 grant)。"""
    if user["role"] != "worker":
        raise HTTPException(403, "只有移工本人能建立理賠案件")
    case_id = "WIC-{}-{}".format(
        datetime.now(timezone.utc).strftime("%Y-%m%d"),
        secrets.token_hex(2).upper(),
    )
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO cases(id,worker_user_id,title,status,created_at) VALUES (?,?,?,?,?)",
            (case_id, user["id"], body.title, "OPEN",
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.execute(
            "INSERT INTO grants(id,case_id,user_id,purpose,scopes,expires_at) "
            "VALUES (?,?,?,?,?,?)",
            ("grant-" + case_id.lower(), case_id, user["id"],
             "僅供本次職災理賠準備", ",".join(sorted(WORKER_SCOPES)),
             default_expiry(90)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"case_id": case_id, "status": "OPEN", "your_scopes": sorted(WORKER_SCOPES)}


def _load_case(conn, case_id):
    row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "找不到這個案件")
    return row


def _load_grant(conn, case_id, user_id):
    return conn.execute(
        "SELECT * FROM grants WHERE case_id=? AND user_id=?", (case_id, user_id)
    ).fetchone()


def _ensure_case_access(conn, case_id, user):
    case = _load_case(conn, case_id)
    grant = _load_grant(conn, case_id, user["id"])
    is_owner = case["worker_user_id"] == user["id"]
    if grant is None and not is_owner:
        raise HTTPException(403, "你在這個案件沒有任何授權")
    if not is_owner and grant is not None:
        expires_at = datetime.fromisoformat(grant["expires_at"])
        if grant["revoked_at"] or expires_at <= datetime.now(timezone.utc):
            raise HTTPException(403, "你在這個案件的授權已撤銷或到期")
    return case, grant


def _ensure_audit_access(case, grant, user):
    if case["worker_user_id"] != user["id"]:
        raise HTTPException(403, "只有案件本人能查看完整可驗證操作紀錄")


@app.get("/cases")
def list_cases(user: dict = Depends(current_user)):
    """列出本人擁有或已獲授權的案件，供登入後的案件選單使用。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT c.*, CASE WHEN c.worker_user_id=? THEN 1 ELSE 0 END AS is_owner "
            "FROM cases c LEFT JOIN grants g ON g.case_id=c.id "
            "WHERE c.worker_user_id=? OR "
            "(g.user_id=? AND g.revoked_at IS NULL AND g.expires_at>?) "
            "ORDER BY c.created_at DESC",
            (user["id"], user["id"], user["id"],
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ).fetchall()
        return [{
            "case_id": row["id"], "title": row["title"], "status": row["status"],
            "created_at": row["created_at"], "is_owner": bool(row["is_owner"]),
        } for row in rows]
    finally:
        conn.close()


@app.get("/cases/{case_id}")
def get_case(case_id: str, user: dict = Depends(current_user)):
    """案件詳情 + 我在這個案件能做/不能做什麼(直接餵前端畫面)。"""
    conn = get_conn()
    try:
        case, grant = _ensure_case_access(conn, case_id, user)

        scopes = set(grant["scopes"].split(",")) if grant and grant["scopes"] else set()
        revoked = bool(grant and grant["revoked_at"])
        capabilities = [
            {
                "name": t.name,
                "description": t.description,
                "scope": t.required_scope,
                "risk": t.risk,
                "in_scope": (t.required_scope in scopes) and not revoked,
                "high_risk": t.is_high_risk(),
            }
            for t in migrant_claim.build_tools()
        ]
        return {
            "case_id": case["id"],
            "title": case["title"],
            "status": case["status"],
            "verifier": migrant_claim.build_verifier().name,
            "acting_as": {
                "display_name": user["display_name"],
                "acting_for": user["acting_for"],
                "role_credential": user["role_credential"],
            },
            "grant": None if grant is None else {
                "id": grant["id"],
                "purpose": grant["purpose"],
                "scopes": sorted(scopes),
                "expires_at": grant["expires_at"],
                "revoked_at": grant["revoked_at"],
            },
            "capabilities": capabilities,
        }
    finally:
        conn.close()


@app.post("/cases/{case_id}/grants")
def add_grant(case_id: str, body: GrantIn, user: dict = Depends(current_user)):
    """移工授權另一個人(通常是仲介承辦人)進來協作。範圍預設比自己窄。"""
    conn = get_conn()
    try:
        case = _load_case(conn, case_id)
        if case["worker_user_id"] != user["id"]:
            raise HTTPException(403, "只有案件當事人(移工)能授權他人")
        target = conn.execute(
            "SELECT * FROM users WHERE email=?", (body.email,)
        ).fetchone()
        if target is None:
            raise HTTPException(404, "找不到這個使用者,請對方先註冊")
        scopes = set(body.scopes) if body.scopes else set(COLLAB_SCOPES)
        if not scopes or not scopes.issubset(DELEGATABLE_SCOPES):
            raise HTTPException(400, "授權包含不可委派的 scope")
        if target["role"] == "employer_officer":
            raise HTTPException(
                400, "雇主案件參與權由已驗證的聘僱關係配置，不能用一般 Grant 改寫"
            )
        role_scope_limits = {
            "worker": {"claim_prep"},
            "agency_officer": {"claim_prep"},
        }
        allowed_for_target = role_scope_limits.get(target["role"], set())
        if not scopes.issubset(allowed_for_target):
            raise HTTPException(400, "這個角色不能取得指定的 scope")
        if body.days_valid < 1 or body.days_valid > 90:
            raise HTTPException(400, "授權期限必須介於 1 到 90 天")
        gid = "grant-{}-{}".format(case_id.lower(), target["id"])
        conn.execute(
            "INSERT OR REPLACE INTO grants(id,case_id,user_id,purpose,scopes,expires_at,revoked_at) "
            "VALUES (?,?,?,?,?,?,NULL)",
            (gid, case_id, target["id"], "協助理賠文件整理",
             ",".join(sorted(scopes)), default_expiry(body.days_valid)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"grant_id": gid, "granted_to": body.email, "scopes": sorted(scopes)}


# ============ 執行動作(核心)=========================================
@app.post("/cases/{case_id}/act")
def act(case_id: str, body: ActIn, user: dict = Depends(current_user)):
    """一次動作 = 過政策閘 + 寫稽核鏈。引擎邏輯完全沿用 TrustAgent.act()。"""
    conn = get_conn()
    try:
        case, grant = _ensure_case_access(conn, case_id, user)

        agent = build_agent(conn, case_id, user, grant)
        try:
            result = agent.act(body.tool, confirmed=body.confirmed, **body.args)
        except TypeError as exc:
            raise HTTPException(400, "工具參數錯誤:{}".format(exc))

        return {
            "tool": result.tool,
            "allowed": result.decision.allowed,
            "code": result.decision.code,
            "reason": result.decision.reason,
            "value": result.value,
            "receipt_seq": result.receipt_seq,
            "fixture_note": migrant_claim.FIXTURE_NOTES.get(body.tool),
        }
    finally:
        conn.close()


# ============ 稽核鏈 ==================================================
@app.get("/cases/{case_id}/audit")
def get_audit(case_id: str, user: dict = Depends(current_user)):
    conn = get_conn()
    try:
        case, grant = _ensure_case_access(conn, case_id, user)
        _ensure_audit_access(case, grant, user)
        agent = build_agent(conn, case_id, user, grant)
        ok, bad, msg = agent.audit.verify()
        return {
            "entries": agent.audit.to_dicts(),
            "signed": agent.audit.signed,
            "verify": {"ok": ok, "bad_seq": bad, "message": msg},
        }
    finally:
        conn.close()


@app.post("/cases/{case_id}/audit/verify")
def verify_audit(case_id: str, user: dict = Depends(current_user)):
    conn = get_conn()
    try:
        case, grant = _ensure_case_access(conn, case_id, user)
        _ensure_audit_access(case, grant, user)
        agent = build_agent(conn, case_id, user, grant)
        ok, bad, msg = agent.audit.verify()
        return {"ok": ok, "bad_seq": bad, "message": msg}
    finally:
        conn.close()


@app.post("/cases/{case_id}/audit/tamper")
def tamper_audit(case_id: str, body: TamperIn, user: dict = Depends(current_user)):
    """demo 專用:故意改一筆,證明 verify 會抓到。上線要拿掉整個端點。"""
    if not security.ENABLE_TAMPER_DEMO:
        raise HTTPException(404, "此環境未啟用竄改示範")
    conn = get_conn()
    try:
        case, grant = _ensure_case_access(conn, case_id, user)
        if case["worker_user_id"] != user["id"]:
            raise HTTPException(403, "只有案件當事人能執行竄改示範")
        agent = build_agent(conn, case_id, user, grant)
        done = agent.audit.tamper(body.seq, body.field, body.value)
        if not done:
            raise HTTPException(400, "改不動:seq 不存在或欄位不允許")
        ok, bad, msg = agent.audit.verify()
        return {"tampered_seq": body.seq, "verify": {"ok": ok, "bad_seq": bad, "message": msg}}
    finally:
        conn.close()


# ============ 撤銷(機制 6)==========================================
@app.post("/grants/{grant_id}/revoke")
def revoke_grant(grant_id: str, user: dict = Depends(current_user)):
    conn = get_conn()
    try:
        grant = conn.execute("SELECT * FROM grants WHERE id=?", (grant_id,)).fetchone()
        if grant is None:
            raise HTTPException(404, "找不到這張授權")
        case = conn.execute("SELECT * FROM cases WHERE id=?", (grant["case_id"],)).fetchone()
        # 移工可以撤自己案件裡的任何授權;協作者只能撤自己的
        if case["worker_user_id"] != user["id"] and grant["user_id"] != user["id"]:
            raise HTTPException(403, "無權撤銷這張授權")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute("UPDATE grants SET revoked_at=? WHERE id=?", (now, grant_id))
        conn.commit()

        # 把「撤銷」這件事也寫進稽核鏈
        agent = build_agent(conn, grant["case_id"], user, None)
        agent.audit.append(user["display_name"], "-", "GRANT_REVOKED_BY_PRINCIPAL",
                           False, {"grant": grant_id})
    finally:
        conn.close()
    return {"grant_id": grant_id, "revoked_at": now}


@app.get("/")
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/api/status")
def api_status():
    verifier = migrant_claim.build_verifier()
    return {
        "service": "Migrant Insurance Infrastructure",
        "version": app.version,
        "verifier": verifier.name,
        "trust_mode": security.TRUST_MODE,
        "sandbox_cryptography": verifier.name == "vlei-sandbox",
        "production_vlei": False,
        "tamper_demo_enabled": security.ENABLE_TAMPER_DEMO,
        "cookie_secure": security.COOKIE_SECURE,
    }
