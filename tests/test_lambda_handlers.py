import io
import json
import subprocess
import sys

import pytest

from ingestion.lambda_handlers import cpi_handler, retail_handler

WORKBOOK = b"PK\x03\x04 workbook"


class Conflict(Exception):
    response = {"Error": {"Code": "PreconditionFailed"}}


class Denied(Exception):
    response = {"Error": {"Code": "AccessDenied"}}


class FakeS3:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.metadata = {}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, IfNoneMatch, Metadata):  # noqa: N803
        assert IfNoneMatch == "*"
        if Key in self.objects:
            raise Conflict
        self.objects[Key] = Body
        self.metadata[Key] = Metadata


def upload_event(key):
    return {"Records": [{"s3": {"bucket": {"name": "lake"}, "object": {"key": key}}}]}


def test_retail_copies_workbook_and_decodes_the_key():
    s3 = FakeS3({"landing/stats_sa/retail trade.xlsx": WORKBOOK})
    result = retail_handler(upload_event("landing/stats_sa/retail+trade.xlsx"), None, client=s3)
    key = result[0]["key"]
    assert key.startswith("bronze/stats_sa/retail_trade/") and key.endswith(".xlsx")
    assert s3.metadata[key]["original-name"] == "retail%20trade.xlsx"
    assert s3.objects[key] == WORKBOOK
    assert result[0]["is_new"]
    assert s3.metadata[key]["origin"].isascii()


def test_retail_upload_of_the_same_file_is_a_no_op():
    s3 = FakeS3({"landing/a.xlsx": WORKBOOK})
    retail_handler(upload_event("landing/a.xlsx"), None, client=s3)
    assert not retail_handler(upload_event("landing/a.xlsx"), None, client=s3)[0]["is_new"]
    assert sum(k.startswith("bronze/") for k in s3.objects) == 1


def test_retail_renamed_copy_of_a_file_is_a_no_op():
    s3 = FakeS3({"landing/a.xlsx": WORKBOOK, "landing/b.xlsx": WORKBOOK})
    retail_handler(upload_event("landing/a.xlsx"), None, client=s3)
    assert not retail_handler(upload_event("landing/b.xlsx"), None, client=s3)[0]["is_new"]
    assert sum(k.startswith("bronze/") for k in s3.objects) == 1


def test_retail_rejects_a_saved_bot_challenge_page():
    s3 = FakeS3({"landing/a.xlsx": b"<html><script></script></html>"})
    with pytest.raises(ValueError, match="not an .xlsx"):
        retail_handler(upload_event("landing/a.xlsx"), None, client=s3)
    assert not any(k.startswith("bronze/") for k in s3.objects)


def test_cpi_stores_the_response(monkeypatch):
    monkeypatch.setenv("LAKE_BUCKET", "lake")
    s3 = FakeS3()
    raw = json.dumps([{"Value": 4.5}]).encode()
    result = cpi_handler({}, None, client=s3, fetch=lambda *_: raw)
    assert result["is_new"] and s3.objects[result["key"]] == raw


def test_cpi_refuses_an_empty_response(monkeypatch):
    monkeypatch.setenv("LAKE_BUCKET", "lake")
    s3 = FakeS3()
    with pytest.raises(ValueError, match="no CPI"):
        cpi_handler({}, None, client=s3, fetch=lambda *_: b"[]")
    assert not s3.objects


def test_real_s3_errors_are_not_swallowed(monkeypatch):
    monkeypatch.setenv("LAKE_BUCKET", "lake")

    class Failing(FakeS3):
        def put_object(self, **_):
            raise Denied

    with pytest.raises(Denied):
        cpi_handler({}, None, client=Failing(), fetch=lambda *_: b'[{"Value": 1}]')


def test_handlers_do_not_import_heavy_dependencies():
    code = (
        "import sys, ingestion.lambda_handlers; "
        "sys.exit(any(m in sys.modules for m in ('pandas', 'pyarrow', 'duckdb', 'openpyxl')))"
    )
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0
