"""Extract numbers, money, dates and times from Japanese text and check that a summary's
facts appear in its source.

Standard library only. No network. Deterministic: same input, same answer.

Japanese writes one number many ways: 3,500万円 / 三千五百万円 / 35,000,000円 / 3500万円,
令和7年4月1日 / 2025年4月1日 / 2025/4/1 / R7.4.1, 午後2時 / 14:00, 1割 / 10%.
Everything is normalized first, then compared by value and unit.
"""
import calendar
import re
import unicodedata

# ---------------------------------------------------------------- numbers
_KDIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KSMALL = {"十": 10, "百": 100, "千": 1000}
_KBIG = {"万": 10**4, "億": 10**8, "兆": 10**12}
_NUMCH = "0-9〇零一二三四五六七八九十百千万億兆"


def parse_number(tok):
    """'3,500万' -> 35000000, '三千五百万' -> 35000000, '二〇二五' -> 2025, '1.5億' -> 150000000.
    Returns int or float, or None if it is not a number."""
    tok = tok.replace(",", "")
    if not tok or tok.strip(".") == "":
        return None
    total, section, cur = 0, 0, ""
    for ch in tok:
        if ch.isdigit() or ch == ".":
            cur += ch
        elif ch in _KDIGIT:
            cur += str(_KDIGIT[ch])
        elif ch in _KSMALL:
            n = float(cur) if cur else 1
            section += n * _KSMALL[ch]
            cur = ""
        elif ch in _KBIG:
            if cur:
                section += float(cur)
            total += (section or 1) * _KBIG[ch]
            section, cur = 0, ""
        else:
            return None
    if cur:
        if cur.count(".") > 1:
            return None
        section += float(cur)
    v = total + section
    return int(v) if float(v).is_integer() else round(v, 10)


# units after a number, longest first. value: (unit class, multiplier)
_UNITS = [
    ("パーセント", "%", 1), ("%", "%", 1), ("割", "%", 10),
    ("円", "円", 1), ("ドル", "USD", 1), ("ユーロ", "EUR", 1),
    ("箇月", "か月", 1), ("か月", "か月", 1), ("ヶ月", "か月", 1), ("カ月", "か月", 1), ("ケ月", "か月", 1), ("ヵ月", "か月", 1),
    ("時間", "時間", 1), ("日間", "日間", 1), ("週間", "週間", 1), ("年間", "年間", 1), ("年度", "年度", 1),
    ("人", "人", 1), ("名", "人", 1), ("件", "件", 1), ("社", "社", 1), ("回", "回", 1), ("個", "個", 1),
    ("台", "台", 1), ("本", "本", 1), ("枚", "枚", 1), ("歳", "歳", 1), ("才", "歳", 1), ("倍", "倍", 1),
    ("拠点", "拠点", 1), ("店舗", "店舗", 1), ("店", "店舗", 1), ("か所", "か所", 1), ("ヶ所", "か所", 1), ("カ所", "か所", 1),
    ("ポイント", "ポイント", 1), ("pt", "ポイント", 1), ("点", "点", 1), ("位", "位", 1), ("号", "号", 1), ("階", "階", 1),
    ("期", "期", 1), ("年", "年", 1), ("月", "月", 1), ("日", "日", 1), ("週", "週", 1), ("分", "分", 1), ("秒", "秒", 1),
    ("kWh", "kWh", 1), ("km", "km", 1), ("kg", "kg", 1), ("cm", "cm", 1), ("mm", "mm", 1), ("ha", "ha", 1),
    ("TB", "TB", 1), ("GB", "GB", 1), ("MB", "MB", 1), ("m", "m", 1), ("g", "g", 1), ("t", "t", 1),
]
_APPROX_BEFORE = ("約", "およそ", "おおよそ", "ほぼ", "概ね", "おおむね", "大体", "だいたい", "推定", "見込み")
_APPROX_AFTER = ("程度", "前後", "ほど", "くらい", "ぐらい", "超", "強", "弱", "余り", "あまり")
# words that start with a kanji numeral but are not quantities
_IDIOMS = ("一部", "一緒", "一方", "一旦", "一応", "一般", "一番", "一層", "一律", "一括", "一致", "一覧", "一環", "一段",
           "一斉", "一定", "一時", "一体", "一向", "一切", "一同", "一連", "一新", "一面", "一流", "一種", "万一", "万全",
           "万能", "千葉", "十分", "三菱", "三井", "一宮", "四国", "九州", "八百屋", "千代田", "百貨店", "二重", "一言",
           "一人一人", "一つ一つ", "一歩", "唯一", "統一", "同一", "随一", "単一", "均一", "一本化", "一元")

_ERAS = {"令和": 2018, "平成": 1988, "昭和": 1925, "大正": 1911, "明治": 1867,
         "R": 2018, "H": 1988, "S": 1925, "T": 1911, "M": 1867}
_WEEK = "月火水木金土日"
_N = f"[0-9〇一二三四五六七八九十]+"

_DATE_PATTERNS = [
    # era with full date: 令和7年4月1日 / 令和元年5月1日 / R7.4.1
    ("era_ymd", re.compile(rf"(令和|平成|昭和|大正|明治)\s*({_N}|元)\s*年\s*({_N})\s*月\s*({_N})\s*日")),
    ("era_ymd", re.compile(r"(?<![A-Za-z])([RHSTM])\s*(\d{1,2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)")),
    ("ymd", re.compile(rf"({_N})\s*年\s*({_N})\s*月\s*({_N})\s*日")),
    ("ymd", re.compile(r"(?<!\d)(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?!\d)")),
    ("era_ym", re.compile(rf"(令和|平成|昭和|大正|明治)\s*({_N}|元)\s*年\s*({_N})\s*月(?!\s*{_N}\s*日)")),
    ("ym", re.compile(rf"(?<![0-9〇一二三四五六七八九十])({_N})\s*年\s*({_N})\s*月(?!\s*{_N}\s*日)")),
    ("md", re.compile(rf"(?<![0-9〇一二三四五六七八九十年])({_N})\s*月\s*({_N})\s*日")),
    ("md", re.compile(r"(?<![\d/.])(\d{1,2})/(\d{1,2})(?![\d/])")),
    ("era_y", re.compile(rf"(令和|平成|昭和|大正|明治)\s*({_N}|元)\s*年(?!\s*{_N}\s*月)")),
]
_TIME_PATTERNS = [
    ("hm", re.compile(rf"(午前|午後)?\s*({_N})\s*時\s*(?:({_N})\s*分|(半))?(?!間)")),
    ("hm", re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")),
]
_WARI_RE = re.compile(rf"(?<![0-9〇一二三四五六七八九十])({_N})割(?:({_N})分)?(?:({_N})厘)?")
_NUM_RE = re.compile(rf"(?<![A-Za-z])[{_NUMCH}](?:[{_NUMCH}.]|,(?=\d))*")


def _n(s):
    return parse_number(s) if s != "元" else 1


def normalize(text):
    """NFKC (full-width digits and letters to half-width, ％ to %, （ to ( )."""
    return unicodedata.normalize("NFKC", text)


def _weekday_after(text, end):
    m = re.match(r"\s*\(([月火水木金土日])(?:曜日?)?\)", text[end:])
    return m.group(1) if m else None


def _ymd_ok(y, m, d):
    try:
        return 1 <= m <= 12 and 1 <= d <= calendar.monthrange(y or 2024, m)[1]
    except (TypeError, ValueError):
        return False


def extract(text):
    """Return the list of facts in text, in reading order. Each fact:
    {kind: number|date|time, text, start, end, value, unit, normalized, approx, issues}"""
    t = normalize(text)
    facts, taken = [], [False] * len(t)

    def free(a, b):
        return not any(taken[a:b])

    def take(a, b):
        for i in range(a, b):
            taken[i] = True

    for kind, rx in _DATE_PATTERNS:
        for m in rx.finditer(t):
            if not free(m.start(), m.end()):
                continue
            g = m.groups()
            y = mo = d = None
            if kind == "era_ymd":
                y, mo, d = _ERAS[g[0]] + _n(g[1]), _n(g[2]), _n(g[3])
            elif kind == "ymd":
                y, mo, d = _n(g[0]), _n(g[1]), _n(g[2])
            elif kind == "era_ym":
                y, mo = _ERAS[g[0]] + _n(g[1]), _n(g[2])
            elif kind == "ym":
                y, mo = _n(g[0]), _n(g[1])
            elif kind == "md":
                mo, d = _n(g[0]), _n(g[1])
            elif kind == "era_y":
                y = _ERAS[g[0]] + _n(g[1])
                take(m.start(), m.end())
                facts.append({"kind": "number", "text": m.group(0), "start": m.start(), "end": m.end(), "value": y,
                              "unit": "年", "normalized": f"{y}年", "approx": False, "issues": []})
                continue
            if None in (mo,) or (d is not None and not _ymd_ok(y, mo, d)) or not (1 <= mo <= 12):
                continue
            if y is not None and y < 100 and kind in ("ymd", "ym"):
                continue
            issues = []
            wd = _weekday_after(t, m.end())
            if wd and y and d:
                real = _WEEK[calendar.weekday(y, mo, d)]
                if real != wd:
                    issues.append({"code": "W_WEEKDAY_MISMATCH",
                                   "message": f"{y}-{mo:02d}-{d:02d} is a {real}曜日, text says {wd}",
                                   "message_ja": f"{y}年{mo}月{d}日は{real}曜日。文中は({wd})"})
            norm = "-".join(["%04d" % y if y else "????", "%02d" % mo, "%02d" % d if d else "??"])
            take(m.start(), m.end())
            facts.append({"kind": "date", "text": m.group(0), "start": m.start(), "end": m.end(),
                          "value": {"year": y, "month": mo, "day": d}, "unit": "date", "normalized": norm,
                          "approx": False, "issues": issues})

    for kind, rx in _TIME_PATTERNS:
        for m in rx.finditer(t):
            if not free(m.start(), m.end()):
                continue
            g = m.groups()
            if len(g) == 4:
                h = _n(g[1])
                mi = 30 if g[3] else (_n(g[2]) if g[2] else 0)
                if g[0] == "午後" and h is not None and h < 12:
                    h += 12
                if g[0] == "午前" and h == 12:
                    h = 0
            else:
                h, mi = int(g[0]), int(g[1])
            if h is None or mi is None or not (0 <= h <= 24 and 0 <= mi < 60):
                continue
            take(m.start(), m.end())
            facts.append({"kind": "time", "text": m.group(0), "start": m.start(), "end": m.end(),
                          "value": {"hour": h, "minute": mi}, "unit": "time", "normalized": f"{h:02d}:{mi:02d}",
                          "approx": False, "issues": []})

    for m in _WARI_RE.finditer(t):  # 1割5分 = 15%, 2割 = 20%
        if not free(m.start(), m.end()):
            continue
        w, bu, rin = (_n(x) if x else 0 for x in m.groups())
        if w is None or bu is None or rin is None:
            continue
        v = round(w * 10 + bu + rin / 10, 10)
        v = int(v) if float(v).is_integer() else v
        take(m.start(), m.end())
        facts.append({"kind": "number", "text": m.group(0), "start": m.start(), "end": m.end(), "value": v, "unit": "%",
                      "normalized": f"{v}%", "approx": False, "issues": []})

    for m in _NUM_RE.finditer(t):
        a, b = m.start(), m.end()
        tok = m.group(0).rstrip(".")
        b = a + len(tok)
        if not free(a, b):
            continue
        pure_kanji = not re.search(r"\d", tok)
        rest = t[b:]
        unit, cls, mult = "", "", 1
        for u, c, k in _UNITS:
            if rest.startswith(u):
                if u.isascii() and u.isalpha() and len(rest) > len(u) and rest[len(u)].isascii() and rest[len(u)].isalpha():
                    continue  # 'm' in 'mail'
                unit, cls, mult = u, c, k
                break
        if pure_kanji:
            word = t[a:b + 3]
            if not unit or any(word.startswith(w) for w in _IDIOMS) or any(t[max(0, a - 1):a + len(w) - 1] == w for w in _IDIOMS):
                continue
            if len(tok) == 1 and a > 0 and re.match(r"[一-鿿]", t[a - 1]) and t[a - 1] not in "約計総全各":
                continue
        if tok in ("万", "億", "兆", "十", "百", "千") and not unit:
            continue
        v = parse_number(tok)
        if v is None:
            continue
        prefix = t[max(0, a - 1):a]
        if prefix in ("$", "＄") and not cls:
            cls = "USD"
        if prefix in ("¥", "￥") and not cls:
            cls = "円"
        v = v * mult
        v = int(v) if float(v).is_integer() else round(v, 10)
        before, after = t[max(0, a - 6):a], t[b + len(unit):b + len(unit) + 3]
        approx = any(before.rstrip().endswith(w) for w in _APPROX_BEFORE) or any(after.startswith(w) for w in _APPROX_AFTER)
        end = b + len(unit)
        take(a, end)
        facts.append({"kind": "number", "text": t[a:end], "start": a, "end": end, "value": v, "unit": cls,
                      "normalized": f"{v}{cls}", "approx": approx, "issues": []})

    facts.sort(key=lambda f: f["start"])
    return facts


# ---------------------------------------------------------------- grounding
_INTERCHANGE = [{"年", "年度"}, {"拠点", "か所"}]


def _units_compatible(a, b):
    if a == b:
        return True
    return any(a in s and b in s for s in _INTERCHANGE)


def _date_match(s, src):
    """('exact'|'year_unverified'|None)"""
    sv, rv = s["value"], src["value"]
    if sv["month"] != rv["month"]:
        return None
    if sv["day"] is not None and rv["day"] != sv["day"]:
        return None
    if sv["day"] is None and rv["day"] is not None:
        pass  # summary says "April 2025", source has a day in April 2025: fine
    if sv["year"] is not None and rv["year"] is not None and sv["year"] != rv["year"]:
        return None
    if sv["year"] is not None and rv["year"] is None:
        return "year_unverified"
    return "exact"


def check(source, summary, tolerance=0.1):
    """Check every number, amount, date and time in `summary` against `source`.

    status per fact:
      supported        same value and unit found in the source
      approx_supported summary marks it approximate (約, 程度 ...) and a source value is within `tolerance`
      year_unverified  date found but the source gives no year
      unit_unverified  value found, but one side has no unit
      unit_mismatch    value found only with a different unit (30人 vs 30件)
      unsupported      nowhere in the source
    ok is False when any fact is unsupported or unit_mismatch, or a weekday is wrong.
    """
    if not isinstance(source, str) or not isinstance(summary, str):
        raise ValueError("source and summary must be strings")
    if not 0 <= tolerance <= 1:
        raise ValueError("tolerance must be between 0 and 1")
    src = extract(source)
    out = []
    for f in extract(summary):
        status, hits = "unsupported", []
        if f["kind"] == "date":
            for s in src:
                if s["kind"] == "date":
                    r = _date_match(f, s)
                    if r == "exact":
                        status, hits = "supported", [s]
                        break
                    if r == "year_unverified" and status == "unsupported":
                        status, hits = "year_unverified", [s]
            if status == "unsupported":  # 4月1日 written as a time-less number pair? try years
                pass
        elif f["kind"] == "time":
            hits = [s for s in src if s["kind"] == "time" and s["value"] == f["value"]]
            status = "supported" if hits else "unsupported"
        else:
            nums = [s for s in src if s["kind"] == "number"]
            same = [s for s in nums if s["value"] == f["value"]]
            exact = [s for s in same if _units_compatible(s["unit"], f["unit"])]
            loose = [s for s in same if not s["unit"] or not f["unit"]]
            if exact:
                status, hits = "supported", exact
            elif loose:
                status, hits = "unit_unverified", loose
            elif same:
                status, hits = "unit_mismatch", same
            elif f["approx"] and isinstance(f["value"], (int, float)):
                near = [s for s in nums if _units_compatible(s["unit"], f["unit"]) and s["value"]
                        and abs(s["value"] - f["value"]) <= tolerance * abs(s["value"])]
                if near:
                    status, hits = "approx_supported", near
            if f["unit"] == "年" and status == "unsupported":
                yrs = [s for s in src if s["kind"] == "date" and s["value"]["year"] == f["value"]]
                if yrs:
                    status, hits = "supported", yrs
        out.append({"text": f["text"], "kind": f["kind"], "normalized": f["normalized"], "status": status,
                    "approx": f["approx"], "issues": f["issues"],
                    "source_matches": [h["text"] for h in hits[:3]], "start": f["start"], "end": f["end"]})
    bad = [x for x in out if x["status"] in ("unsupported", "unit_mismatch") or x["issues"]]
    counts = {}
    for x in out:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    return {"ok": not bad, "facts": out, "counts": counts,
            "problems": [{"text": x["text"], "normalized": x["normalized"], "status": x["status"],
                          "issues": [i["code"] for i in x["issues"]]} for x in bad],
            "note": ("Checks presence of values only, not meaning: a number can be in the source and still be used "
                     "wrongly. 値が原文にあるかだけを確かめる。意味の正しさは確かめない。")}
