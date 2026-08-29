# 移工職災保險 Claim Copilot

> **DeSci Brokers**｜Trustworthy AI Hackathon 2026
> 一個代表**移工本人**的可信 AI Agent：協助理解保障、準備理賠、追蹤進度，
> 但不得越權讀取、不得替本人送件。

---

## 60 秒跑起來

```bash
cd agent && python3 run.py claim
```

零外部相依，Python 3.8+ 即可。不需要 `pip install`、不需要 Docker、不需要網路。

| 指令 | 做什麼 |
|---|---|
| `python3 run.py claim` | **理賠主線**：六步流程 + 仲介承辦人授權 |
| `python3 run.py demo` | 六項信任機制逐項演示 |
| `python3 run.py tour` | 同一引擎跑三個情境，證明引擎與情境分離 |
| `python3 run.py llm` | 檢查 API 金鑰與模型抽取是否正常 |
| `python3 run.py verify` | 驗證稽核鏈 → PASS |
| `python3 run.py tamper` | 竄改一筆後重驗 → FAIL |
| `python3 run.py audit` | 印出稽核紀錄 JSON |

---

## 這個作品在解什麼

一次職災理賠跨越移工、仲介、雇主、醫療與保險五方。核心問題不是「沒有資料」，
而是**資料分散、身份與授權難驗證、處理過程缺乏共同可信紀錄**。

移工端最痛的三件事：

1. 不知道自己有哪些保障、是否仍有效（**漏賠**）
2. 語言與制度門檻高，只能依賴仲介（**資訊不對稱**）
3. 缺件反覆補，看不到案件進度（**權力不對等**）

六步流程 `Verify → Understand → Match → Claim → Track → Record` 逐項回應這些痛點，
而企業端在處理理賠的同時，自然累積出可用於 RBA / ESG 稽核的證據。
**RBA 是副產品，不是產品主軸。**

---

## 六項信任機制

| # | 機制 | 實作位置 |
|---|---|---|
| 1 | 代表誰 | `models.Principal`，畫面常駐橫幅 |
| 2 | 授權範圍＋期限 | `models.Grant.scopes` / `expires_at` |
| 3 | 可執行動作 | `models.Tool.required_scope` / `risk` |
| 4 | 高風險攔截 | `gate.PolicyGate` |
| 5 | 稽核追溯 | `audit.AuditLog` 雜湊鏈 |
| 6 | 失效與撤銷 | `Grant.revoke()`、憑證撤銷 |

外加**組織對個人授權**（對應新加坡 Corppass）：
驗的不只是「這家公司是真的」，而是「**這位承辦人被公司授權處理本案**」。
`run.py claim` 最後兩步演的就是這個——同一家仲介、同一個請求，
在職承辦人放行，已離職承辦人被擋。

---

## 專案結構

```
build/
├── README.md                    ← 你正在讀的這份
├── .gitignore                   金鑰、大檔、Python 產物
│
├── agent/                       可信 Agent 骨架
│   ├── run.py                   demo 驅動（輸出即錄影素材）
│   ├── README.md                架構說明與設計決定
│   ├── FIXTURES.md              ⚠️ 假資料清單，交件前必讀
│   ├── .env.example             金鑰欄位範本（.env 本身不進 repo）
│   │
│   ├── trustagent/              引擎 — 不含任何情境知識
│   │   ├── models.py            Principal / Grant / Tool / Decision
│   │   ├── gate.py              政策閘：撤銷 > 到期 > 範圍 > 風險
│   │   ├── audit.py             雜湊鏈式唯附加紀錄 + 竄改偵測
│   │   ├── verifier.py          出處驗證介面（Mock / vLEI sandbox）
│   │   ├── llm.py               OpenRouter 客戶端（stdlib，零相依）
│   │   ├── agent.py             執行迴圈
│   │   └── console.py           終端輸出
│   │
│   └── scenarios/               情境 — 換皮只換這裡
│       ├── claim_copilot.py     移工職災保險理賠（主線）
│       ├── health_pass.py       職安健檢綠燈（現為理賠的證據之一）
│       └── medical_claim.py     個人醫療理賠（證明引擎可複用）
│
├── health_pass_scenario/        合成資料：健檢報告與遮罩計畫
└── medical_claim_scenario/      合成資料：醫療理賠情境包
```

**分層原則**：`trustagent/` 底下沒有任何一行知道「理賠」或「健檢」。
換情境只需新增一個 `scenarios/*.py`，引擎一行不動。`run.py tour` 就是這件事的證明。

---

## AI 與密碼學的分工

> **AI 負責理解與代理，密碼學負責證明，人類負責不可逆的那一下。**

| 環節 | 誰做 |
|---|---|
| 母語事故理解 | AI（實際呼叫模型） |
| 出處與授權證明 | 密碼學（AI 完全不參與） |
| 決定遮罩哪些欄位 | **宣告式規則——刻意不讓 AI 決定，規則不會幻覺** |
| 正式送件 | 人類確認（不可逆動作一律攔截） |

**轉人工的判斷用欄位完整性，不用信心分數門檻。**
必填欄位（事故日期、受傷部位、事故機轉、是否因執行職務）少任一項，
或模型自己標記為推測而非讀取，就轉人工。
理由：分數門檻在問答時站不住，欄位完整性說得出口也能當場示範。

---

## 設定 API 金鑰（選用）

不設也能跑——母語理解會退回固定值並在畫面標明。

```bash
cd agent
cp .env.example .env      # 填入 OPENROUTER_API_KEY
python3 run.py llm        # 驗證金鑰是否生效
```

`.env` 已被 `.gitignore` 擋住。**不要把金鑰貼進簡報、README 或任何會截圖的地方。**

---

## ⚠️ 誠實限制

**請先讀 [`agent/FIXTURES.md`](agent/FIXTURES.md)。** 摘要：

- 所有資料為**合成資料**，無任何真實醫療、金融或政府資料
- 除母語理解外，其餘工具回傳的都是**寫死的固定值**
- 憑證驗證目前為 **mock 模式**，未執行真正的密碼學驗證
- SAID 為可讀假字串，非真實 CESR 編碼；LEI 為虛構法人但**檢查碼格式有效**
- **vLEI 證明的是出處與授權，不證明內容正確、也不證明企業合規**——
  GLEIF 官方文件本身就這樣寫

程式執行時會在畫面上標出每一格的實際來源，錄影本身即帶有誠實聲明。

---

## 第三方套件與授權

| 套件 | 授權 | 用途 |
|---|---|---|
| Python 標準函式庫 | PSF | 全部核心功能 |
| `cryptography`（選用） | Apache-2.0 / BSD | Ed25519 簽章，未安裝時自動略過 |
| [vlei-sandbox](https://github.com/smpebble/vlei-sandbox) | MIT | vLEI 信任鏈與撤銷 |
| [apl-sidecar](https://github.com/OIA-LAB/apl-sidecar) | runtime FSL-1.1-ALv2 / verifier Apache-2.0 | 揭露最小化層（選用） |
| OpenRouter API | 服務條款 | 母語事故理解 |

---

## 團隊

**DeSci Brokers**｜彭彥菱（PM）・吳語復（後端／Agent）・吳映柔（Builder）・沈怡茜（UI/UX）
