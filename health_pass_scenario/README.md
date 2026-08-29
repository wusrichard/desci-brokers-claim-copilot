# 移工職安 Health Pass — 可驗證健康合規綠燈憑證

> DeSci Brokers ｜ Trustworthy AI Hackathon（8/29–8/31）
> **治理／信任設計 + Day1–2 build plan**。全部合成資料。

---

## 一句話

移工的職安健檢**資料不出廠**，只輸出一張**密碼學綠燈憑證（Health Pass）**；SGS 稽核員／品牌客戶掃碼就能離線確認「這位移工健康合規、可在指定環境作業」，**看不到任何一頁病歷**。健檢過期或移工離職 → 綠燈自動轉紅。

**Insurance/健檢 is the entry point. Worker protection is the purpose. RBA compliance is the business value. AI governance builds trust.**

---

## 為什麼是這題（初選/決選都吃）

- **大廠一定買單**：RBA 砍單是真的。巨大/捷安特因強迫勞動被美國 CBP 下 **WRO 暫扣令，貨卡海關近一年**；證件代管會讓 RBA 驗廠分數**直接歸零**、新專案被 Hold。
- **命中痛點 4（個資）**：現行人資為應付 RBA 職安稽查，把移工紙本健檢報告整疊攤開給稽核員翻 → 違反《個資法》第 6 條敏感個資（最高罰 50 萬）＋ RBA 道德重大缺失。**Health Pass 讓「顧了合規率、卻洩漏隱私」這個兩難消失。**
- **對到主辦口味**：8/22 講者就是 NGPay（移工 FinTech）＋ RBA，評審腦子裡就是這條線。

---

## 單一 Demo Flow（5 分鐘，只演這一條）

> 移工：阮氏梅（越南，電子二階代工廠）。事件：年度職安健檢。

1. **健檢資料落地不出廠** — 特約醫院把健檢報告寫進工廠內部加密伺服器（`input.original`：含居留證號、肺結核 X 光、B 肝帶原、病史…）。
2. **醫院醫師簽發 vLEI 憑證** — 職業醫學科醫師（ECR）用 Ed25519 簽一張「適任判定」ACDC（`適合高溫/高架作業`＋健檢日＋到期日＋報告 hash），鏈到醫院 LE → GLEIF。→ **出處為真**。
3. **APL 揭露最小化** — Agent 依 `masking_plan` 只把「綠燈判定＋hash＋到期日」送給稽核方；居留證號/X光/B肝/病史全留本地（收據只進指紋）。→ **沒有任何一方看到病歷**。
4. **稽核員掃碼離線驗證** — `apl verify` → **PASS**；當場 `apl break-receipt`（竄改一個欄位）→ **FAIL**。→ **可驗證證據**。
5. **撤銷 → 轉紅燈** — 健檢過期 or 移工離職 → `revoke` 憑證 → 綠燈變紅，稽核當場失效。→ **撤銷級聯**。
6. **B2B 戰情室** — 品牌 ESG 主管只看到聚合狀態：「健保卡自持率 100%、健檢綠燈覆蓋率 88%、1 筆黃燈已通知代工廠」。→ **可稽核、不觸個資**。

---

## 兩幕架構（引擎不變，換皮）

| | Act 1 · 揭露層 APL | Act 2 · 出處層 vLEI |
|---|---|---|
| 回答 | 「只揭露了綠燈，沒給病歷，這是收據」 | 「這張健康判定是真醫院真醫師簽的」 |
| 工具 | `OIA-LAB/apl-sidecar`（本情境包） | `smpebble/vlei-sandbox`（加一張 `healthpass` 憑證型別）|
| RBA 對應 | 痛點4 個資、Health & Safety | 供應鏈憑證信任鏈、Ethics |
| demo 高潮 | `verify` PASS → `break-receipt` FAIL | `revoke` 醫師/憑證 → 綠燈轉紅 |

> 這就是我先前幫你建的醫療理賠架構**換客戶**：保險審核方 → **SGS 稽核方**；理賠草案 → **Health Pass 綠燈**。引擎（APL＋vLEI＋六機制＋Verifier）原封不動。

---

## 六項信任機制對照（Demo 逐項打勾）

| # | 機制 | 這條 flow 怎麼演 |
|---|---|---|
| 1 | 代表誰 | Agent 代表**移工本人**；畫面常駐「代表：阮氏梅／健檢案 #HP-2026-0142」 |
| 2 | 授權範圍＋期限 | 移工同意「僅供 RBA 職安稽核用途，效期至下次健檢」 |
| 3 | 可執行動作 | 產生綠燈、回答稽核；**不得輸出原始病歷** |
| 4 | 高風險攔截 | 任何「調閱原始報告」請求 → 攔截、要移工＋醫院雙重確認 |
| 5 | 稽核追溯 | APL 簽章收據（誰驗了什麼綠燈）＋ vLEI KEL/TEL；RBA Incident→Evidence→Audit trail |
| 6 | 撤銷失效 | 過期/離職 → 撤銷 → 綠燈轉紅；撤醫師 ECR → 其所有綠燈同時垮 |

---

## 誠實限制（主動講＝加分，且 GLEIF 官方也這樣要求）

- **驗證 ≠ 可信**：vLEI 只證明「這張判定由授權醫師/醫院簽」，**不證明健檢內容正確、不證明工廠沒逼工**。GLEIF 官方 rules 區原文就寫 "does not assert that the Legal Entity is trustworthy... or compliant with any laws"。
- **APL 不保證**：不保證稽核方不另存、不保證意圖無法還原；它保證的是「揭露了什麼」的可驗證紀錄。
- **移工/醫師個人無 LEI**：憑證層用醫院 LE + 醫師 ECR；移工同意層是 KERI/ACDC 收據，不是 vLEI。刻意分層。
- **上線治理路徑**：mock PoC → 醫院取 LEI → QVI 依 EGF 對醫院 DAR/LAR 做身份保證 → 委發醫師 ECR → 驗證器 pin GLEIF root。

---

## Day 1 / Day 2 工時 + 四人分工

| 人 | 主責 | Day 1 交付 | Day 2 交付 |
|---|---|---|---|
| **語復**（後端/Agent） | vLEI 憑證 + Verifier + Agent | sandbox 加 `healthpass` 憑證型別、跑通鏈+撤銷級聯 | 接 APL 收據，串成一條 verify 流程 |
| **映柔**（Builder） | APL Health Pass 情境包 + 資料 | `apl demo` 跑通本情境包（verify/break） | 綠燈/紅燈 QR 產生、demo 腳本 |
| **彭**（PM/資料科學） | 治理敘事 + 公平性/風險 | RBA 痛點與真實案例整理成簡報 | 多語準確率/公平性一頁 + 主述 |
| **怡茜**（UI/UX） | 移工 App + B2B 戰情室 | 移工同意畫面 + 綠燈卡 | 稽核掃碼畫面 + 戰情室 dashboard |

**凍結規則**：Day 2 下午只做整合＋彩排，**不加新功能**。別碰 KERIA/Signify（Real Mode）、別做微型貸款/消費分期/仲介信任分數——那些留在簡報的「Roadmap」頁，不進 build。

---

## 怎麼跑

```bash
pip install apl-sidecar
apl demo --scenario /Users/wuyufu/Downloads/TrustAgentHackthon/build/health_pass_scenario
apl verify apl-out/receipt.json          # PASS ✓
apl break-receipt apl-out/receipt.json   # FAIL ✗
```

vLEI 憑證鏈（加 `healthpass` 型別後）：見 `../medical_claim_scenario/README.md` 的建鏈指令，把 `diag` 換成 `healthpass`、診斷欄位換成 `{fitness, checkDate, expiry, reportHash}`。

- APL Sidecar：https://github.com/OIA-LAB/apl-sidecar （runtime FSL-1.1-ALv2 / verifier Apache-2.0；交件須揭露）
- vLEI Sandbox：https://github.com/smpebble/vlei-sandbox （MIT）

---

## Pitch 一句話

> 「傳統 RBA 稽核是人資的惡夢、個資的漏洞、大廠的未爆彈。我們用一張**可驗證的健康綠燈憑證**——資料不出廠、稽核掃碼即驗、過期自動轉紅——讓大廠**免翻紙本、持續合規、零個資外洩**。」
