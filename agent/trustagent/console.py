"""終端輸出 — 這就是錄影素材，所以要好看。

錄影時放大字體、視窗調到 100 字元寬最好看。
"""

import os
import sys

_NO_COLOR = os.environ.get("NO_COLOR") or not sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return text if _NO_COLOR else "\033[{}m{}\033[0m".format(code, text)


def dim(t: str) -> str:
    return _c("2", t)


def bold(t: str) -> str:
    return _c("1", t)


def green(t: str) -> str:
    return _c("32", t)


def red(t: str) -> str:
    return _c("31", t)


def amber(t: str) -> str:
    return _c("33", t)


def cyan(t: str) -> str:
    return _c("36", t)


WIDTH = 78


def dwidth(text: str) -> int:
    """終端顯示寬度。中日韓字元佔兩格，用 len() 會把框線算歪。"""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def dpad(text: str, width: int) -> str:
    """依顯示寬度補空白到指定寬度。"""
    return text + " " * max(0, width - dwidth(text))


def rule(char: str = "─") -> None:
    print(dim(char * WIDTH))


def header(title: str, subtitle: str = "") -> None:
    print()
    print(bold("━" * WIDTH))
    print(bold("  " + title))
    if subtitle:
        print(dim("  " + subtitle))
    print(bold("━" * WIDTH))


def _truncate(text: str, width: int) -> str:
    """超過框寬就截斷，否則右框線會被推歪。"""
    if dwidth(text) <= width:
        return text
    out, used = "", 0
    for ch in text:
        w = 2 if dwidth(ch) == 2 else 1
        if used + w > width - 1:
            return out + "…"
        out += ch
        used += w
    return out


def _boxline(color_fn, text: str, styler=None) -> str:
    inner = dpad(_truncate("  " + text, WIDTH - 2), WIDTH - 2)
    body = styler(inner) if styler else inner
    return color_fn("│") + body + color_fn("│")


def banner(principal: str, grant_line: str) -> None:
    """常駐的「此 Agent 代表誰」——機制 1 要全程看得到。"""
    print()
    print(cyan("┌" + "─" * (WIDTH - 2) + "┐"))
    print(_boxline(cyan, "此 Agent 代表：" + principal, bold))
    print(_boxline(cyan, grant_line, dim))
    print(cyan("└" + "─" * (WIDTH - 2) + "┘"))


def step(n: int, title: str) -> None:
    print()
    print(bold("  [{}] {}".format(n, title)))
    rule()


def allowed(tool: str, reason: str) -> None:
    print("  {}  {}".format(green("✓ 放行"), bold(tool)))
    print("        {}".format(dim(reason)))


def blocked(tool: str, code: str, reason: str) -> None:
    print("  {}  {}".format(red("✕ 攔截"), bold(tool)))
    print("        {} {}".format(amber("[" + code + "]"), reason))


def kv(key: str, value: str, mark: str = "") -> None:
    print("        {:<22} {} {}".format(dim(key), value, mark))


def note(text: str) -> None:
    print("  " + dim(text))


def fixture(text: str) -> None:
    """標注這一格的資料是寫死的固定值，不是真的算出來的。

    錄影時這行會出現在畫面上，所以影片本身就帶著誠實聲明。
    """
    print("        {} {}".format(amber("[假資料]"), dim(text)))


def disclosure(lines) -> None:
    """開場的假資料總聲明。放在最前面，不要藏在最後。"""
    print()
    print(amber("┌" + "─" * (WIDTH - 2) + "┐"))
    print(_boxline(amber, "⚠ 假資料聲明", lambda s: bold(amber(s))))
    print(_boxline(amber, ""))
    for ln in lines:
        print(_boxline(amber, ln))
    print(amber("└" + "─" * (WIDTH - 2) + "┘"))


def verdict(ok: bool, text: str) -> None:
    print()
    if ok:
        print("  " + green(bold("  PASS  ")) + "  " + text)
    else:
        print("  " + red(bold("  FAIL  ")) + "  " + text)
