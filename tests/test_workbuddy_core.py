import ast
import contextlib
import hashlib
import io
import json
import math
import os
import re
import tempfile
import time
import unittest
from pathlib import Path


SOURCE_PATH = Path(__file__).resolve().parents[1] / "workbuddy_daily.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCTIONS = {
    node.name: node
    for node in TREE.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}


def load_functions(*names, **globals_):
    namespace = {"__builtins__": __builtins__, **globals_}
    body = [FUNCTIONS[name] for name in names]
    module = ast.Module(body=body, type_ignores=[])
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload if payload is not None else {}

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)


class CoreBehaviorTests(unittest.TestCase):
    def test_claim_ready_prefers_claimable_rows_and_correct_platform(self):
        desktop_tasks = {
            "code": 0,
            "data": {"tasks": [
                {"task_code": "desktop_ready", "accept_status": "accepted",
                 "progress": {"current": 1, "target": 1}},
                {"task_code": "fallback_done", "accept_status": "completed",
                 "progress": {}},
                {"task_code": "already_done", "accept_status": "claimed",
                 "claimed": True, "progress": {"current": 1, "target": 1}},
            ]},
        }
        mp_tasks = {
            "code": 0,
            "data": {"tasks": [
                {"task_code": "desktop_ready", "accept_status": "accepted",
                 "progress": {"current": 0, "target": 1}},
                {"task_code": "mp_ready", "accept_status": "accepted",
                 "progress": {"current": 2, "target": 2}},
            ]},
        }

        class Session:
            def __init__(self):
                self.posts = []

            def get(self, url, **kwargs):
                headers = kwargs.get("headers")
                return FakeResponse(payload=mp_tasks if headers else desktop_tasks)

            def post(self, url, **kwargs):
                self.posts.append((url, kwargs.get("headers")))
                return FakeResponse(payload={
                    "code": 0,
                    "data": {"credit": 10, "energy": 1},
                })

        sleep_calls = []
        module = load_functions(
            "_api_code_ok", "_claim_response_ok", "claim", "_mp_claim",
            "claim_ready_tasks",
            _as_int=lambda value, default=0: int(value or default),
            BASE="https://example.test",
            MP_HEADER={"X-Client-Platform": "miniprogram"},
            MP_TASK_CODES=set(),
            time=type("Time", (), {"sleep": staticmethod(sleep_calls.append)}),
        )
        session = Session()
        logs = []
        module["claim_ready_tasks"](session, logs.append)

        claimed_urls = [url.rsplit("/", 2)[-2] for url, _ in session.posts]
        self.assertEqual({"desktop_ready", "fallback_done", "mp_ready"}, set(claimed_urls))
        self.assertEqual(3, len(session.posts))
        self.assertEqual(
            ["desktop_ready", "fallback_done", "mp_ready"],
            sorted(claimed_urls),
        )
        self.assertIn("达标补领完成", " ".join(logs))
        empty_ok, _, _ = module["_claim_response_ok"](
            FakeResponse(payload={}), {})
        self.assertFalse(empty_ok)

    def test_sign_checks_status_before_claim_and_does_not_fake_empty_success(self):
        calls = []

        def api_retry(session, method, url, **kwargs):
            calls.append(url)
            if url.endswith("checkin-activity-status"):
                return FakeResponse(payload={
                    "code": 0,
                    "data": {"active": True, "today_checked_in": False},
                })
            return FakeResponse(payload={"code": 0, "data": {}})

        module = load_functions(
            "_api_code_ok", "t_sign",
            api_retry=api_retry,
            BASE="https://example.test",
            is_enterprise_denial=lambda status, payload: False,
            _checkin_status=lambda session: {"today_checked_in": False},
            _checkin_tail=lambda session: "（签到连签2天）",
            t_daily_activity=lambda *args: calls.append("daily-activity"),
        )
        logs = []
        module["t_sign"](object(), "u1", "nick", logs.append)
        self.assertEqual(1, sum("checkin-activity-status" in c for c in calls))
        self.assertIn("daily-checkin", " ".join(calls))
        self.assertIn("签到未确认", " ".join(logs))
        self.assertNotIn("签到成功", " ".join(logs))

    def test_travel_claim_uses_record_id_and_real_reward(self):
        response_queue = [
            FakeResponse(payload={"code": 0, "data": {"has_buddy": True}}),
            FakeResponse(payload={
                "code": 0,
                "data": {
                    "state": "arrived",
                    "record_id": "record-42",
                    "daily_limit_reached": True,
                },
            }),
            FakeResponse(payload={
                "code": 0,
                "data": {"reward_credit": 30},
            }),
        ]
        session = FakeSession(response_queue)
        module = load_functions(
            "_api_code_ok", "_dig", "t_travel", BASE="https://example.test")
        logs = []
        module["t_travel"](session, "u1", "nick", logs.append)
        claim_call = [call for call in session.calls
                      if call[1].endswith("/buddy/travel/claim")][0]
        self.assertEqual({"record_id": "record-42"}, claim_call[2]["json"])
        self.assertIn("+30积分", " ".join(logs))

    def test_makeup_candidates_use_server_calendar_and_exclude_made_up_dates(self):
        module = load_functions("_dig", "_makeup_candidates", re=re, math=math)
        streak_body = {
            "code": 0,
            "data": {
                "launch_date": "2026-10-10",
                "streak": {"makeup_dates": ["2026-10-19", "2026-10-20"]},
            },
        }
        heatmap_body = {
            "code": 0,
            "data": {
                "today": {"date": "2026-10-21"},
                "cells": [
                    {"date": "2026-09-30", "score": 0},
                    {"date": "2026-10-18", "score": 0},
                    {"date": "2026-10-19", "score": 0},
                    {"date": "2026-10-20", "score": 0},
                    {"date": "2026-10-21", "score": 0},
                ],
            },
        }
        candidates = module["_makeup_candidates"](streak_body, heatmap_body)
        self.assertEqual(["2026-10-18"], candidates)

    def test_compensation_local_guard_prevents_repeated_claims(self):
        class Session:
            def __init__(self):
                self.claim_calls = 0

            def post(self, url, **kwargs):
                if url.endswith("/compensation-status"):
                    return FakeResponse(payload={
                        "code": 0,
                        "data": {
                            "active": True,
                            "claimed": False,
                            "credit_num": 500,
                            "end_time": "2026-10-22 23:59:59",
                        },
                    })
                self.claim_calls += 1
                return FakeResponse(payload={"code": 0, "data": {}})

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "benefit-state.json")
            module = load_functions(
                "_as_int", "_api_code_ok", "_benefit_state_path",
                "_benefit_state_load",
                "_benefit_state_save", "_benefit_guard_key",
                "_benefit_guard_get", "_benefit_guard_mark",
                "_benefit_status", "_benefit_claim",
                "_benefit_actual_credit", "t_compensation",
                os=os, json=json, time=time, re=re, hashlib=hashlib,
                CBDOMAIN="https://example.test",
                BENEFIT_STATE_FILE=state_path,
                api_retry=lambda session, method, url, **kwargs: session.post(url),
                is_enterprise_denial=lambda status, payload: False,
            )
            session = Session()
            logs = []
            module["t_compensation"](session, "uid-1", logs.append)
            module["t_compensation"](session, "uid-1", logs.append)

            self.assertEqual(1, session.claim_calls)
            self.assertIn("未提供实际到账额", " ".join(logs))
            self.assertIn("本地防重", " ".join(logs))

    def test_serverchan_sctp_url_and_title_normalization(self):
        posted = {}

        class Response:
            def json(self):
                return {"code": 0}

        class Session:
            trust_env = True

            def post(self, url, **kwargs):
                posted["url"] = url
                posted["data"] = kwargs["data"]
                return Response()

        requests_module = type("Requests", (), {"Session": Session})
        os.environ["SERVERCHAN_SENDKEY"] = "sctp123tabcdef"
        try:
            module = load_functions(
                "_serverchan_notify",
                os=os, re=re, requests=requests_module,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                ok = module["_serverchan_notify"]("标题\n第二行", "正文")
        finally:
            os.environ.pop("SERVERCHAN_SENDKEY", None)

        self.assertTrue(ok)
        self.assertEqual(
            "https://123.push.ft07.com/send/sctp123tabcdef.send",
            posted["url"],
        )
        self.assertEqual("标题 第二行", posted["data"]["title"])


if __name__ == "__main__":
    unittest.main()
