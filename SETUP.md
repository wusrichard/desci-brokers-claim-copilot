# 隊友上手指南

> DeSci Brokers｜移工職災保險 Claim Copilot
> repo：https://github.com/wusrichard/desci-brokers-claim-copilot

---

## 最快：30 秒跑起來

```bash
git clone https://github.com/wusrichard/desci-brokers-claim-copilot
cd desci-brokers-claim-copilot/agent
python3 run.py claim
```

**這樣就會動。** 不需要 `pip install`、不需要虛擬環境、不需要 Docker、不需要網路。

此時有兩格會走「退回模式」，畫面上會明白標出來：

- 母語理解 → 未設定金鑰，使用固定值
- 憑證驗證 → 找不到 vlei-sandbox，退回查表模式

功能不會壞，只是那兩格不是真的在算。要看完整版，往下做兩步設定。

---

## 可用指令

| 指令 | 做什麼 |
|---|---|
| `python3 run.py claim` | **理賠主線**：六步流程 + 仲介承辦人授權（錄影錄這支） |
| `python3 run.py demo` | 六項信任機制逐項演示 |
| `python3 run.py tour` | 同一引擎跑三個情境，證明引擎與情境分離 |
| `python3 run.py llm` | 檢查 API 金鑰與模型抽取是否正常 |
| `python3 run.py verify` | 驗證稽核鏈 → PASS |
| `python3 run.py tamper` | 竄改一筆後重驗 → FAIL |
| `python3 run.py audit` | 印出稽核紀錄 JSON |

---

## 設定 ①：模型金鑰（讓母語理解變成真的）

**各自去 https://openrouter.ai/keys 開一把，不要共用同一支。**
共用的話用量會混在一起，出問題也查不出是誰打的。

```bash
cd desci-brokers-claim-copilot/agent
cp .env.example .env
open -e .env          # 把金鑰填在 OPENROUTER_API_KEY= 後面
python3 run.py llm    # 驗證
```

`.env` 已被 `.gitignore` 擋住，不會進 repo。

**不要把金鑰貼進 LINE 群組、Notion、簡報或任何會截圖的地方。**

跑 `run.py llm` 成功的話會看到兩個測試：
第一個資訊完整 → 綠色「可自動進行」；
第二個只說「手痛」→ 黃色「需要人工複核」。

---

## 設定 ②：vLEI sandbox（讓憑證驗證變成真的）

一段指令建好完整信任鏈（GLEIF → QVI → 仲介法人 → 兩位承辦人），
並把已離職的林志豪的憑證撤銷：

```bash
cd desci-brokers-claim-copilot
git clone -q --depth 1 https://github.com/smpebble/vlei-sandbox
cd vlei-sandbox
S=scripts/vlei_sandbox.py
LEI=8945002HONGTAI00TW15

python3 $S init --force
python3 $S actor add --alias gleif  --registry gleifRegistry  --root
python3 $S actor add --alias qvi    --registry qviRegistry    --delegator gleif
python3 $S actor add --alias agency --registry agencyRegistry
python3 $S actor add --alias chen
python3 $S actor add --alias lin

QVI=$(python3 $S issue --type qvi --issuer gleif --holder qvi --lei $LEI \
      | grep -oE '[EF][A-Za-z0-9_-]{43}' | head -1)
LE=$(python3 $S issue --type le --issuer qvi --holder agency --lei $LEI --auth $QVI \
     | grep -oE '[EF][A-Za-z0-9_-]{43}' | head -1)
CHEN=$(python3 $S issue --type ecr --issuer agency --holder chen --lei $LEI \
       --person "陳美玲" --context-role "理賠承辦人" --auth $LE \
       | grep -oE '[EF][A-Za-z0-9_-]{43}' | head -1)
LIN=$(python3 $S issue --type ecr --issuer agency --holder lin --lei $LEI \
      --person "林志豪" --context-role "理賠承辦人" --auth $LE \
      | grep -oE '[EF][A-Za-z0-9_-]{43}' | head -1)

python3 $S revoke --said $LIN

echo "陳美玲 ECR: $CHEN"
echo "林志豪 ECR: $LIN"
```

`vlei-sandbox/` 已被 `.gitignore` 擋掉——它是第三方 MIT 專案，
放進我們的 repo 會多出一份不是我們寫的程式碼，交件時反而要解釋。

---

## ⚠️ 目前已知的坑：SAID 每次重建都會變

上面那段指令**每跑一次就產生一組新的 SAID**。
但 `agent/scenarios/claim_copilot.py` 裡的 `ECR_ACTIVE` / `ECR_REVOKED`
是語復那台機器建鏈時寫死的值。

**所以你自己建完鏈之後，程式碼裡那組對不上你的 sandbox，驗證會失敗。**
錯誤訊息只會說驗證沒過，不會告訴你是這個原因。

**暫時的解法**：把上面印出來的兩個 SAID 貼進 `agent/scenarios/claim_copilot.py`：

```python
ECR_ACTIVE  = "你剛剛印出來的 陳美玲 ECR"
ECR_REVOKED = "你剛剛印出來的 林志豪 ECR"
```

改完**不要 commit 這兩行**，否則會蓋掉別人的值。

> **待處理**：正確做法是讓程式自動從 sandbox 讀當前 SAID，而不是寫死。
> 改一個函式就好，還沒動。要動之前跟語復講一聲，避免兩個人同時改同一個檔案。

---

## 怎麼確認自己跑到「完整版」

跑 `python3 run.py claim`，開頭那個黃框應該長這樣：

```
1. 母語理解：真的呼叫模型（anthropic/claude-sonnet-5）
```

而不是「未設定金鑰，本次使用固定值」。

往下捲到「仲介承辦人授權」那一段，應該看到綠色的：

```
✓ 真實驗證：以 vlei-sandbox 執行，重算 SAID、驗簽章、查 TEL 撤銷狀態、遞迴至信任根
```

而不是「找不到 vlei-sandbox，退回查表模式」。

---

## 改程式碼時請注意

**引擎與情境是分開的，不要混。**

- `agent/trustagent/` — 引擎。**不含任何情境知識**，不應該出現「理賠」「健檢」「移工」這些字。
- `agent/scenarios/` — 情境。換皮只換這裡。

`run.py tour` 會跑三個情境驗證這件事，改完記得跑一次。

**假資料一定要標注。** 每個回傳固定值的函式，docstring 要寫明現況與真實版本該怎麼做，
並在 `FIXTURE_NOTES` 登記——那份會印在畫面上，所以錄影本身就帶著誠實聲明。
細節看 `agent/FIXTURES.md`。

標注錯了跟沒標一樣糟：接上真東西之後，記得把對應的標注一起改掉。

---

## 交件前的檢查

```bash
# 全指令回歸
cd agent && for c in claim demo tour verify audit tamper llm; do
  printf "%-8s " "$c"; python3 run.py $c >/dev/null 2>&1 && echo OK || echo FAIL
done

# 確認沒有金鑰混進 commit
cd .. && git log -p | grep -cE 'sk-or-v1-[A-Za-z0-9_-]{20,}'   # 應該是 0
```
