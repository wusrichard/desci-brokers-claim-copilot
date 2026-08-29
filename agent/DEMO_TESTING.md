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
- `sgs@audit.tw`：尚未獲授權的稽核方

## 自動測試

```bash
cd agent
python3 -m backend.selftest
.venv-backend/bin/python -m backend.integration_test
```

第一支測試 TrustAgent、SQLite 稽核鏈、scope、撤銷與 vLEI；第二支從 HTTP 層測登入、案件、人工確認、有效／撤銷 ECR、存取控制及竄改偵測。兩者都使用臨時資料庫。

## 建議的手動驗收順序

1. 以阮氏梅登入，依序點擊六步流程。
2. 點「正式送出理賠申請」，確認第一次被攔，按本人確認後才放行。
3. 到「代理與授權」，切換為陳美玲；確認缺件清單能執行、保護紀錄因 scope 不足被擋。
4. 切換為林志豪；確認任何工具先被 `ROLE_NOT_VERIFIED` 擋下。
5. 回到阮氏梅，開啟「稽核紀錄」，先驗證 PASS，再按「故意竄改一筆」看到 FAIL。

## 如何確認 vLEI 已接上

頁面右上角應顯示 `vLEI sandbox ✓`。也可執行：

```bash
curl -s http://127.0.0.1:8000/api/status
```

預期 `verifier` 為 `vlei-sandbox`。這代表本地 sandbox 會重算 SAID、驗 Ed25519 簽章並查 TEL；並不代表已連上正式 GLEIF／QVI production 網路。
