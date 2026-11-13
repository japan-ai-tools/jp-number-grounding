"""MCP server (stdio, JSON-RPC 2.0). Python standard library only, no network.

Start: python -m jpnumground.server
"""
import json
import sys

from . import __version__
from .ground import check, extract

PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]
RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
MAX_CHARS = 200_000

TOOLS = [
    {
        "name": "jp_number_grounding_check",
        "title": "Check that numbers, amounts, dates and times in a Japanese summary appear in its source",
        "annotations": RO,
        "description": ("Before you send a summary, meeting minutes (議事録), report or answer written from a Japanese "
                        "source, pass both texts here. Every number, money amount, percentage, count, date and time in "
                        "the summary is normalized (三千五百万円 = 3,500万円 = 35,000,000円, 令和7年 = 2025年, "
                        "R7.4.1 = 2025/4/1, 午後2時 = 14:00, 1割5分 = 15%, 12名 = 12人) and looked up in the source. "
                        "Returns ok, problems, counts and per-fact status: supported, approx_supported (marked 約/程度 "
                        "and within tolerance), year_unverified, unit_unverified, unit_mismatch (30人 vs 30件), "
                        "unsupported (not in the source: often an invented deadline or a wrong figure). Also flags a "
                        "weekday that does not match its date (W_WEEKDAY_MISMATCH). Deterministic, offline. It checks "
                        "presence of values, not meaning. 要約の数字・日付・金額が原文にあるかを確かめる。"),
        "inputSchema": {"type": "object", "properties": {
            "source": {"type": "string", "description": "Original text: transcript, document, email"},
            "summary": {"type": "string", "description": "Text written from the source (by an AI or a person)"},
            "tolerance": {"type": "number", "description": "Relative tolerance for values marked approximate (約). Default 0.1"}},
            "required": ["source", "summary"]},
    },
    {
        "name": "jp_number_extract",
        "title": "Extract and normalize numbers, amounts, dates and times from Japanese text",
        "annotations": RO,
        "description": ("List every quantity in a Japanese text with its normalized value: kanji numerals, 万/億 units, "
                        "full-width digits, Japanese era years (令和/平成/昭和, R7), dates, 午前/午後 times, 割/分 rates, "
                        "counters (人, 名, 件, 社, 回, か月 ...). Skips words that only look like numbers (一宮, 統一, "
                        "一部, 万一). Returns facts with kind, text, normalized, value, unit, approx, issues."),
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    },
]


def _str(args, key):
    v = args.get(key)
    if not isinstance(v, str):
        raise ValueError(f"'{key}' must be a string")
    if len(v) > MAX_CHARS:
        raise ValueError(f"'{key}' is longer than {MAX_CHARS} characters; split it")
    return v


def _tol(args):
    v = args.get("tolerance", 0.1)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
        raise ValueError("'tolerance' must be a number between 0 and 1")
    return float(v)


HANDLERS = {
    "jp_number_grounding_check": lambda a: check(_str(a, "source"), _str(a, "summary"), _tol(a)),
    "jp_number_extract": lambda a: {"facts": extract(_str(a, "text"))},
}


def _handle_legacy(msg):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None
    try:
        if method == "initialize":
            want = params.get("protocolVersion")
            result = {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "jp-number-grounding", "version": __version__},
                      "instructions": ("After writing a summary or minutes from Japanese text, call "
                                       "jp_number_grounding_check with the source and your summary. Fix or remove every "
                                       "fact it reports as unsupported or unit_mismatch before sending.")}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            if name not in HANDLERS:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
            try:
                out = HANDLERS[name](params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                          "structuredContent": out, "isError": False}
            except ValueError as e:
                result = {"content": [{"type": "text", "text": str(e)}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as e:  # keep the server alive
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"Internal error: {e}"}}


# --- MCP 2026-07-28 (stateless) support. The legacy initialize flow above stays as it was. ---
# Spec: https://modelcontextprotocol.io/specification/2026-07-28/changelog
MODERN_PROTOCOLS = ["2026-07-28"]
_K = "io.modelcontextprotocol/"
_TOOLS_TTL_MS = 300000


def _legacy_info():
    r = _handle_legacy({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})["result"]
    return r["serverInfo"], r.get("instructions"), {k: {} for k in r.get("capabilities", {})}


def _modern_error(mid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": mid, "error": err}


def _handle_modern(msg):
    mid, method = msg.get("id"), msg.get("method")
    if mid is None:
        return None
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    version = meta.get(_K + "protocolVersion")
    if not isinstance(version, str):
        return _modern_error(mid, -32602, "Missing _meta io.modelcontextprotocol/protocolVersion")
    if version not in MODERN_PROTOCOLS:
        return _modern_error(mid, -32022, "Unsupported protocol version",
                             {"supported": MODERN_PROTOCOLS + PROTOCOLS, "requested": version})
    if not isinstance(meta.get(_K + "clientCapabilities"), dict):
        return _modern_error(mid, -32602, "Missing _meta io.modelcontextprotocol/clientCapabilities")
    server_info, instructions, caps = _legacy_info()
    if method == "server/discover":
        result = {"resultType": "complete", "supportedVersions": list(MODERN_PROTOCOLS), "capabilities": caps,
                  "_meta": {_K + "serverInfo": server_info}, "ttlMs": 3600000, "cacheScope": "public"}
        if instructions:
            result["instructions"] = instructions
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method not in ("tools/list", "tools/call"):
        return _modern_error(mid, -32601, f"Method not found: {method}")
    resp = _handle_legacy(msg)
    if "result" in resp:
        result = dict(resp["result"])
        result["resultType"] = "complete"
        result.setdefault("_meta", {})[_K + "serverInfo"] = server_info
        if method == "tools/list":
            result["ttlMs"] = _TOOLS_TTL_MS
            result["cacheScope"] = "public"
        resp = {"jsonrpc": "2.0", "id": mid, "result": result}
    return resp


def handle(msg):
    """Dual-era: server/discover or a request with modern _meta is stateless 2026-07-28; initialize keeps the old flow."""
    params = msg.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    method = msg.get("method")
    if method == "server/discover" or (method != "initialize" and isinstance(meta, dict)
                                       and _K + "protocolVersion" in meta):
        return _handle_modern(msg)
    return _handle_legacy(msg)


def main():
    for s in (sys.stdin, sys.stdout):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(msg) if isinstance(msg, dict) else None
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
