#!/usr/bin/env python3
"""Tests for download_sma.py and import_sma_to_influx.py. The inverter and InfluxDB are mocked.

Run: python3 -m unittest test_sma.py   (needs `pip install -r requirements.txt`)
"""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock
from zipfile import ZipFile

import download_sma as dl
import import_sma_to_influx as imp


def make_zip(entries):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class Response:
    def __init__(self, content=b"", status=200, data=None):
        self.content, self.status_code, self._data = content, status, data

    def json(self):
        return self._data


class Download(unittest.TestCase):
    def test_normalize_host(self):
        self.assertEqual(dl.normalize_host("192.168.1.5"), "https://192.168.1.5")
        self.assertEqual(dl.normalize_host(" https://sma.local/ "), "https://sma.local")
        self.assertEqual(dl.normalize_host(""), "")

    def run_main(self, argv, env):
        with mock.patch.object(sys, "argv", ["download_sma.py", *argv]), \
                mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(dl, "SMA_PASS", env.get("SMA_PASS", "")), \
                mock.patch.object(dl, "SMA_HOST", env.get("SMA_HOST", "")):
            dl.main()

    def test_missing_host_and_password(self):
        with self.assertRaises(SystemExit):
            self.run_main([], {"SMA_PASS": "x", "SMA_HOST": ""})
        with self.assertRaises(SystemExit):
            self.run_main(["--host", "1.2.3.4"], {"SMA_PASS": "", "SMA_HOST": ""})

    def test_download_keeps_only_valid_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = os.path.join(tmp, "DA1.ZIP"), os.path.join(tmp, "DA2.ZIP")
            with mock.patch.object(dl, "SMA_HOST", "https://x"), mock.patch.object(dl.requests, "post") as post:
                post.return_value = Response(make_zip({"a.csv": "x"}))
                self.assertTrue(dl.download_file("sid", "ONLINE5M", "DA1.ZIP", good))
                post.return_value = Response(b"<html>500 Error</html>")
                self.assertFalse(dl.download_file("sid", "ONLINE5M", "DA2.ZIP", bad))
            self.assertTrue(os.path.isfile(good))
            self.assertEqual(sorted(os.listdir(tmp)), ["DA1.ZIP"])  # no broken file, no .part left

    def test_dry_run_lists_missing_and_writes_nothing(self):
        listing = {"result": {"dev": {"/DIAGNOSE/ONLINE5M/": [{"f": "DA1.ZIP"}, {"f": "DA2.ZIP"}, {"f": "x.txt"}]}}}
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "ONLINE5M"))
            open(os.path.join(tmp, "ONLINE5M", "DA1.ZIP"), "w").close()  # already local
            out = io.StringIO()
            with mock.patch.object(dl, "get_session", return_value="sid"), \
                    mock.patch.object(dl.requests, "post", return_value=Response(data=listing)), \
                    mock.patch("sys.stdout", out):
                self.run_main(["--dry-run", "--host", "1.2.3.4", "--dest", tmp], {"SMA_PASS": "x"})
            self.assertIn("Would download: DA2.ZIP", out.getvalue())
            self.assertNotIn("DA1.ZIP", out.getvalue().split("Missing")[-1])
            self.assertEqual(os.listdir(os.path.join(tmp, "ONLINE5M")), ["DA1.ZIP"])


class Import(unittest.TestCase):
    def test_parse_csv_from_zip(self):
        header = ["meta"] * 5 + [",GridMs.TotW.Avg,Other.Col", "", ""]
        rows = ["01.01.2026 00:05:00,100.5,1", "01.01.2026 00:10:00,nan,2", "01.01.2026 00:15:00,-3,3"]
        csv = "\n".join(header + rows)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "DA260101.ZIP")
            with open(path, "wb") as handle:
                handle.write(make_zip({"DA260101.CSV": csv}))
            lines = imp.parse_csv_from_zip(path)
        self.assertEqual(len(lines), 2)  # the nan row is skipped
        self.assertTrue(lines[0].startswith("gridms_totw_avg,source=pv value=100.5 "))

    def test_bad_zip_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "DA1.ZIP")
            with open(path, "wb") as handle:
                handle.write(b"not a zip")
            self.assertEqual(imp.parse_csv_from_zip(path), [])

    def test_write_in_batches(self):
        with mock.patch.object(imp, "BATCH_SIZE", 2), mock.patch.object(imp.requests, "post") as post:
            post.return_value = mock.Mock(status_code=204)
            self.assertEqual(imp.write_to_influx(["a", "b", "c", "d", "e"]), 5)
            self.assertEqual(post.call_count, 3)
            post.reset_mock()
            self.assertEqual(imp.write_to_influx(["a", "b", "c"], dry_run=True), 3)
            post.assert_not_called()

    def test_influx_error_stops(self):
        with mock.patch.object(imp, "BATCH_SIZE", 2), mock.patch.object(imp.requests, "post") as post, \
                mock.patch("sys.stderr", io.StringIO()):
            post.return_value = mock.Mock(status_code=500, text="boom")
            self.assertEqual(imp.write_to_influx(["a", "b", "c"]), 0)
            self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
