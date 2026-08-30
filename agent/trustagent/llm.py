"""OpenRouter 客戶端 — 只用 Python 標準函式庫。

刻意不裝 openai 或 requests 套件，維持整個專案「零外部相依」的性質：
明天早上不需要 pip install、不需要處理 venv，clone 下來就能跑。
OpenRouter 是 OpenAI 相容介面，一個 JSON POST 就夠了。

金鑰處理原則：
  * 只從環境變數或 .env 讀取，程式碼裡不出現任何金鑰
  * .env 已被 .gitignore 擋住
  * 金鑰若不存在，不報錯，改用固定值並明確標注——
    Demo Day 現場網路不穩時，這一點讓簡報不會開天窗
"""

import json
import os
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"


def load_dotenv(path=None):
    """讀取 .env。標準庫沒有這個功能，所以自己寫一個最小版本。

    格式：一行一個 KEY=VALUE，# 開頭是註解。
    已存在的環境變數優先，不覆蓋。
    """
    if path is None:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(here, ".env")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and value and not os.environ.get(key):
                os.environ[key] = value
    return True


def api_key():
    load_dotenv()
    return os.environ.get("OPENROUTER_API_KEY") or ""


def is_available():
    return bool(api_key())


def key_fingerprint():
    """給畫面顯示用的遮罩字串。永遠不回傳完整金鑰。"""
    k = api_key()
    if not k:
        return "未設定"
    return "{}…{}（長度 {}）".format(k[:7], k[-4:], len(k))


class LLMError(Exception):
    pass


def chat_json(system, user, model=None, max_tokens=1024, timeout=40):
    """送一次對話，要求回傳 JSON，解析後回傳 dict。

    失敗時拋 LLMError，由呼叫端決定要不要退回固定值。
    """
    key = api_key()
    if not key:
        raise LLMError("找不到 OPENROUTER_API_KEY（請確認 .env 已填寫）")

    body = {
        "model": model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            # OpenRouter 用這兩個標頭做用量歸屬，非必填
            "HTTP-Referer": "https://github.com/desci-brokers",
            "X-Title": "DeSci Brokers Migrant Insurance Infrastructure",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError("HTTP {}：{}".format(exc.code, detail))
    except Exception as exc:
        raise LLMError("呼叫失敗：{}".format(exc))

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LLMError("回應格式非預期：{}".format(json.dumps(payload)[:300]))

    return parse_json_loose(content)


def parse_json_loose(content):
    """解析模型回傳的 JSON。

    即使要求了 response_format=json_object，仍有模型會把 JSON 包在
    markdown 圍籬裡（```json ... ```）。這不是模型的錯，是各家實作差異，
    所以解析端要自己處理，不能假設回來的一定是乾淨的 JSON。
    """
    text = content.strip()

    # 去掉 markdown 圍籬
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]                       # 丟掉 ```json 那行
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 最後一招：抓第一個 { 到最後一個 } 之間的內容
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise LLMError("模型沒有回傳合法 JSON：{}".format(content[:200]))
