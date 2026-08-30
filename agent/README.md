# 可信 AI Agent 骨架 — TrustAgent

> DeSci Brokers｜Trustworthy AI Hackathon 2026
> 六項信任機制的執行引擎。**情境無關**——健檢綠燈與醫療理賠共用同一套引擎。

---

## 60 秒跑起來

```bash
python3 run.py claim
```

零外部相依，Python 3.8+ 即可。不需要 pip install、不需要 Docker、不需要網路。

| 指令 | 做什麼 |
|---|---|
| `python3 run.py claim` | **理賠主線**：六步流程 + 仲介承辦人授權（**錄影錄這支**） |
| `python3 run.py demo` | 六項信任機制逐項演示 |
| `python3 run.py tour` | 同一引擎跑三個情境，證明可換皮 |
| `python3 run.py verify` | 驗證稽核鏈 → PASS |
| `python3 run.py tamper` | 竄改一筆後重驗 → FAIL |
| `python3 run.py audit` | 印出稽核紀錄 JSON |

主線是**移工職災理賠**（Migrant Insurance Infrastructure，依 0829 Concept deck）。
健檢綠燈已降級為理賠包裡的一項證據，不再是主軸；RBA 是企業端的副產品，不是產品定位。

---

## 架構

```
run.py                  demo 驅動（輸出即錄影素材）
trustagent/             引擎 — 不含任何情境知識
  models.py             Principal / Grant / Tool / Decision
  gate.py               政策閘：撤銷 > 到期 > 範圍 > 風險
  audit.py              雜湊鏈式唯附加紀錄 + 竄改偵測
  verifier.py           出處驗證介面（Mock / vLEI sandbox）
  agent.py              執行迴圈
  console.py            終端輸出
scenarios/              情境 — 換皮只換這裡
  migrant_claim.py      移工職災理賠（主線）
  health_pass.py        職安健檢綠燈（現為理賠的證據之一）
  medical_claim.py      個人醫療理賠（證明引擎可複用）
```

**分層原則**：`trustagent/` 底下沒有任何一行知道「健檢」或「理賠」。
換情境 = 新增一個 `scenarios/*.py`，引擎一行不動。`run.py tour` 就是這件事的證明。

---

## 六項信任機制對應

| # | 機制 | 實作位置 | demo 步驟 |
|---|---|---|---|
| 1 | 代表誰 | `models.Principal`，常駐畫面橫幅 | 全程 |
| 2 | 授權範圍＋期限 | `models.Grant.scopes` / `expires_at` | 3 |
| 3 | 可執行動作 | `models.Tool.required_scope` / `risk` | 1 |
| 4 | 高風險攔截 | `gate.PolicyGate` | 5、6 |
| 5 | 稽核追溯 | `audit.AuditLog` 雜湊鏈 | 7、8 |
| 6 | 撤銷失效 | `Grant.revoke()` | 9 |

機制 4 演兩種攔截，理由不同：

- **攔截 A** `read_raw_report` — scope 不在授權內，直接擋
- **攔截 B** `share_with_new_auditor` — scope 通過，但動作不可逆 → 停下等人工確認 → 帶 `confirmed=True` 重送才放行

---

## 組織對個人授權（新加坡 Corppass 模式）

`run.py claim` 最後兩步演的是三國比較研究裡最有價值的一條啟示：
**驗證的重點不是「這家公司是真的」，而是「這位承辦人是否被公司授權處理本案」。**

同一家仲介、同一個請求，差別只在那個人的角色憑證還有沒有效：

| 承辦人 | 角色憑證 | 結果 |
|---|---|---|
| 陳美玲（在職） | 有效 ECR | ✓ 可協助整理文件 |
| 陳美玲（在職） | 有效 ECR | ✕ 但碰不到雇主責任紀錄（scope 較窄） |
| 林志豪（已離職） | ECR 已撤銷 | ✕ 同一請求直接擋下 |

實作在 `Principal.acting_for` / `role_credential` 與 `agent._check_delegation()`。
代理關係的驗證刻意排在政策閘**之前**——連「你是誰的人」都沒確認，談授權範圍沒有意義。

---

## 六步理賠流程

`Verify → Understand → Match → Claim → Track → Record`，對應 `migrant_claim.py` 的工具。
其中 **Understand** 是 AI 真正做事的一格：移工用越南文描述事故，
Agent 結構化成 claim event 並標出信心值；低信心或高風險案件轉人工。

---

## 兩個設計決定（值得在簡報講）

**1. 遮罩規則不交給 LLM。**
哪些欄位可以外送，是 `scenarios/*.py` 裡的宣告式清單，不是模型判斷。
規則不會幻覺；這一格刻意不用 AI。

**2. 稽核鏈自帶，不依賴外部套件。**
`audit.py` 用 stdlib 的 sha256 做雜湊鏈，每筆含前一筆雜湊。
改任一欄位，該筆以後的鏈全部對不上 → `verify` 立刻 FAIL。
有安裝 `cryptography` 時會額外加 Ed25519 簽章，沒有也照跑。

**被擋下來的嘗試一樣寫進紀錄**——那才是攔截有效的證據。

---

## 接 vLEI

`verifier.py` 定義介面。理賠情境會在專案根目錄找到 `vlei-sandbox` CLI 與 `.vlei/state.json` 時自動使用 `VleiVerifier`，否則降級為 `MockVerifier`。手動指定方式：

```python
from trustagent import VleiVerifier
verifier = VleiVerifier(sandbox_dir="/path/to/vlei-sandbox")
```

它會呼叫 `python3 scripts/vlei_sandbox.py verify --said <SAID>`，
解析結果回傳 `VerificationResult`。sandbox 沒裝好時回傳失敗而不是拋例外——
現場 demo 不會因此整個掛掉。

憑證鏈建立指令見 [vlei-sandbox](https://github.com/smpebble/vlei-sandbox)（MIT）。

---

## 資料

全部為**合成資料**，見 `../health_pass_scenario/`。
`input.original.example.txt` 檔頭標明「虛構合成資料，非真實個資」。
無任何真實醫療、金融或政府資料。

---

## 第三方套件

| 套件 | 授權 | 用途 |
|---|---|---|
| Python 標準函式庫 | PSF | 全部核心功能 |
| `cryptography`（選用） | Apache-2.0 / BSD | Ed25519 簽章，未安裝時自動略過 |
| [vlei-sandbox](https://github.com/smpebble/vlei-sandbox) | MIT | vLEI 信任鏈與撤銷（Day 2 接入） |
| [apl-sidecar](https://github.com/OIA-LAB/apl-sidecar) | runtime FSL-1.1-ALv2 / verifier Apache-2.0 | 揭露最小化層（選用） |

---

## 誠實限制

- `MockVerifier` 不做真正的密碼學驗證，只是查表。真驗證在 `VleiVerifier`。
- 雜湊鏈證明「紀錄未被竄改」，不證明「紀錄當初寫得對」。
- vLEI 證明出處與授權，**不證明健檢內容正確、不證明工廠合規**——
  GLEIF 官方在憑證規則區塊裡就是這樣寫的。
