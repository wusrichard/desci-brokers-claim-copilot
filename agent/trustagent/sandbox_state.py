"""從 vlei-sandbox 的狀態檔讀出當前憑證 SAID——不要寫死在程式碼裡。

為什麼需要這支：

SAID 是內容雜湊，而內容包含發行者的 AID，AID 又來自建鏈當下新生成的金鑰。
所以**每個人重建憑證鏈，都會得到一組不同的 SAID**，這是設計使然，不是誰做錯。

而 `.vlei/state.json` 含 `seed` / `next_seed`（私鑰種子），**永遠不能 commit**——
一個以「可信任」為題的作品，repo 裡放私鑰會直接自打嘴巴。

兩件事合起來的結果是：SAID 沒辦法共用，寫死在程式碼裡就會人人衝突。
所以改成執行期從狀態檔讀，程式碼裡不出現任何 SAID。

找不到 sandbox 時回傳空值，情境層會退回 mock 並在畫面標明——不會壞掉。
"""

import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SANDBOX = os.path.normpath(os.path.join(HERE, "..", "vlei-sandbox"))


def _state_path(sandbox_dir=None):
    return os.path.join(sandbox_dir or DEFAULT_SANDBOX, ".vlei", "state.json")


def available(sandbox_dir=None):
    return os.path.exists(_state_path(sandbox_dir))


def _load(sandbox_dir=None):
    path = _state_path(sandbox_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _revoked_saids(state):
    """掃所有 registry 的 TEL，收集有 rev 事件的憑證。

    撤銷在 KERI 裡就是 TEL 上的一個事件，跟發行同屬一份唯附加歷史，
    沒有 CRL 也沒有 OCSP。
    """
    revoked = set()
    for actor in (state.get("actors") or {}).values():
        for reg in (actor.get("registries") or {}).values():
            for said, events in (reg.get("tel") or {}).items():
                if any(e.get("t") == "rev" for e in events):
                    revoked.add(said)
    return revoked


def credentials(sandbox_dir=None):
    """回傳當前所有憑證的摘要。

    每筆：said / type / person / role / lei / revoked
    """
    state = _load(sandbox_dir)
    if not state:
        return []
    revoked = _revoked_saids(state)
    out = []
    for said, cred in (state.get("credentials") or {}).items():
        attrs = (cred.get("acdc") or {}).get("a") or {}
        out.append({
            "said": said,
            "type": cred.get("type", ""),
            "person": attrs.get("personLegalName", ""),
            "role": attrs.get("engagementContextRole") or attrs.get("officialRole", ""),
            "lei": attrs.get("LEI", ""),
            "revoked": said in revoked,
        })
    return out


def find_ecr(person=None, revoked=None, sandbox_dir=None):
    """依姓名或撤銷狀態找一張 ECR 憑證的 SAID。找不到回傳 None。"""
    for c in credentials(sandbox_dir):
        if c["type"] != "ecr":
            continue
        if person is not None and c["person"] != person:
            continue
        if revoked is not None and c["revoked"] != revoked:
            continue
        return c["said"]
    return None


def find_by_type(cred_type, sandbox_dir=None):
    for c in credentials(sandbox_dir):
        if c["type"] == cred_type:
            return c["said"]
    return None
