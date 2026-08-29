"""出處驗證層 — 掛 vLEI 的地方。

Agent 本身不做驗證，也不該做。驗證是密碼學的工作，這裡只定義介面，
讓 Agent 能問「這份文件的出處為真嗎」而不需要知道底下是 mock 還是真的 KERI。

MockVerifier   跑得動、不用裝東西，用來先把 Agent 骨架串起來。
VleiVerifier   實際呼叫 vlei-sandbox 的 `verify --said`，Day 2 換上去。
"""

import json
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class VerificationResult:
    ok: bool
    said: str
    issuer: str = ""
    detail: str = ""
    revoked: bool = False


class Verifier:
    """介面。實作只要回傳 VerificationResult。"""

    name = "base"

    def verify(self, said: str) -> VerificationResult:  # pragma: no cover - 介面
        raise NotImplementedError


class MockVerifier(Verifier):
    """把已知 SAID 當成有效。可用 revoke() 模擬撤銷級聯。"""

    name = "mock"

    def __init__(self) -> None:
        self._known = {}
        self._revoked = set()

    def register(self, said: str, issuer: str) -> None:
        self._known[said] = issuer

    def revoke(self, said: str) -> None:
        self._revoked.add(said)

    def verify(self, said: str) -> VerificationResult:
        if said in self._revoked:
            return VerificationResult(
                False, said, self._known.get(said, ""), "憑證已被撤銷，整條鏈失效", revoked=True
            )
        if said not in self._known:
            return VerificationResult(False, said, "", "找不到這張憑證")
        return VerificationResult(True, said, self._known[said], "信任鏈驗證通過，根為 GLEIF")


class VleiVerifier(Verifier):
    """呼叫 vlei-sandbox。sandbox_dir 指向 clone 下來的 repo。"""

    name = "vlei-sandbox"

    def __init__(self, sandbox_dir: str, python: str = "python3") -> None:
        self.sandbox_dir = sandbox_dir
        self.python = python

    def verify(self, said: str) -> VerificationResult:
        cmd = [self.python, "scripts/vlei_sandbox.py", "verify", "--said", said]
        try:
            proc = subprocess.run(
                cmd, cwd=self.sandbox_dir, capture_output=True, text=True, timeout=30
            )
        except Exception as exc:  # sandbox 沒裝好時不要讓整個 demo 掛掉
            return VerificationResult(False, said, "", "無法呼叫 vlei-sandbox: {}".format(exc))

        out = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0 and "VALID" in out.upper()
        revoked = "REVOK" in out.upper()
        return VerificationResult(ok, said, "", out.strip()[:200], revoked=revoked)
