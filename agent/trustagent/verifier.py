"""出處驗證層 — 掛 vLEI 的地方。

Agent 本身不做驗證，也不該做。驗證是密碼學的工作，這裡只定義介面，
讓 Agent 能問「這份文件的出處為真嗎」而不需要知道底下是 mock 還是真的 KERI。

MockVerifier   跑得動、不用裝東西，用來先把 Agent 骨架串起來。
VleiVerifier   實際呼叫 vlei-sandbox 的 `verify --said`，Day 2 換上去。
"""

import subprocess
from dataclasses import dataclass


@dataclass
class VerificationResult:
    ok: bool
    said: str
    issuer: str = ""
    detail: str = ""
    revoked: bool = False
    unavailable: bool = False


class Verifier:
    """介面。實作只要回傳 VerificationResult。"""

    name = "base"

    def verify(self, said: str) -> VerificationResult:  # pragma: no cover - 介面
        raise NotImplementedError


class UnavailableVerifier(Verifier):
    """Fail-closed verifier：環境要求可信驗證，但驗證服務目前不可用。"""

    name = "unavailable"

    def __init__(self, detail: str) -> None:
        self.detail = detail

    def verify(self, said: str) -> VerificationResult:
        return VerificationResult(
            False, said, "", self.detail, unavailable=True
        )


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
        except Exception as exc:  # 嚴格模式由 Agent 將 unavailable 視為 fail closed
            return VerificationResult(
                False, said, "", "無法呼叫 vlei-sandbox：{}".format(exc), unavailable=True
            )

        out = (proc.stdout or "") + (proc.stderr or "")

        # 判定依 RESULT 行與退出碼，不要用關鍵字比對整段輸出：
        # 輸出裡的「LEI ...: valid (ISO 17442-1)」只代表 LEI 檢查碼合格，
        # 不代表整條鏈驗證通過。拿 "VALID" 去 match 會把撤銷過的憑證判成有效。
        ok = proc.returncode == 0 and "RESULT: chain verified" in out

        # 撤銷要看標記 FAIL 的那一行，不是任何提到 revoke 的行
        # （通過的憑證每一節都會印「issued, not revoked」）
        revoked = any(
            "[FAIL]" in line and "revoked" in line
            for line in out.splitlines()
        )

        if revoked:
            detail = "憑證已被撤銷，整條鏈失效"
        elif ok:
            detail = "信任鏈驗證通過，根為 GLEIF"
        else:
            fails = [ln.strip() for ln in out.splitlines() if "[FAIL]" in ln]
            detail = fails[0] if fails else "驗證失敗（exit={}）".format(proc.returncode)

        return VerificationResult(ok, said, "", detail, revoked=revoked)
