import csv
from io import StringIO

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.cleaner import clean_data, export_csv


@pytest.mark.parametrize("blank,duplicate,rows", [(False, False, 6), (True, False, 4),
    (False, True, 3), (True, True, 2)])
def test_clean_options_and_original(blank, duplicate, rows):
    frame = pd.DataFrame({"a": ["", None, "x", "x", "y", "y"], "b": [" ", None, 1, 1, 2, 2]})
    original = frame.copy(deep=True)
    cleaned = clean_data(frame, drop_blank=blank, drop_duplicates=duplicate)
    assert len(cleaned) == rows
    assert_frame_equal(frame, original)
    assert cleaned is not frame
    if not blank and not duplicate:
        assert_frame_equal(cleaned, original)


def test_nonunique_index():
    frame = pd.DataFrame({"a": [1, 1, None]}, index=[1, 1, 1])
    assert clean_data(frame, drop_blank=True, drop_duplicates=True)["a"].tolist() == [1]


def test_csv_encoding_and_formula_safety():
    frame = pd.DataFrame({"=header": ["=1+1", "+SUM(A1)", "-cmd", "@name", " \t=1", "\ntext", "正常中文"],
                          "数值": [-3, 4, -5.5, 0, 2, 3, 4]})
    original = frame.copy(deep=True)
    output = export_csv(frame)
    assert output.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(StringIO(output.decode("utf-8-sig"))))
    assert rows[0][0] == "'=header"
    assert all(row[0].startswith("'") for row in rows[1:7])
    assert rows[1][1] == "-3.0"
    assert rows[7][0] == "正常中文"
    assert_frame_equal(frame, original)


def test_retained_whitespace_and_default_noop():
    frame = pd.DataFrame({"a": [" padded ", "  "]})
    assert_frame_equal(clean_data(frame), frame)
    assert clean_data(frame, drop_blank=True).iloc[0, 0] == " padded "


def test_empty_export_has_headers():
    assert export_csv(pd.DataFrame(columns=["a"])).decode("utf-8-sig") == '"a"\r\n'
