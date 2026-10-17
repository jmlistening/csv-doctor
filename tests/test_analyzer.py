import json
from datetime import datetime, timezone

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.analyzer import analyze, build_report, quality_score, report_json
from src.loader import LoadedData


def test_missing_duplicates_and_immutability():
    frame = pd.DataFrame({"a": ["", "  ", None, "ok"], "b": [1, 1, 1, 2]})
    original = frame.copy(deep=True)
    result = analyze(frame)
    assert result["missing"]["count"] == 3
    assert result["missing"]["ratio"] == 3 / 8
    assert result["missing"]["by_column"][0]["ratio"] == 3 / 4
    assert result["duplicates"]["count"] == 2
    assert result["duplicates"]["ratio"] == .5
    assert_frame_equal(frame, original)


def test_iqr_and_score_denominator():
    frame = pd.DataFrame({"x": [1, 2, 3, 4, 5, 6, 7, 100], "constant": [1] * 8})
    result = analyze(frame)
    field = result["outliers"]["by_column"][0]
    assert field["q1"] == 2.75
    assert field["q3"] == 6.25
    assert field["lower"] == -2.5
    assert field["upper"] == 11.5
    assert result["outliers"]["count"] == 1
    assert result["outliers"]["applicable_cells"] == 8
    assert result["outliers"]["ratio"] == 1 / 8
    assert result["score"] == 97.5


@pytest.mark.parametrize("values,status", [([1, 2, 3], "insufficient_samples"),
    ([1, 1, 1, 1], "constant"), ([1, 1, 1, 1, 1, 100], "zero_iqr"),
    ([None, None], "insufficient_samples")])
def test_skipped_iqr(values, status):
    result = analyze(pd.DataFrame({"x": pd.Series(values, dtype="Float64")}))
    field = result["outliers"]["by_column"][0]
    assert field["status"] == status
    assert field["count"] is None
    assert result["outliers"]["ratio"] == 0


def test_non_numeric_boolean_and_empty():
    result = analyze(pd.DataFrame({"x": ["a", "b"], "flag": [True, False]}))
    assert result["outliers"]["by_column"] == []
    assert result["score"] == 100
    assert analyze(pd.DataFrame(columns=["x"]))["score"] is None
    assert analyze(pd.DataFrame())["score"] is None


def test_nonfinite_and_nullable():
    result = analyze(pd.DataFrame({"x": pd.Series([1, 2, 3, 4, float("inf"), None], dtype="Float64")}))
    assert result["outliers"]["applicable_cells"] == 4
    assert result["outliers"]["by_column"][0]["nonfinite_count"] == 1
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("m,d,o,expected", [(0, 0, 0, 100), (1, 1, 1, 0),
    (1, 0, 0, 50), (.1, .2, .3, 83)])
def test_score_boundaries(m, d, o, expected):
    assert quality_score(m, d, o) == expected
    assert quality_score(m, d, o, has_data=False) is None


@pytest.mark.parametrize("bad", [-1, 2, float("nan"), float("inf")])
def test_bad_score_inputs(bad):
    with pytest.raises(ValueError):
        quality_score(bad, 0, 0)


def test_report_json_privacy_and_timestamp():
    frame = pd.DataFrame({"城市": ["PRIVATE_CELL_MARKER", None]})
    time = datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc)
    report = build_report(LoadedData(frame, "test.csv", 42, "utf-8"), analyzed_at=time)
    content = report_json(report)
    assert b"PRIVATE_CELL_MARKER" not in content
    assert json.loads(content)["analyzed_at"] == "2026-10-17T08:00:00+00:00"
    assert json.loads(content)["analysis"]["field_types"] == {"城市": "object"}
    assert "scoring" in json.loads(content)["analysis"]


def test_all_missing_is_not_header_only():
    result = analyze(pd.DataFrame({"a": [None, None]}))
    assert result["score"] == 35
