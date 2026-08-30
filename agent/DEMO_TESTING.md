# 前後端 Demo：啟動與測試

## 啟動

```bash
cd agent
./start_demo.sh
```

瀏覽器開啟 <http://127.0.0.1:8000>；API 文件位於 <http://127.0.0.1:8000/docs>。

Demo 帳號密碼都是 `demo1234`：

- `mai@demo.tw`：移工本人
- `meiling@hongtai.tw`：ECR 有效的仲介承辦人
- `zhihao@hongtai.tw`：ECR 已撤銷的前承辦人
- `taka@jinghong.tw`：晶宏電子授權的 Migrant Worker Manager（ECR 有效）

## 自動測試

```bash
cd agent
python3 -m backend.selftest
.venv-backend/bin/python -m backend.integration_test
```

第一支測試 TrustAgent、SQLite 稽核鏈、scope、撤銷與 vLEI；第二支從 HTTP 層測登入、案件、人工確認、有效／撤銷 ECR、存取控制及竄改偵測。兩者都使用臨時資料庫。

測試也涵蓋：Taka 雇主權限與隱私邊界、Verifier fail-closed、HttpOnly Cookie、CSRF、登入節流、CSP、scope 防升權，以及 Ed25519 稽核簽章驗證。

## 建議的手動驗收順序

1. 以阮氏梅登入，依序點擊六步流程。
2. 點「正式送出理賠申請」，確認第一次被攔，按本人確認後才放行。
3. 到「代理與授權」，切換為陳美玲；確認缺件清單能執行、保護紀錄因 scope 不足被擋。
4. 切換為林志豪；確認任何工具先被 `ROLE_NOT_VERIFIED` 擋下。
5. 切換為 Taka；確認自動進入「公司員工保險平台」，四項雇主任務可執行，且畫面清楚列出不可讀完整病歷、不可正式送件。
6. 回到阮氏梅，開啟「可驗證操作紀錄」，先驗證 PASS，再按「故意竄改一筆」看到 FAIL。

## 如何確認 vLEI 已接上

頁面右上角應顯示 `vLEI sandbox ✓`。也可執行：

```bash
curl -s http://127.0.0.1:8000/api/status
```

預期 `verifier` 為 `vlei-sandbox`。這代表本地 sandbox 會重算 SAID、驗 Ed25519 簽章並查 TEL；並不代表已連上正式 GLEIF／QVI production 網路。

`start_demo.sh` 會冪等確認兩條組織信任鏈都存在：仲介公司 ECR，以及
`GLEIF 模擬根 → QVI → 晶宏電子 LE → Taka Migrant Worker Manager ECR`。
私鑰只存在 git-ignored 的 `vlei-sandbox/.vlei/state.json`，不會寫入程式碼或 Git。

## 信任模式與安全邊界

```bash
# 錄影與合成資料 Demo（預設）
AGENT_TRUST_MODE=demo ./start_demo.sh

# 必須有可用 sandbox，否則組織代理操作一律拒絕
AGENT_TRUST_MODE=sandbox_strict ./start_demo.sh

# 正式 verifier 尚未串接，因此目前會安全地 fail closed
AGENT_TRUST_MODE=production_strict ./start_demo.sh
```

strict 模式預設停用公開註冊與 `/audit/tamper`。正式 HTTPS 部署另設 `COOKIE_SECURE=1`，並把 `ALLOWED_ORIGINS` 收斂到正式前端網域。
