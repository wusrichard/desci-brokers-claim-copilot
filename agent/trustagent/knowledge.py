"""知識庫載入器——本地、版本化、可驗證。

設計原則（三條，都跟這個作品的主題直接相關）：

  1. **不在推論路徑上抓線上資料。**
     線上同步屬於維運排程，不屬於使用者請求。
     同一個問題不同時間得到不同答案，就沒辦法重現、也沒辦法驗證。

  2. **每次載入都算雜湊。**
     引用出處帶上 kb 版本與 sha256，任何人都能重算確認引用的是哪一份。
     憑證那層我們證明「文件出處為真」，這層證明「建議出處為真」。

  3. **沒填完的條目不會被引用。**
     範本條目（text 還是佔位字串）一律跳過。
     寧可回答「查無可引用條文」，也不要引用半成品——
     那正是我先前編造法條條號犯的錯。

不用向量檢索：幾十條條文全部塞進 prompt 都還有空間，
向量是為了「文件多到塞不下」發明的，這裡用它是過度設計。
"""

import hashlib
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(HERE, "knowledge")

# 範本條目的標記。text 含這些字樣就視為未填。
_PLACEHOLDER_MARKS = ("（", "TEMPLATE")


def _is_filled(entry):
    """判斷這筆是不是真的填好了。"""
    text = (entry.get("text") or "").strip()
    if not text:
        return False
    if str(entry.get("id", "")).startswith("TEMPLATE"):
        return False
    # 原文若整段還是佔位括號，視為未填
    return not text.startswith(_PLACEHOLDER_MARKS)


class KnowledgeBase:
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.meta = {}
        self.entries = []
        self.sha256 = ""
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "rb") as fh:
            raw = fh.read()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return
        self.meta = data.get("meta", {})
        self.entries = [e for e in data.get("entries", []) if _is_filled(e)]

    @property
    def ready(self):
        return len(self.entries) > 0

    @property
    def version(self):
        return self.meta.get("kb_version") or "尚未建立"

    def find(self, keywords):
        """關鍵字比對——不用向量，這個規模不需要。

        條目的 applies_when 任一項命中就算相關。
        """
        hits = []
        for entry in self.entries:
            tags = entry.get("applies_when") or []
            if any(k in t or t in k for k in keywords for t in tags):
                hits.append(entry)
        return hits

    def cite(self, entry):
        """產生可回溯的引用——帶知識庫版本與雜湊。"""
        return {
            "source": "{} {}".format(entry.get("law") or entry.get("policy_type", ""),
                                     entry.get("article") or entry.get("clause", "")).strip(),
            "effective": entry.get("effective", ""),
            "kb_version": self.version,
            "kb_sha256": self.sha256[:16] + "…",
        }


def load_all():
    return {
        "laws": KnowledgeBase("法規", os.path.join(KB_DIR, "laws.json")),
        "policies": KnowledgeBase("保單條款", os.path.join(KB_DIR, "policies.json")),
    }


def load_enrollments():
    """讀移工的實際投保紀錄。

    這份跟 laws/policies 不同——那兩份是「條文」，這份是「她保了什麼」。
    有了它，match_coverage 才是真的在比對，而不是回傳固定清單。

    真實版本要串勞保局、健保署與雇主端保單系統，且都需要她本人的授權，
    那正是 Grant 模型存在的理由。本 demo 全為合成資料。
    """
    path = os.path.join(KB_DIR, "enrollments.json")
    if not os.path.exists(path):
        return {"enrollments": [], "sha256": "", "version": "尚未建立"}
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {"enrollments": [], "sha256": "", "version": "解析失敗"}
    return {
        "enrollments": data.get("enrollments", []),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "version": (data.get("meta") or {}).get("kb_version", ""),
    }


def load_claim_documents():
    """讀職災保險請領所需文件清單（真實參考資料，取自勞保局公告）。

    跟 enrollments 一樣是「規範」而非「狀態」：這份說的是規定要哪些文件，
    這個案子實際備齊了哪些則由情境層提供。
    """
    path = os.path.join(KB_DIR, "claim_documents.json")
    if not os.path.exists(path):
        return {"documents": [], "sha256": "", "version": "尚未建立"}
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {"documents": [], "sha256": "", "version": "解析失敗"}
    return {
        "documents": data.get("documents", []),
        "benefit": data.get("benefit", ""),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "version": (data.get("meta") or {}).get("kb_version", ""),
    }


def status():
    """給 `run.py kb` 用的摘要。"""
    out = []
    for key, kb in load_all().items():
        out.append({
            "name": kb.name,
            "ready": kb.ready,
            "filled": len(kb.entries),
            "version": kb.version,
            "sha256": kb.sha256[:16] + "…" if kb.sha256 else "（檔案不存在）",
        })
    return out
