"""Streamlit's official app harness; no browser or user profile is touched."""

import json
from io import BytesIO
from pathlib import Path

import pytest
import streamlit as st
from openpyxl import Workbook
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def start():
    return AppTest.from_file(str(APP), default_timeout=30).run()


def demo():
    app = start()
    app.button[0].click().run()
    assert not app.exception
    return app


def navigate(app, name):
    app.radio(key="page").set_value(name).run()
    assert not app.exception
    return app


def test_landing_and_demo_navigation():
    app = start()
    assert not app.exception
    assert len(app.metric) == 0
    app.button[0].click().run()
    assert not app.exception
    assert app.metric[0].value == "37"
    assert app.metric[1].value == "6"
    for page in ["质量分析", "报告导出", "数据总览"]:
        navigate(app, page)
    assert app.session_state["report"]["analysis"]["outliers"]["count"] >= 4


def test_clean_preview_gate_and_invalidation():
    app = navigate(demo(), "数据清洗")
    original = app.session_state["loaded"].frame.copy(deep=True)
    assert not app.get("download_button")
    assert not any(box.value for box in app.checkbox)
    app.checkbox(key="clean_blank").check()
    app.checkbox(key="clean_duplicate").check().run()
    next(button for button in app.button if button.label == "预览清洗结果").click().run()
    assert not app.exception
    assert len(app.session_state["preview"]["frame"]) == 32
    assert len(app.get("download_button")) == 1
    assert app.session_state["preview"]["csv"].startswith(b"\xef\xbb\xbf")
    assert_frame_equal(app.session_state["loaded"].frame, original)
    app.checkbox(key="clean_blank").uncheck().run()
    assert not app.get("download_button")
    assert "preview" not in app.session_state


def upload_mock(monkeypatch, data, name):
    file = BytesIO(data)
    file.name = name
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: file)


def test_upload_replacement_and_error_clear_old_dataset(monkeypatch):
    upload_mock(monkeypatch, b"a,b\n1,2\n3,4", "file.csv")
    app = start()
    assert not app.exception
    assert app.metric[0].value == "2"
    upload_mock(monkeypatch, b"a,b\n1,2", "file.csv")
    app.run()
    assert app.metric[0].value == "1"
    upload_mock(monkeypatch, b"a,b\n1,2,3", "file.csv")
    app.run()
    assert not app.exception
    assert app.error
    assert "loaded" not in app.session_state
    assert "report" not in app.session_state


def test_xlsx_sheet_switch(monkeypatch):
    workbook = Workbook()
    workbook.active.title = "首张"
    workbook.active.append(["value"])
    workbook.active.append([1])
    second = workbook.create_sheet("另张")
    second.append(["value"])
    second.append([2])
    second.append([3])
    data = BytesIO()
    workbook.save(data)
    upload_mock(monkeypatch, data.getvalue(), "example.xlsx")
    app = start()
    assert not app.exception
    assert app.metric[0].value == "1"
    app.selectbox[0].set_value("另张").run()
    assert not app.exception
    assert app.metric[0].value == "2"
    assert app.session_state["loaded"].sheet == "另张"


@pytest.mark.parametrize("content", [b"a,b\n", b"a,b\n,\n,", b"text\none\ntwo"])
def test_edge_case_pages(monkeypatch, content):
    upload_mock(monkeypatch, content, "edge.csv")
    app = start()
    assert not app.exception
    for page in ["质量分析", "数据清洗", "报告导出"]:
        navigate(app, page)


def test_leaving_clean_page_resets_preview_with_options():
    app = navigate(demo(), "数据清洗")
    app.checkbox(key="clean_blank").check().run()
    next(button for button in app.button if button.label == "预览清洗结果").click().run()
    navigate(app, "报告导出")
    navigate(app, "数据清洗")
    assert not app.checkbox(key="clean_blank").value
    assert not app.get("download_button")


@pytest.mark.parametrize("content,missing_count", [
    (b"a,b\n1,2\n3,4", 0),
    (b"a,b\n1,\n3,4", 1),
    (b'a,b\n"  ",2\n3,4', 1),
    (b"a,b\n,\n,", 4),
    (b"a,b\n" + b"1,2\n" * 2000 + b"1,\n", 1),
    (b"a,b\n", 0),
])
def test_missing_chart_states_and_labels(monkeypatch, content, missing_count):
    upload_mock(monkeypatch, content, "missing.csv")
    app = start()
    assert not app.exception
    assert any(item.value == "#### 各字段缺失率" for item in app.markdown)
    assert not any(item.value == "#### 字段完整性" for item in app.markdown)
    report_before = app.session_state["report"]
    result = report_before["analysis"]
    assert result["missing"]["count"] == missing_count
    for page in ["数据总览", "质量分析"]:
        navigate(app, page)
        messages = [item.value for item in app.info]
        figures = [json.loads(chart.proto.spec) for chart in app.get("plotly_chart")]
        bars = [figure for figure in figures if figure["data"][0]["type"] == "bar"]
        complete_message = "当前数据未检测到缺失值，各字段完整率均为 100%。"
        if not result["rows"]:
            assert "当前没有可分析的数据，暂不展示缺失率。" in messages
            assert complete_message not in messages
            assert not bars
            assert app.metric[2].value == "暂无数据"
            assert app.metric[3].value == "暂无评分"
            if page == "质量分析":
                assert set(app.dataframe[0].value["缺失率"]) == {"暂无数据"}
                duplicate_metric = next(m for m in app.metric if m.label == "完整重复行比例")
                assert duplicate_metric.value == "暂无数据"
        elif missing_count == 0:
            assert messages.count(complete_message) == 1
            assert not bars
        else:
            assert complete_message not in messages
            assert len(bars) == 1
            expected = sorted(result["missing"]["by_column"], key=lambda item: item["ratio"], reverse=True)
            assert bars[0]["data"][0]["x"] == [item["column"] for item in expected]
            assert bars[0]["data"][0]["y"] == [item["ratio"] for item in expected]
            assert bars[0]["layout"]["xaxis"]["title"]["text"] == "字段"
            assert bars[0]["layout"]["yaxis"]["title"]["text"] == "缺失率"
            assert bars[0]["layout"]["yaxis"]["range"][1] <= 1
        assert app.session_state["report"] == report_before


def test_native_uploader_has_chinese_instructions():
    app = start()
    assert not app.exception
    assert app.get("file_uploader")[0].proto.label == "上传数据文件"
    assert any("将文件拖入上方区域" in item.value and "Browse files" in item.value
               for item in app.sidebar.caption)


def test_inapplicable_iqr_summary_is_not_a_zero_findings_claim(monkeypatch):
    upload_mock(monkeypatch, b"text\none\ntwo", "text.csv")
    app = start()
    assert not app.exception
    assert any(item.value == "当前无适用的 IQR 数值字段，未进行统计异常检测。"
               for item in app.caption)
    assert not any("个统计异常单元格" in item.value for item in app.markdown)
