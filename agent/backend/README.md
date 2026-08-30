# 後端骨架 — 從「一個 agent 演給你看」到「多方真的登入協作」

> DeSci Brokers｜Trustworthy AI Hackathon 2026
> 這一層讓 [trustagent](../trustagent/) 引擎變成一個大家連得進來的服務。
> **引擎一行不動**,只加了三件事:持久化、認證、HTTP 端點。

---

## 60 秒跑起來

```bash
cd agent
./start_demo.sh
```

前端：<http://localhost:8000>　互動式 API 文件：<http://localhost:8000/docs>

完整測試與錄影操作順序見 [`../DEMO_TESTING.md`](../DEMO_TESTING.md)。

示範帳號(密碼都是 `demo1234`):

| email | 角色 | 說明 |
|---|---|---|
| `mai@demo.tw` | 移工 阮氏梅 | 案件當事人,可建案、可授權他人、可撤銷 |
| `meiling@hongtai.tw` | 仲介承辦人 陳美玲 | ECR 有效 → 代理關係驗證通過 |
| `zhihao@hongtai.tw` | 仲介承辦人 林志豪 | ECR 已撤銷 → 同一請求被 `ROLE_NOT_VERIFIED` 擋下 |
| `taka@jinghong.tw` | 雇主 Taka | 晶宏電子授權的 Migrant Worker Manager，ECR 有效 |

---

## 跟現在的 CLI 差在哪

| 面向 | 現在 `run.py`(CLI) | 這個後端 |
|---|---|---|
| 稽核紀錄 | 記憶體 list,程序結束就沒 | SQLite `audit_entries` 表,跨 session 共享同一條鏈 |
| 「代表誰」 | `build_principal()` 寫死阮氏梅 | 誰登入,Principal 就是誰 |
| 授權 Grant | 每次執行現造,`revoke()` 只影響這次執行 | 存 DB,任一 session 可查詢/撤銷,對所有人立即生效 |
| 多方協作 | 假的 — 同一支腳本依序 new 好幾個 agent 物件 | 真的 — 移工、仲介與雇主登入同一個案件 |
| 認證 | 無 | PBKDF2 密碼 + HMAC session、HttpOnly Cookie、CSRF 與登入節流 |
| 對外介面 | 只有終端輸出 | 一組 HTTP 端點(見下表) |
| 簽章金鑰 | 每次啟動重新 generate | 存 `.secrets/`,重啟沿用 |

**沒變的**:`PolicyGate` 判定順序、`Decision` 決策碼、`Tool` 定義、雜湊鏈演算法、`Verifier` 介面、
`scenarios/migrant_claim.py` 的工具註冊方式。`SqliteAuditLog` 直接重用 `trustagent.audit.Entry` 的 `compute_hash()`。

---

## 檔案

```
backend/
  server.py       FastAPI 應用 + 全部端點
  db.py           SQLite schema 與連線(只用標準庫 sqlite3)
  auth.py         密碼雜湊 + session token + CSRF token
  security.py     strict/demo 模式、CORS、CSRF、節流、大小限制與安全標頭
  audit_store.py  SqliteAuditLog — 與 trustagent.AuditLog 介面相容的持久化版本
  identity.py     User 資料列 → Principal / Grant → 組出 TrustAgent
  provision_vlei_demo.py  冪等建立仲介與 Taka 的 sandbox vLEI 憑證鏈
  seed.py         建示範帳號與案件
  selftest.py     不需要 FastAPI 的相容性測試(對照 run.py claim 的每一步)
```

---

## 端點對照(CLI → API)

| `run.py` 的動作 | API |
|---|---|
| — 註冊 / 登入 | `POST /register`、`POST /login`、`GET /me` |
| 登入後案件選單 | `GET /cases` |
| `build_agent()` 內建的移工授權 | `POST /cases`(建案時自動發) |
| 「移工授權仲介承辦人」(claim 最後兩步的前提) | `POST /cases/{id}/grants` |
| `agent.capabilities()` 的授權內/外表格 | `GET /cases/{id}`(回 `capabilities`) |
| `run.py claim` 的六步 `agent.act(...)` | `POST /cases/{id}/act` |
| Taka 的雇主聘僱／事故／加保／待辦工具 | 同一個 `POST /cases/{id}/act` |
| `run.py audit` | `GET /cases/{id}/audit` |
| `run.py verify` | `POST /cases/{id}/audit/verify` |
| `run.py tamper` | `POST /cases/{id}/audit/tamper`(demo 專用,上線移除) |
| 機制 6 撤銷 | `POST /grants/{id}/revoke` |

### `POST /cases/{id}/act` 請求格式

```json
{ "tool": "understand_incident", "args": { "lang": "vi" }, "confirmed": false }
```

回傳就是 `ActionResult` 攤平:`allowed` / `code` / `reason` / `value` / `receipt_seq` / `fixture_note`。

---

## 一條可以直接錄影的 demo 流程(curl)

```bash
BASE=http://localhost:8000
tok() { curl -s $BASE/login -H 'content-type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"demo1234\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])'; }

MAI=$(tok mai@demo.tw)
CID=$(curl -s $BASE/cases -H "authorization: Bearer $MAI" -H 'content-type: application/json' \
  -d '{"title":"職災理賠"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["case_id"])')

# 移工走六步
for T in verify_employment match_coverage list_missing_documents track_status build_protection_record; do
  curl -s $BASE/cases/$CID/act -H "authorization: Bearer $MAI" -H 'content-type: application/json' \
    -d "{\"tool\":\"$T\"}" | python3 -m json.tool
done

# 不可逆動作:先被攔,帶 confirmed 才放行
curl -s $BASE/cases/$CID/act -H "authorization: Bearer $MAI" -H 'content-type: application/json' -d '{"tool":"submit_claim"}'
curl -s $BASE/cases/$CID/act -H "authorization: Bearer $MAI" -H 'content-type: application/json' -d '{"tool":"submit_claim","confirmed":true}'

# 移工授權在職承辦人 → 她能整理文件,但碰不到雇主責任紀錄
curl -s $BASE/cases/$CID/grants -H "authorization: Bearer $MAI" -H 'content-type: application/json' -d '{"email":"meiling@hongtai.tw"}'
MEI=$(tok meiling@hongtai.tw)
curl -s $BASE/cases/$CID/act -H "authorization: Bearer $MEI" -H 'content-type: application/json' -d '{"tool":"list_missing_documents"}'
curl -s $BASE/cases/$CID/act -H "authorization: Bearer $MEI" -H 'content-type: application/json' -d '{"tool":"build_protection_record"}'

# 已離職承辦人:同一請求,直接被擋
curl -s $BASE/cases/$CID/grants -H "authorization: Bearer $MAI" -H 'content-type: application/json' -d '{"email":"zhihao@hongtai.tw"}'
ZHI=$(tok zhihao@hongtai.tw)
curl -s $BASE/cases/$CID/act -H "authorization: Bearer $ZHI" -H 'content-type: application/json' -d '{"tool":"list_missing_documents"}'

# 稽核鏈:驗證 → 竄改 → 再驗證
curl -s -XPOST $BASE/cases/$CID/audit/verify -H "authorization: Bearer $MAI"
curl -s $BASE/cases/$CID/audit/tamper -H "authorization: Bearer $MAI" -H 'content-type: application/json' -d '{"seq":3,"field":"code","value":"OK"}'
```

---

## 前端已接的五個畫面(對應 25% Demo 呈現分)

1. **登入頁** → `POST /login`,拿 token
2. **案件面板** → `GET /cases/{id}`:常駐「我代表誰」橫幅、scope、`capabilities`(授權內/外 + 高風險標記)、動作按鈕
3. **不可逆動作確認 modal** → 先送不帶 `confirmed`,收到 `NEEDS_HUMAN_CONFIRMATION` 後彈窗,按確認再送 `confirmed:true`
4. **可驗證操作紀錄頁** → `GET /cases/{id}/audit`:案件本人可即時驗證 PASS/FAIL 與竄改示範
5. **雇主員工保險平台** → Taka 的有效 ECR、公司 LEI、四項雇主任務與不可存取邊界

---

## 誠實限制(沿用 [FIXTURES.md](../FIXTURES.md),再加後端這層)

- 認證已有 HttpOnly/SameSite Cookie、CSRF、PBKDF2、HMAC token 與單程序 rate limit；仍沒有 email 驗證、MFA、refresh token 或跨節點集中節流
- `tamper` 端點只在 demo 模式預設開啟，strict 模式預設回 404
- 授權模型仍是應用層 DB 記錄,**不是**簽章式同意 ACDC(那是 Phase 1)
- 不提供外部稽核人員登入角色；Agent 產生可驗證證據，但不宣稱取代獨立第三方稽核
- 憑證驗證走 `scenarios.migrant_claim.build_verifier()`；demo 可降級 Mock，strict 找不到可信 Verifier 就回 `VERIFIER_UNAVAILABLE`
- 六步與雇主工具除 `understand_incident` 外全是固定值，畫面與 API 會明確標示 fixture
