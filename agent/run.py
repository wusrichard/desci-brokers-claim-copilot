#!/usr/bin/env python3
"""Demo 驅動程式 — 這支的輸出就是錄影素材。

    python3 run.py demo        # 完整六機制走一遍（錄這個）
    python3 run.py verify      # 只驗稽核紀錄
    python3 run.py tamper      # 竄改一筆 → 驗證失敗
    python3 run.py audit       # 印出完整稽核紀錄 JSON

零外部相依，Python 3.8+ 可跑。
"""

import argparse
import importlib
import os
import json
import sys

from scenarios import health_pass as scenario
from trustagent import TrustAgent
from trustagent import console as c


def load_scenario(name: str):
    """換情境的唯一入口。引擎不因此改動任何一行。"""
    global scenario
    scenario = importlib.import_module("scenarios.{}".format(name))
    return scenario


def build_agent(days_valid=None) -> TrustAgent:
    principal = scenario.build_principal()
    # days_valid 留 None 時採用情境自己的預設效期，不要從外面蓋掉
    grant = (
        scenario.build_grant(principal)
        if days_valid is None
        else scenario.build_grant(principal, days_valid=days_valid)
    )
    agent = TrustAgent(
        principal=principal,
        grant=grant,
        verifier=scenario.build_verifier(),
    )
    agent.register_all(scenario.build_tools())
    return agent


def show_banner(agent: TrustAgent) -> None:
    g = agent.grant
    c.banner(
        "{}／案號 {}".format(agent.principal.display_name, scenario.CASE_ID),
        "授權：{}｜範圍 {}｜效期至 {}".format(
            g.purpose, "/".join(sorted(g.scopes)), g.expires_at.date()
        ),
    )


def cmd_demo(args) -> int:
    agent = build_agent()

    c.header(
        "移工職安 Health Pass — 可信 Agent Demo",
        "DeSci Brokers｜全部為合成資料",
    )
    show_banner(agent)

    # --- 機制 3：先攤開這個 Agent 能做什麼、不能做什麼 ---
    c.step(1, "機制 3 — 可執行動作範圍")
    for tool in agent.capabilities():
        covered = agent.grant.covers(tool.required_scope)
        mark = c.green("授權內") if covered else c.red("授權外")
        risk = c.amber("高風險") if tool.is_high_risk() else c.dim("低風險")
        c.kv(tool.name, "{} {}".format(mark, risk), c.dim(tool.description))

    # --- 出處驗證：Agent 不自己證明，交給驗證器 ---
    c.step(2, "出處驗證 — 這張綠燈是誰簽的")
    res = agent.verify_provenance(scenario.CREDENTIAL_SAID)
    c.kv("憑證 SAID", scenario.CREDENTIAL_SAID)
    c.kv("發證者", res.issuer or "-")
    c.verdict(res.ok, res.detail)

    # --- 機制 2：授權內的讀取 ---
    c.step(3, "機制 2 — 授權範圍內：稽核員讀綠燈")
    r = agent.act("read_green_light")
    c.allowed(r.tool, r.decision.reason)
    for k, v in r.value.items():
        c.kv(k, str(v))
    c.note("↑ 以上是稽核員拿到的全部內容——沒有任何一個檢查值")

    # --- 母語解釋 ---
    c.step(4, "AI 的工作 — 用移工母語解釋")
    r = agent.act("explain_to_worker", lang="vi")
    c.allowed(r.tool, r.decision.reason)
    c.note(r.value["message"])

    # --- 機制 4：兩種攔截，理由不同 ---
    c.step(5, "機制 4 — 攔截 A：授權範圍外（稽核員要求調閱原始報告）")
    r = agent.act("read_raw_report")
    c.blocked(r.tool, r.decision.code, r.decision.reason)
    c.note("scope 是 raw_medical，根本不在移工勾選的範圍內——連談風險都不必")

    c.step(6, "機制 4 — 攔截 B：授權內、但不可逆（揭露給新稽核方）")
    r = agent.act("share_with_new_auditor", auditor="SGS-TW-0417")
    c.blocked(r.tool, r.decision.code, r.decision.reason)
    c.note("這次 scope 通過了，但動作不可逆——揭露出去收不回來，所以仍然停下來等人")
    print()
    c.note("→ 移工在手機上按下確認後，同一個呼叫帶 confirmed=True 重送：")
    r = agent.act("share_with_new_auditor", auditor="SGS-TW-0417", confirmed=True)
    c.allowed(r.tool, r.decision.reason)
    for k, v in r.value.items():
        c.kv(k, str(v))
    c.note("被擋下的嘗試與後來的放行，兩筆都在稽核紀錄裡——這才是可追溯")

    # --- 機制 5：稽核鏈驗證 ---
    c.step(7, "機制 5 — 稽核追溯")
    ok, bad, msg = agent.audit.verify()
    for e in agent.audit.entries:
        icon = c.green("✓") if e.allowed else c.red("✕")
        print("        {} #{:<2} {:<24} {}".format(icon, e.seq, e.tool, c.dim(e.code)))
    c.kv("簽章", "Ed25519" if agent.audit.signed else "雜湊鏈（stdlib，零相依）")
    c.verdict(ok, msg)

    # --- 竄改示範：挑一筆「被擋下來」的，改成放行 ---
    c.step(8, "竄改偵測 — 把一筆攔截紀錄竄改成放行")
    victim = next((e.seq for e in agent.audit.entries if not e.allowed), 1)
    agent.audit.tamper(seq=victim, field_name="code", new_value="OK")
    agent.audit.tamper(seq=victim, field_name="allowed", new_value=True)
    c.note("已把第 {} 筆（原本被攔截）改成 OK／allowed=True，只改內容、不重算雜湊".format(victim))
    ok, bad, msg = agent.audit.verify()
    c.verdict(ok, msg)
    c.note("想蓋掉『我被擋過』這件事，就得重算它之後每一筆的雜湊——鏈式結構讓竄改藏不住")

    # --- 機制 6：撤銷 ---
    c.step(9, "機制 6 — 移工撤銷授權")
    agent2 = build_agent()
    agent2.revoke_grant()
    r = agent2.act("read_green_light")
    c.blocked(r.tool, r.decision.code, r.decision.reason)
    c.note("同一個工具，撤銷前放行、撤銷後立即失效——綠燈轉紅")

    print()
    c.rule("━")
    print("  " + c.bold("六項機制全部演示完畢"))
    c.rule("━")
    print()
    return 0


def cmd_verify(args) -> int:
    agent = build_agent()
    agent.act("read_green_light")
    agent.act("read_raw_report")
    ok, bad, msg = agent.audit.verify()
    c.verdict(ok, msg)
    return 0 if ok else 1


def cmd_tamper(args) -> int:
    agent = build_agent()
    agent.act("read_green_light")
    agent.act("read_raw_report")
    ok, _, msg = agent.audit.verify()
    c.verdict(ok, "竄改前：" + msg)
    agent.audit.tamper(seq=args.seq, field_name="code", new_value="OK")
    ok, bad, msg = agent.audit.verify()
    c.verdict(ok, "竄改後：" + msg)
    return 0 if not ok else 1  # 竄改後「應該」失敗


def cmd_audit(args) -> int:
    agent = build_agent()
    agent.act("read_green_light")
    agent.act("read_raw_report")
    print(agent.audit.to_json())
    return 0


def cmd_kb(args) -> int:
    """知識庫狀態：填了幾筆、版本、雜湊。交件前確認引用出處是真的。"""
    from trustagent import knowledge
    c.header("知識庫狀態", "本地、版本化、可重算雜湊")
    ready = False
    for s in knowledge.status():
        c.kv(s["name"], "已填 {} 筆｜版本 {}".format(s["filled"], s["version"]))
        c.kv("  sha256", s["sha256"])
        ready = ready or s["ready"]
    print()
    if ready:
        c.verdict(True, "知識庫可引用，match_coverage 會輸出真實出處")
    else:
        c.verdict(False, "知識庫尚未填入條文——citations 會是空的")
        c.note("填 knowledge/laws.json，複製 TEMPLATE 那筆再改")
        c.note("text 要逐字貼原文；填不確定的寧可留空，空著比錯著好")
    print()
    return 0


def cmd_llm(args) -> int:
    """檢查金鑰有沒有生效，並實際跑一次越南文抽取。

    交件前跑這個確認，不要等到錄影當下才發現金鑰沒讀到。
    """
    from trustagent import llm
    s = load_scenario("migrant_claim")

    c.header("模型連線自我檢查", "確認金鑰、連線與抽取結果")
    c.kv("金鑰", llm.key_fingerprint())
    c.kv("模型", os.environ.get("OPENROUTER_MODEL") or llm.DEFAULT_MODEL)

    if not llm.is_available():
        c.verdict(False, "找不到 OPENROUTER_API_KEY")
        print()
        c.note("解法：cp .env.example .env，把金鑰填進 OPENROUTER_API_KEY=")
        c.note(".env 已被 .gitignore 擋住，不會進 repo")
        return 1

    tests = [
        ("越南文・資訊完整", "vi", s.DEFAULT_STATEMENT),
        ("越南文・資訊不全", "vi", "Tay tôi bị đau."),  # 只說「手痛」，必填欄位會缺
    ]
    for title, lang, text in tests:
        c.step(tests.index((title, lang, text)) + 1, title)
        c.kv("輸入", text)
        r = s.understand_incident(lang=lang, raw=text)
        c.kv("來源", r["source"])
        for k, v in r["structured"].items():
            c.kv("  " + k, str(v) if v is not None else c.dim("null"))
        c.kv("摘要", r.get("summary_zh", ""))
        flag = c.amber("需要人工複核") if r["needs_human_review"] else c.green("可自動進行")
        c.kv("轉人工判斷", flag)
        c.kv("理由", r["review_reason"])

    print()
    c.note("第二個測試刻意只講「手痛」——必填欄位抽不到，應該要轉人工。")
    c.note("這是用欄位完整性判斷，不是信心分數門檻。")
    print()
    return 0


def cmd_claim(args) -> int:
    """理賠主線：六步流程 + 仲介承辦人授權（Corppass 模式）。"""
    s = load_scenario("migrant_claim")
    agent = build_agent()

    c.header("Migrant Insurance Infrastructure｜移工職災理賠", "DeSci Brokers｜合成資料原型")
    # 聲明內容依實際狀態產生，不寫死——標注錯了跟沒標一樣糟
    from trustagent import llm
    if llm.is_available():
        llm_line = "  1. 母語理解：真的呼叫模型（{}）".format(
            os.environ.get("OPENROUTER_MODEL") or llm.DEFAULT_MODEL)
    else:
        llm_line = "  1. 母語理解：未設定金鑰，本次使用固定值"
    if agent.verifier is not None and agent.verifier.name == "vlei-sandbox":
        verifier_line = "  2. vLEI：沙盒內實際重算 SAID、驗簽章並查 TEL 撤銷狀態"
        said_line = "  4. 案號、公司與人名為合成資料；仲介 LE／ECR SAID 由本地 sandbox 產生"
    else:
        verifier_line = "  2. vLEI：未找到 sandbox 狀態，本次使用 MockVerifier 查表"
        said_line = "  4. 案號、公司、人名與 SAID 為合成／模擬資料（LEI 檢查碼格式有效）"
    c.disclosure([
        "本原型除母語理解外，其餘回傳值皆為寫死的固定值：",
        "",
        llm_line,
        verifier_line,
        "  3. 沒有比對真實保單或法規條文",
        said_line,
        "",
        "每一步畫面上都會標出該格的實際來源。",
    ])
    show_banner(agent)

    notes = scenario.FIXTURE_NOTES
    steps = [
        ("1 Verify — 身份與聘僱關係", "verify_employment", {}),
        ("2 Understand — 母語事故描述結構化", "understand_incident", {"lang": "vi"}),
        ("3 Match — 我到底保了什麼、能申請什麼", "match_coverage", {}),
        ("4 Claim — 缺件清單", "list_missing_documents", {}),
        ("5 Track — 案件進度（移工看得到）", "track_status", {}),
        ("6 Record — 產出 worker protection record", "build_protection_record", {}),
    ]
    for i, (title, tool, kw) in enumerate(steps, start=1):
        c.step(i, title)
        r = agent.act(tool, **kw)
        c.allowed(r.tool, r.decision.reason)
        _print_value(r.value)
        if tool in notes:
            c.fixture(notes[tool])

    # --- 不可逆動作 ---
    c.step(7, "不可逆動作 — 正式送件")
    r = agent.act("submit_claim")
    c.blocked(r.tool, r.decision.code, r.decision.reason)
    c.note("Agent 可以準備到最後一步，但送出去要移工本人按下確認")
    r = agent.act("submit_claim", confirmed=True)
    c.allowed(r.tool, r.decision.reason)
    _print_value(r.value)
    c.fixture(notes["submit_claim"])

    # --- Corppass：組織對個人授權 ---
    c.header("仲介承辦人授權", "對應新加坡 Corppass：驗的不只是公司是真的，是這個人被公司授權")
    _v = s.build_verifier()
    if _v.name == "vlei-sandbox":
        c.note(c.green("✓ 真實驗證") + "：以 vlei-sandbox 執行，重算 SAID、驗簽章、查 TEL 撤銷狀態、遞迴至信任根")
    else:
        c.fixture("找不到 vlei-sandbox，退回查表模式，非真實 TEL 撤銷紀錄")

    for revoked, label in ((False, "在職承辦人 陳美玲"), (True, "已離職承辦人 林志豪")):
        officer = s.build_agency_officer(revoked=revoked)
        grant = s.build_agency_grant(officer)
        oa = TrustAgent(principal=officer, grant=grant, verifier=s.build_verifier())
        oa.register_all(s.build_tools())

        c.step(8 if not revoked else 9, label)
        c.kv("代表組織", "{}（LEI {}）".format(officer.acting_for, officer.org_lei))
        c.kv("角色憑證", officer.role_credential)
        r = oa.act("list_missing_documents")
        if r.blocked:
            c.blocked(r.tool, r.decision.code, r.decision.reason)
        else:
            c.allowed(r.tool, r.decision.reason)
        r2 = oa.act("build_protection_record")
        if r2.blocked:
            c.blocked(r2.tool, r2.decision.code, r2.decision.reason)

    print()
    c.note("同一家仲介、同一個請求——差別只在那個人的角色憑證還有沒有效。")
    c.note("公司是真的，不代表這個人有權處理你的案件。")
    print()
    return 0


def _print_value(value) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                c.kv(k, json.dumps(v, ensure_ascii=False)[:96])
            else:
                c.kv(k, str(v))


def cmd_tour(args) -> int:
    """證明引擎與情境分離：同一組引擎程式碼跑兩個完全不同的情境。"""
    for name in ("migrant_claim", "health_pass", "medical_claim"):
        s = load_scenario(name)
        agent = build_agent()
        c.header("情境：{}".format(s.SCENARIO["name"]), "引擎程式碼完全相同，只換了 scenarios/ 底下一個模組")
        c.kv("Agent 代表", agent.principal.display_name)
        c.kv("授權範圍", "/".join(sorted(agent.grant.scopes)))
        print()
        for tool in agent.capabilities():
            covered = agent.grant.covers(tool.required_scope)
            mark = c.green("授權內") if covered else c.red("授權外")
            risk = c.amber("高風險") if tool.is_high_risk() else c.dim("低風險")
            c.kv(tool.name, "{} {}".format(mark, risk), c.dim(tool.description))
        print()
        for tool in agent.capabilities():
            if not agent.grant.covers(tool.required_scope):
                r = agent.act(tool.name)
                c.blocked(r.tool, r.decision.code, r.decision.reason)
    print()
    c.note("同一個 TrustAgent、同一個 PolicyGate、同一份 AuditLog——換情境只換一個檔案。")
    print()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="可信 Agent 骨架 demo")
    p.add_argument("--scenario", default="health_pass", help="health_pass | medical_claim")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("claim", help="理賠主線：六步流程 + 仲介授權（錄影用）")
    sub.add_parser("llm", help="檢查 API 金鑰與模型抽取是否正常")
    sub.add_parser("kb", help="檢查知識庫狀態與雜湊")
    sub.add_parser("demo", help="六項信任機制演示")
    sub.add_parser("tour", help="同一引擎跑多個情境，證明可換皮")
    sub.add_parser("verify", help="驗證稽核紀錄")
    t = sub.add_parser("tamper", help="竄改一筆後重驗")
    t.add_argument("--seq", type=int, default=2)
    sub.add_parser("audit", help="印出稽核紀錄 JSON")

    args = p.parse_args()
    if getattr(args, "scenario", "health_pass") != "health_pass" and args.cmd != "tour":
        load_scenario(args.scenario)
    cmds = {"claim": cmd_claim, "llm": cmd_llm, "kb": cmd_kb, "demo": cmd_demo, "tour": cmd_tour,
            "verify": cmd_verify, "tamper": cmd_tamper, "audit": cmd_audit}
    if args.cmd not in cmds:
        p.print_help()
        return 1
    return cmds[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
