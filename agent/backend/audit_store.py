"""SQLite 版的稽核鏈 — 與 trustagent.AuditLog 介面相容。

重點:**重用** trustagent.audit.Entry 的 body() / compute_hash(),雜湊演算法一個字都沒改。
差別只在紀錄存哪裡:

    trustagent.audit.AuditLog   →  記憶體 list,程序結束就沒
    SqliteAuditLog              →  audit_entries 表,跨 session 共享同一條鏈

TrustAgent.__init__ 接受注入的 audit,所以把這個物件塞進去,整個引擎照跑:
    TrustAgent(principal=..., grant=..., verifier=..., audit=SqliteAuditLog(conn, case_id))
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone

from trustagent.audit import GENESIS, Entry

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_KEY_PATH = os.path.join(HERE, ".secrets", "audit_ed25519.key")


def load_audit_key(path: str = AUDIT_KEY_PATH):
    """有 cryptography 就載入/建立一把固定的 Ed25519 私鑰;沒有就回 None。

    與 trustagent.audit 的差別:那邊每次程序啟動 generate() 一把新的,
    重啟後舊簽章就對不起來。這邊存檔,重啟沿用同一把。
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception:
        return None

    if os.path.exists(path):
        os.chmod(os.path.dirname(path), 0o700)
        os.chmod(path, 0o600)
        with open(path, encoding="utf-8") as fh:
            return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(fh.read().strip()))

    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    os.chmod(os.path.dirname(path), 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(raw.hex())
    return key


class SqliteAuditLog:
    """唯附加稽核鏈,存在 SQLite。介面對齊 trustagent.audit.AuditLog。"""

    def __init__(self, conn, case_id: str, key=None) -> None:
        self.conn = conn
        self.case_id = case_id
        self._key = key

    @property
    def signed(self) -> bool:
        return self._key is not None

    # ---- 讀 --------------------------------------------------------------
    def _rows(self):
        return self.conn.execute(
            "SELECT * FROM audit_entries WHERE case_id=? ORDER BY seq", (self.case_id,)
        ).fetchall()

    @staticmethod
    def _row_to_entry(row) -> Entry:
        return Entry(
            seq=row["seq"],
            ts=row["ts"],
            principal=row["principal"],
            tool=row["tool"],
            code=row["code"],
            allowed=bool(row["allowed"]),
            detail=json.loads(row["detail"]),
            prev=row["prev"],
            hash=row["hash"],
            sig=row["sig"],
        )

    @property
    def entries(self):
        return [self._row_to_entry(r) for r in self._rows()]

    # ---- 寫(唯附加)---------------------------------------------------
    def append(self, principal, tool, code, allowed, detail=None) -> Entry:
        rows = self._rows()
        prev = rows[-1]["hash"] if rows else GENESIS
        entry = Entry(
            seq=len(rows) + 1,
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            principal=principal,
            tool=tool,
            code=code,
            allowed=bool(allowed),
            detail=detail or {},
            prev=prev,
        )
        entry.hash = entry.compute_hash()          # ← trustagent 的原演算法
        if self._key is not None:
            entry.sig = self._key.sign(bytes.fromhex(entry.hash)).hex()

        self.conn.execute(
            "INSERT INTO audit_entries"
            "(case_id,seq,ts,principal,tool,code,allowed,detail,prev,hash,sig) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.case_id, entry.seq, entry.ts, entry.principal, entry.tool,
                entry.code, int(entry.allowed),
                json.dumps(entry.detail, ensure_ascii=False, sort_keys=True),
                entry.prev, entry.hash, entry.sig,
            ),
        )
        self.conn.commit()
        return entry

    # ---- 驗證(重走整條鏈)-------------------------------------------
    def verify(self):
        prev = GENESIS
        entries = self.entries
        unsigned = 0
        for e in entries:
            if e.prev != prev:
                return False, e.seq, "第 {} 筆的 prev 與前一筆的雜湊對不上".format(e.seq)
            if e.compute_hash() != e.hash:
                return False, e.seq, "第 {} 筆內容被改過(雜湊重算不符)".format(e.seq)
            if e.sig:
                if self._key is None:
                    return False, e.seq, "第 {} 筆有簽章，但目前無法載入驗證金鑰".format(e.seq)
                try:
                    self._key.public_key().verify(
                        bytes.fromhex(e.sig), bytes.fromhex(e.hash)
                    )
                except Exception:
                    return False, e.seq, "第 {} 筆 Ed25519 簽章驗證失敗".format(e.seq)
            else:
                unsigned += 1
            prev = e.hash
        if unsigned:
            return True, None, "全部 {} 筆雜湊完好（{} 筆為既有未簽章紀錄）".format(
                len(entries), unsigned
            )
        return True, None, "全部 {} 筆雜湊與 Ed25519 簽章完好".format(len(entries))

    # ---- demo 用:故意竄改一筆(只改內容、不重算雜湊)------------------
    def tamper(self, seq: int, field_name: str = "code", new_value="OK") -> bool:
        if field_name not in ("code", "allowed", "tool", "principal"):
            return False
        value = int(bool(new_value)) if field_name == "allowed" else new_value
        cur = self.conn.execute(
            "UPDATE audit_entries SET {}=? WHERE case_id=? AND seq=?".format(field_name),
            (value, self.case_id, seq),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def to_dicts(self):
        return [asdict(e) for e in self.entries]
