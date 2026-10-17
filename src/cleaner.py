"""Opt-in cleaning and spreadsheet-safe CSV output without mutating inputs."""

from __future__ import annotations

import csv

import pandas as pd

from src.loader import normalize_missing


def clean_data(frame: pd.DataFrame, *, drop_blank: bool = False,
               drop_duplicates: bool = False) -> pd.DataFrame:
    # Use normalized comparison keys, but preserve values in retained rows.
    keys = normalize_missing(frame)
    keep = pd.Series(True, index=range(len(frame)))
    keys = keys.reset_index(drop=True)
    if drop_blank:
        keep &= ~keys.isna().all(axis=1)
    if drop_duplicates and len(keys.columns):
        remaining = keys.loc[keep]
        keep.loc[remaining.index] &= ~remaining.duplicated(keep="first")
    return frame.iloc[keep.to_numpy()].copy(deep=True).reset_index(drop=True)


def _safe_cell(value):
    if isinstance(value, str):
        candidate = value.lstrip("\ufeff \t\r\n\v\f")
        if candidate.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            return "'" + value
    return value


def export_csv(frame: pd.DataFrame) -> bytes:
    safe = frame.copy(deep=True)
    for column in safe:
        safe[column] = safe[column].map(_safe_cell)
    safe.columns = [_safe_cell(str(c)) for c in safe.columns]
    return safe.to_csv(index=False, quoting=csv.QUOTE_ALL, lineterminator="\r\n").encode("utf-8-sig")
