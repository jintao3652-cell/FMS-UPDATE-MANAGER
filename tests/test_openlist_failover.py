import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openlist  # noqa: E402


class OpenlistSourceOrderTests(unittest.TestCase):
    def test_default_order_primary_first(self):
        openlist._set_active_base(openlist.OPENLIST_PRIMARY_BASE_URL)
        self.assertEqual(
            openlist.openlist_ordered_base_urls(),
            [openlist.OPENLIST_PRIMARY_BASE_URL, openlist.OPENLIST_FALLBACK_BASE_URL],
        )

    def test_active_source_moves_first(self):
        openlist._set_active_base(openlist.OPENLIST_FALLBACK_BASE_URL)
        try:
            self.assertEqual(
                openlist.openlist_ordered_base_urls()[0],
                openlist.OPENLIST_FALLBACK_BASE_URL,
            )
        finally:
            openlist._set_active_base(openlist.OPENLIST_PRIMARY_BASE_URL)


class OpenlistFailoverTests(unittest.TestCase):
    def setUp(self):
        openlist._set_active_base(openlist.OPENLIST_PRIMARY_BASE_URL)
        openlist.OPENLIST_TOKEN_CACHE = ""
        openlist._OPENLIST_TOKEN_BASE = ""

    def test_login_falls_over_on_network_error(self):
        calls = []

        def fake_post(path, payload, headers, timeout, base_url):
            calls.append(base_url)
            if base_url == openlist.OPENLIST_PRIMARY_BASE_URL:
                raise openlist._OpenListNetworkError("connection refused")
            return (
                '{"code":200,"data":{"token":"tok-fallback"}}',
                200,
            )

        with mock.patch.object(openlist, "_openlist_post", side_effect=fake_post):
            token = openlist.openlist_login_request()

        self.assertEqual(token, "tok-fallback")
        self.assertEqual(calls[0], openlist.OPENLIST_PRIMARY_BASE_URL)
        self.assertEqual(calls[1], openlist.OPENLIST_FALLBACK_BASE_URL)
        self.assertEqual(openlist.openlist_active_base_url(), openlist.OPENLIST_FALLBACK_BASE_URL)

    def test_login_raises_when_all_sources_down(self):
        with mock.patch.object(
            openlist,
            "_openlist_post",
            side_effect=openlist._OpenListNetworkError("timeout"),
        ):
            with self.assertRaises(ValueError) as ctx:
                openlist.openlist_login_request()
        self.assertIn("均不可达", str(ctx.exception))

    def test_authed_post_failover_and_relogin(self):
        calls = []

        def fake_post(path, payload, headers, timeout, base_url):
            calls.append((path, base_url, headers.get("Authorization", "")))
            if base_url == openlist.OPENLIST_PRIMARY_BASE_URL:
                raise openlist._OpenListNetworkError("reset")
            if len(calls) == 2:
                return ('{"code":200,"data":{"token":"tok-b"}}', 200)  # login
            if path == openlist.OPENLIST_LIST_PATH:
                return (
                    '{"code":200,"data":{"content":[{"name":"a.zip","is_dir":false}]}}',
                    200,
                )
            return ('{"code":200,"data":{"raw_url":"http://x/file"}}', 200)

        with mock.patch.object(openlist, "_openlist_post", side_effect=fake_post):
            items = openlist.openlist_list_dir_auto_request("/导航数据/2609/MSFS")

        self.assertEqual(items, [{"name": "a.zip", "is_dir": False}])
        self.assertEqual(openlist.openlist_active_base_url(), openlist.OPENLIST_FALLBACK_BASE_URL)
        # 缓存为空 -> 先登录（主源网络失败）-> 登录（备用源成功）-> 列表（备用源）
        self.assertEqual(calls[0][0], openlist.OPENLIST_LOGIN_PATH)
        self.assertEqual(calls[0][1], openlist.OPENLIST_PRIMARY_BASE_URL)
        self.assertEqual(calls[1], (openlist.OPENLIST_LOGIN_PATH, openlist.OPENLIST_FALLBACK_BASE_URL, ""))
        self.assertEqual(calls[2], (openlist.OPENLIST_LIST_PATH, openlist.OPENLIST_FALLBACK_BASE_URL, "tok-b"))

    def test_authed_post_token_error_triggers_relogin(self):
        state = {"phase": 0}

        def fake_post(path, payload, headers, timeout, base_url):
            auth = headers.get("Authorization", "")
            if path == openlist.OPENLIST_LOGIN_PATH:
                return ('{"code":200,"data":{"token":"fresh"}}', 200)
            if state["phase"] == 0:
                state["phase"] = 1
                # OpenList 风格：HTTP 200 + body code 401
                return ('{"code":401,"message":"invalid token"}', 200)
            self.assertEqual(auth, "fresh")
            return (
                '{"code":200,"data":{"content":[{"name":"ok.zip","is_dir":false}]}}',
                200,
            )

        openlist.OPENLIST_TOKEN_CACHE = "stale"
        openlist._OPENLIST_TOKEN_BASE = openlist.OPENLIST_PRIMARY_BASE_URL
        with mock.patch.object(openlist, "_openlist_post", side_effect=fake_post):
            items = openlist.openlist_list_dir_auto_request("/x")

        self.assertEqual(items, [{"name": "ok.zip", "is_dir": False}])
        self.assertEqual(openlist.OPENLIST_TOKEN_CACHE, "fresh")

    def test_non_json_error_page_fails_over(self):
        calls = []

        def fake_post(path, payload, headers, timeout, base_url):
            calls.append((path, base_url))
            if base_url == openlist.OPENLIST_PRIMARY_BASE_URL:
                if path == openlist.OPENLIST_LOGIN_PATH:
                    return ('{"code":200,"data":{"token":"tok"}}', 200)
                # Cloudflare 拦截页：HTTP 403 + HTML body
                raise openlist._OpenListHTTPError(403, "<html>Forbidden</html>")
            if path == openlist.OPENLIST_LOGIN_PATH:
                return ('{"code":200,"data":{"token":"tok-b"}}', 200)
            return (
                '{"code":200,"data":{"content":[{"name":"b.zip","is_dir":false}]}}',
                200,
            )

        with mock.patch.object(openlist, "_openlist_post", side_effect=fake_post):
            items = openlist.openlist_list_dir_auto_request("/x")

        self.assertEqual(items, [{"name": "b.zip", "is_dir": False}])
        self.assertEqual(openlist.openlist_active_base_url(), openlist.OPENLIST_FALLBACK_BASE_URL)
        list_calls = [c for c in calls if c[0] == openlist.OPENLIST_LIST_PATH]
        self.assertEqual(len(list_calls), 2)

    def test_business_error_does_not_fail_over(self):
        def fake_post(path, payload, headers, timeout, base_url):
            if path == openlist.OPENLIST_LOGIN_PATH:
                return ('{"code":200,"data":{"token":"tok"}}', 200)
            raise openlist._OpenListHTTPError(500, '{"message":"boom"}')

        with mock.patch.object(openlist, "_openlist_post", side_effect=fake_post):
            with self.assertRaises(ValueError) as ctx:
                openlist.openlist_list_dir_auto_request("/x")
        self.assertIn("OpenList 目录读取失败 (500)", str(ctx.exception))
        self.assertEqual(openlist.openlist_active_base_url(), openlist.OPENLIST_PRIMARY_BASE_URL)


class OpenlistDownloadFailoverTests(unittest.TestCase):
    def setUp(self):
        import io
        import shutil
        import tempfile

        self.io = io
        openlist._set_active_base(openlist.OPENLIST_PRIMARY_BASE_URL)
        openlist.OPENLIST_TOKEN_CACHE = ""
        openlist._OPENLIST_TOKEN_BASE = ""
        self.tmp = tempfile.mkdtemp(prefix="fms_dl_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    class _FakeResp:
        def __init__(self, data: bytes, status: int = 200):
            self.status = status
            self._buf = io.BytesIO(data)

        def read(self, n):
            return self._buf.read(n)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def test_download_switches_source_midway(self):
        import urllib.error

        addon = openlist.Addon(
            name="Test Jet",
            description="",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="test-jet",
        )
        meta_calls = []

        def fake_meta(file_path):
            meta_calls.append(openlist.openlist_active_base_url())
            return {"raw_url": openlist.openlist_active_base_url() + "/dl/" + file_path}

        def fake_urlopen(req, timeout):
            if "pan.cnrpg.top" in req.full_url:
                raise urllib.error.URLError("connection reset during download")
            return self._FakeResp(b"NAVDATA-BYTES")

        messages = []
        with mock.patch.object(
            openlist, "list_openlist_cycle_msfs_items", return_value=[{"name": "X.zip", "is_dir": False}]
        ), mock.patch.object(
            openlist, "openlist_cycle_msfs_actual_path", return_value="/导航数据/2609/msfs"
        ), mock.patch.object(
            openlist, "select_openlist_archive_for_addon", return_value={"name": "X.zip"}
        ), mock.patch.object(
            openlist, "openlist_get_file_meta_auto_request", side_effect=fake_meta
        ), mock.patch.object(openlist, "urlopen", side_effect=fake_urlopen):
            result = openlist.download_openlist_archive_for_addon(
                addon,
                "2609",
                Path(self.tmp),
                progress_callback=messages.append,
            )

        self.assertEqual(result["archive_name"], "X.zip")
        self.assertTrue(Path(result["archive_path"]).exists())
        # 第一次 meta 来自主源，下载失败后第二次 meta 来自备用源
        self.assertEqual(meta_calls[0], openlist.OPENLIST_PRIMARY_BASE_URL)
        self.assertEqual(meta_calls[-1], openlist.OPENLIST_FALLBACK_BASE_URL)
        self.assertEqual(openlist.openlist_active_base_url(), openlist.OPENLIST_FALLBACK_BASE_URL)
        self.assertTrue(any("切换备用源" in m for m in messages))


if __name__ == "__main__":
    unittest.main()
