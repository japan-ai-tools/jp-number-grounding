# JP Number Grounding

<!-- mcp-name: io.github.japan-ai-tools/jp-number-grounding -->

**Check that every number, amount, date and time in an AI-written Japanese summary actually appears in its source. Kanji numerals, 万/億, full-width digits, Japanese era years and 午前/午後 are normalized first. MCP server, CLI and Python library. Standard library only, no network, MIT.**

Meeting minutes (議事録) and summaries are one of the most common jobs given to language models in Japan. A Japanese municipal survey counted 755 use cases for minutes summarization, second only to greeting drafts ([cited here](https://exawizards.com/column/article/ai-article/ai-generated-meeting-minutes/)). The known failure: a model turns a proposal into a decision, or adds a deadline nobody said.

Checking the numbers by hand is slow because Japanese writes one value many ways. A script that searches the source for the digits in the summary misses most of them:

```text
source                              summary            naive digit search   this tool
三千五百万円                         3,500万円          "3500" not found     supported
令和7年4月1日                        2025/4/1           "2025" not found     supported
午後2時                              14:00              "14" not found       supported
1割5分                               15%                "15" not found       supported
参加者12名                           12人               found                supported
問い合わせ30件                       30人               found (wrong)        unit_mismatch
次回は5月18日                        期限は5月1日        "5","1" found (wrong) unsupported
2025年4月1日(火)                     2025年4月1日(水)    found (wrong)        W_WEEKDAY_MISMATCH
```

On the 30 bundled cases this tool flags the right cases 30/30; the naive digit search gets 14/30. The cases and the rules come from the same author, so treat this as a regression suite, not proof.

## What it normalizes

- kanji and mixed numerals: 三千五百万, 3千5百万, 1億2000万, 二〇二五, full-width １２
- money, rates and counters: 円, ドル, %, パーセント, 割/分/厘, 人 = 名, 件, 社, 回, か月 = ヶ月 = カ月, 拠点 = か所, kg, km ...
- dates: 2025年4月1日, 2025/4/1, 令和7年4月1日, 令和元年, R7.4.1, 4月1日, 4/1, 2025年4月, and the weekday in (火)
- times: 14:00, 午後2時, 10時半, 午前12時
- era years: 令和6年度 = 2024年度
- approximations: 約, およそ, 程度, 前後 ... allow a tolerance (default 10%)
- words that only look like numbers are skipped: 一宮, 三菱, 統一, 一部, 万一, 同一人物

Status per fact: `supported`, `approx_supported`, `year_unverified` (source gives no year), `unit_unverified` (one side has no unit), `unit_mismatch`, `unsupported`. `ok` is false when any fact is `unsupported` or `unit_mismatch`, or a weekday does not match its date.

It checks that values are present, not that they are used correctly. A summary can quote 15% from the source and attach it to the wrong item.

## MCP server (for AI agents)

```json
{"mcpServers": {"jp-number-grounding": {"command": "python", "args": ["-m", "jpnumground.server"], "cwd": "/path/to/jp-number-grounding"}}}
```

| Tool | Input | Returns |
|---|---|---|
| `jp_number_grounding_check` | `source`, `summary`, `tolerance` | `ok`, `problems`, `counts`, `facts` (text, normalized, status, source_matches) |
| `jp_number_extract` | `text` | `facts` (kind, text, normalized, value, unit, approx, issues) |

Both tools are read-only and offline. Suggested agent rule: after writing minutes or a summary from Japanese text, call `jp_number_grounding_check` and fix or remove every `unsupported` fact before sending.

## CLI and Python

```bash
python -m jpnumground transcript.txt minutes.txt   # JSON, exit 1 when a fact is unsupported
python -m jpnumground --extract minutes.txt        # list quantities
python -m jpnumground.bench                         # score on the 30 cases
```

```python
from jpnumground import check, extract
check("予算は三千五百万円", "予算は3,800万円")["problems"]
# [{'text': '3,800万円', 'normalized': '38000000円', 'status': 'unsupported', 'issues': []}]
extract("令和7年4月1日 午後2時")[0]["normalized"]   # '2025-04-01'
```

## Limits

- It checks that each number, amount, date and time in the summary also appears in the source. It does not check meaning: a correct number in a wrong sentence passes.
- Numbers written only in words it does not know (rare counters, dialects, slang) may be missed. Unknown forms are reported, not guessed.
- Japanese text only. It is a checking aid for minutes and summaries, not a replacement for a person reading them.

## Tests

```bash
python -m unittest discover -s tests   # 26 tests
```

## 日本語

AIが書いた要約・議事録の数字・金額・日付・時刻が、元の文章(文字起こし・資料)にあるかを確かめます。漢数字・万/億・全角・和暦・午前/午後・割/分をそろえてから比べるので、「三千五百万円」と「3,500万円」、「令和7年4月1日」と「2025/4/1」は同じとみなし、言っていない期限(unsupported)や単位の取り違え(30件→30人)、日付と曜日の食い違いを返します。値があるかを確かめる道具で、意味の正しさは確かめません。標準ライブラリだけ・外部通信なし・MIT。

## License

MIT. See LICENSE.
