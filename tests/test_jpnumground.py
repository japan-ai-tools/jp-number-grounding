import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jpnumground import check, extract, parse_number  # noqa: E402
from jpnumground.bench import load, score  # noqa: E402
from jpnumground.server import TOOLS, handle  # noqa: E402


def norms(text):
    return [f["normalized"] for f in extract(text)]


def status(source, summary):
    return [f["status"] for f in check(source, summary)["facts"]]


class TestParse(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(parse_number("3,500万"), 35000000)
        self.assertEqual(parse_number("三千五百万"), 35000000)
        self.assertEqual(parse_number("二〇二五"), 2025)
        self.assertEqual(parse_number("1.5億"), 150000000)
        self.assertEqual(parse_number("1億2000万"), 120000000)
        self.assertEqual(parse_number("3千5百万"), 35000000)
        self.assertIsNone(parse_number("abc"))


class TestExtract(unittest.TestCase):
    def test_money_forms_equal(self):
        self.assertEqual(norms("三千五百万円"), norms("3,500万円"))
        self.assertEqual(norms("3,500万円"), norms("35,000,000円"))

    def test_dates(self):
        self.assertEqual(norms("令和7年4月1日"), ["2025-04-01"])
        self.assertEqual(norms("R7.4.1"), ["2025-04-01"])
        self.assertEqual(norms("2025/4/1"), ["2025-04-01"])
        self.assertEqual(norms("令和元年5月1日"), ["2019-05-01"])
        self.assertEqual(norms("4月1日"), ["????-04-01"])
        self.assertEqual(norms("2025年4月"), ["2025-04-??"])

    def test_era_year_is_a_year(self):
        self.assertEqual(norms("令和6年"), ["2024年"])

    def test_times(self):
        self.assertEqual(norms("午後2時"), ["14:00"])
        self.assertEqual(norms("10時半"), ["10:30"])
        self.assertEqual(norms("午前12時"), ["00:00"])
        self.assertEqual(norms("9:05"), ["09:05"])

    def test_rates(self):
        self.assertEqual(norms("1割5分"), ["15%"])
        self.assertEqual(norms("15パーセント"), ["15%"])

    def test_counters(self):
        self.assertEqual(norms("12名"), ["12人"])
        self.assertEqual(norms("十五名"), ["15人"])
        self.assertEqual(norms("6ヶ月"), ["6か月"])

    def test_words_that_look_like_numbers(self):
        self.assertEqual(norms("一宮支店と三菱の統一書式を一部修正。万一に備える。"), [])

    def test_full_width(self):
        self.assertEqual(norms("１２名、３，５００万円"), ["12人", "35000000円"])

    def test_weekday_mismatch(self):
        f = extract("2025年4月2日(火)")[0]
        self.assertEqual(f["issues"][0]["code"], "W_WEEKDAY_MISMATCH")
        self.assertEqual(extract("2025年4月1日(火)")[0]["issues"], [])

    def test_approx_marker(self):
        self.assertTrue(extract("約3,500万円")[0]["approx"])
        self.assertTrue(extract("30人程度")[0]["approx"])
        self.assertFalse(extract("3,500万円")[0]["approx"])


class TestCheck(unittest.TestCase):
    def test_supported_across_forms(self):
        r = check("令和7年4月1日、参加者12名、予算三千五百万円、午後2時開始", "2025/4/1、12人、3,500万円、14:00開始")
        self.assertTrue(r["ok"])
        self.assertEqual(r["counts"], {"supported": 4})

    def test_invented_deadline(self):
        r = check("次回は5月8日。", "次回は5月8日。提出期限は5月1日。")
        self.assertFalse(r["ok"])
        self.assertEqual([p["normalized"] for p in r["problems"]], ["????-05-01"])

    def test_unit_mismatch(self):
        self.assertEqual(status("問い合わせは30件", "30人が問い合わせ"), ["unit_mismatch"])

    def test_approx(self):
        self.assertEqual(status("3,480万円", "約3,500万円"), ["approx_supported"])
        self.assertEqual(status("3,480万円", "3,500万円"), ["unsupported"])
        self.assertEqual(status("3,480万円", "約3,500万円") , ["approx_supported"])
        self.assertEqual(check("3,480万円", "約3,600万円", tolerance=0.01)["facts"][0]["status"], "unsupported")

    def test_year_unverified(self):
        self.assertEqual(status("締切は4月30日", "締切は2025年4月30日"), ["year_unverified"])
        self.assertTrue(check("締切は4月30日", "締切は2025年4月30日")["ok"])

    def test_unit_unverified(self):
        self.assertEqual(status("番号は300", "300円"), ["unit_unverified"])

    def test_era_year_vs_fiscal_year(self):
        self.assertEqual(status("令和6年度の実績", "2024年度の実績"), ["supported"])

    def test_weekday_makes_not_ok(self):
        self.assertFalse(check("2025年4月1日(火)", "2025年4月1日(水)")["ok"])

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            check(None, "x")
        with self.assertRaises(ValueError):
            check("a", "b", tolerance=2)


class TestBench(unittest.TestCase):
    def test_all_cases(self):
        r = score(load())
        self.assertEqual(r["jp_number_grounding_exact"], r["cases"])
        self.assertLess(r["naive_flag"], r["cases"])


class TestServer(unittest.TestCase):
    def call(self, name, args):
        return handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})["result"]

    def test_initialize_and_list(self):
        r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        names = [t["name"] for t in handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]]
        self.assertEqual(names, [t["name"] for t in TOOLS])
        for t in TOOLS:
            self.assertTrue(t["annotations"]["readOnlyHint"])

    def test_call(self):
        r = self.call("jp_number_grounding_check", {"source": "予算は二百万円", "summary": "予算は300万円"})
        self.assertFalse(r["isError"])
        self.assertFalse(r["structuredContent"]["ok"])
        r = self.call("jp_number_extract", {"text": "令和7年"})
        self.assertEqual(r["structuredContent"]["facts"][0]["normalized"], "2025年")

    def test_errors(self):
        self.assertTrue(self.call("jp_number_grounding_check", {"source": 1, "summary": "x"})["isError"])
        r = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"}})
        self.assertIn("error", r)
        self.assertIsNone(handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_stdio(self):
        req = "\n".join(json.dumps(m) for m in [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "jp_number_grounding_check", "arguments": {"source": "12名", "summary": "12人"}}}]) + "\n"
        out = subprocess.run([sys.executable, "-m", "jpnumground.server"], input=req, capture_output=True, text=True,
                             encoding="utf-8", cwd=ROOT, timeout=30).stdout.strip().splitlines()
        self.assertEqual(len(out), 2)
        self.assertTrue(json.loads(out[1])["result"]["structuredContent"]["ok"])


class TestCli(unittest.TestCase):
    def test_cli_exit_code(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.txt"), os.path.join(d, "b.txt")
            open(a, "w", encoding="utf-8").write("予算は二百万円")
            open(b, "w", encoding="utf-8").write("予算は300万円")
            p = subprocess.run([sys.executable, "-m", "jpnumground", a, b], capture_output=True, text=True,
                               encoding="utf-8", cwd=ROOT, timeout=30)
            self.assertEqual(p.returncode, 1)
            self.assertIn("unsupported", p.stdout)


if __name__ == "__main__":
    unittest.main()
