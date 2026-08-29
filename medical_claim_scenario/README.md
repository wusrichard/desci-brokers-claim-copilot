# DeSci Brokers — 個人醫療理賠協作 Agent（治理／信任設計）

> 可信 AI Agent 原型：**「有同意才能看，有授權才能送」**。
> 本資料夾是 Act 1（揭露最小化層）的 APL Sidecar 情境包，全部為合成資料。

---

## 這是什麼

一個代表**保戶本人**的理賠協作 Agent。保戶回報住院/手術後，Agent 比對跨公司、
跨年代保單、列缺件、草擬申請書；但**只在保戶授權範圍內讀資料，送件前一定回到保戶確認**，
且每一步都留下可離線驗證的簽章收據。

對應痛點（皆已網路查證，見提案文件）：
- 痛點 3：病歷調閱範圍常被質疑「超出本次理賠所需」（個資法比例原則）← **本層主打**
- 痛點 1/2：文件不齊反覆補件、病歷調閱冗長
- 痛點 4：核保/理賠爭議占保險申訴大宗

---

## 兩幕架構（分兩輪做，先能動再加深）

| | Act 1 · 揭露層（APL Sidecar） | Act 2 · 出處層（vLEI Sandbox） |
|---|---|---|
| 回答 | 「Agent 只揭露了必要資料，這是收據」 | 「這份診斷證明是真醫師、真醫院簽的」 |
| 工具 | `OIA-LAB/apl-sidecar`（本資料夾） | `smpebble/vlei-sandbox`（Act 2 再接） |
| 技術 | 遮罩最小化 + Ed25519 簽章收據 + 離線驗證 + 竄改偵測 | KERI/ACDC 信任鏈 + I2I + root pinning + 撤銷級聯 |
| 主痛點 | 痛點 3（揭露範圍/比例原則） | 醫院文件出處（人工對章、電話確認醫師） |
| demo 高潮 | `apl verify` PASS → `apl break-receipt` FAIL | `revoke` 醫師 ECR → 診斷證明整條驗證失敗 |
| 風險 | 低（純情境包，不改 runtime，離線） | 中（加 ~8 行 schema，mock 模式，不碰 Docker） |

兩幕相接點：Agent 讀到的診斷證明先過 **Act 2 vLEI 驗證**（確認出處為真）→ 再進
**Act 1 APL 揭露最小化**（只把必要欄位送給保險公司/詐欺偵測，並簽收據）。
vLEI 管「文件真不真」，APL 管「揭露多不多」，兩者不重疊。

---

## 怎麼跑 Act 1（60 秒）

```bash
pip install apl-sidecar          # 或 pipx install apl-sidecar（隔離 CLI）
# 把本資料夾複製進 apl-sidecar 的 examples/ 或直接指路徑
apl demo --scenario ./medical_claim_scenario   # 產生 apl-out/{exposure.html, receipt.json, assessment.md}
apl inspect apl-out                             # 看三種視角：完整本地 / 保險審核方 / 詐欺偵測方
apl verify apl-out/receipt.json                 # PASS ✓（雜湊與簽章一致）
apl break-receipt apl-out/receipt.json          # FAIL ✗（改一個欄位就被離線驗證器擋下）
```

> ⚠️ 需先確認 `apl demo` 帶自訂情境的實際旗標名（原始碼 `run(scenario_dir=...)` 支援；
> 安裝後 `apl demo --help` 對一下是 `--scenario` 還是別的）。跑不掛就用 `run-mock`。

### 這個情境包演什麼（八個檔案）
- `input.original.example.txt` — 王先生完整卷宗：含身分證、精神科/B肝/家族史、3 張保單。**模型其實只需要本次住院那幾項。**
- `masking_plan.yaml` — 宣告哪些是 local-only（身分證/無關病史/保單號），哪些是必要保留訊號。
- `local_only.json` — 敏感值，只留在本地，收據裡只進「指紋(hash)」不進內容。
- `provider_a_payload.txt` — 送「理賠審核方」：只有 ICD-10/日期/手術/金額/給付類別。
- `provider_b_payload.txt` — 送「詐欺偵測方」：只有去識別化樣態（金額級距/手術碼/天數）。
- `mock_answer_a/b.txt` — 兩方的離線確定性回覆。
- `final_rehydrated_answer.txt` — 本地把個資接回，產出理賠草案 + 送件前確認勾選。

**關鍵：沒有任何單一外部方看到完整卷鎖**（`no_single_provider_saw_full`），
收據把「誰看了哪些字元、多少比例」簽起來——這就是比例原則的可驗證證據。
詐欺偵測方(provider B)只拿樣態，正好讓彭的 ML 詐欺模型接在後面、拿乾淨去識別化資料算。

---

## 六項信任機制對照（Demo 逐項打勾）

| # | 機制 | 這個作品怎麼演 | 來自 |
|---|---|---|---|
| 1 | 代表誰（Principal） | 畫面常駐「此 Agent 代表：王大明／案件 #CLM-2026-0810」 | 應用層 |
| 2 | 授權範圍＋期限 | 保戶勾選「僅本次住院診斷+收據，30 天」 | 應用層 + APL masking_plan |
| 3 | 可執行動作 | 讀取/比對/草擬 ✓；送出 ✗ | 應用層 |
| 4 | 高風險攔截 | 送件前強制人工確認（final answer 的勾選） | 應用層 |
| 5 | 稽核／可追溯 | APL 簽章收據（誰看了什麼）+ vLEI 的 KEL/TEL append-only log | APL + vLEI |
| 6 | 撤銷後失效 | 撤銷同意→Agent 讀不到；撤醫師 ECR→其診斷證明全塌 | 應用層 + vLEI 撤銷級聯 |

---

## 簡報骨架（對齊 GLEIF 評審框架：Mandate / Workload / Transaction）

1. **痛點（35% 場景契合）** — 保戶跨保單看不懂能賠什麼；保險公司過度調病歷（比例原則爭議）。附查證數據。
2. **Mandate — 誰可行動** — Agent 代表保戶，授權有範圍與期限，可撤銷。
3. **Workload — 什麼在呼叫** — Agent 的 3~5 個 MCP tool（查條款/比對/列缺件），逐條引用條款出處、標信心。
4. **Transaction / Evidence — 什麼夠真** — Act 1 揭露收據（apl verify/break）+ Act 2 診斷證明 vLEI 驗證。
5. **Governance Gap — 治理缺口（誠實面對）** — 見下。
6. **現場 Demo** — 授權→比對→草擬→送件攔截→查稽核→撤銷級聯。

---

## 誠實界定範圍（主動講，比被評審戳好）

- **驗證 ≠ 可信**：vLEI 只證明「這份診斷書由有授權的醫師代表已驗證醫院所簽」，**不證明診斷本身正確、也不證明沒詐保**。詐欺偵測是另一層（ML）。
- **APL 不保證**：不保證供應商沒留存、不保證意圖無法還原、不等於法遵。它保證的是「揭露了什麼」的可驗證紀錄。
- **病人沒有 LEI**：同意/揭露層不是 vLEI（保戶非法人）；vLEI 只用在「醫療文件出處」。刻意分層。
- **LEI 有年費**：醫院/診所採用障礙，商業模式走 Validation Agent（折進既有 KYC）。
- **自簽憑證真驗證器不收**：本作品是 mock 模式 PoC，模型化信任結構；上線路徑：mock→本地 KERIA→取 LEI→委由 QVI 簽→驗證器 pin GLEIF root。

---

## 分工與兩天工時（4 人）

| 人 | 主責 |
|---|---|
| 彭彥菱（PM/資料科學） | 詐欺偵測 ML（接 provider B 去識別化樣態）+ 簡報主述 |
| 吳語復（後端/Agent） | Act 2 vLEI schema（加診斷證明憑證 ~8 行）+ MCP tool + 串接 Verifier |
| 吳映柔（Builder） | Act 1 APL 情境包調校 + 條款/合成資料 seed + demo 腳本 |
| 沈怡茜（UI/UX） | 授權畫面/攔截彈窗/撤銷鍵/稽核紀錄——**這四個畫面就是 25% 的 Demo 呈現分** |

**Day 1**：Act 1 跑通（APL 情境包 verify/break）+ UI 授權/撤銷畫面骨架 + vLEI mock 鏈跑通。
**Day 2 上午**：Act 2 診斷證明憑證 + 撤銷級聯；串成一條 5 分鐘流程。
**Day 2 下午**：只做整合與 demo 彩排，不加新功能（凍結範圍）。

---

## 相關 repo
- APL Sidecar：https://github.com/OIA-LAB/apl-sidecar （runtime FSL-1.1-ALv2 / verifier Apache-2.0；交件須揭露）
- vLEI Sandbox：https://github.com/smpebble/vlei-sandbox （MIT）
