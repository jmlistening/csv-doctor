"""Pure analysis functions; no raw records are included in quality reports."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pandas as pd

from src.loader import LoadedData, normalize_missing

SCORE_FORMULA = "100 × (1 - 0.5M - 0.3D - 0.2O)"
IQR_WARNING = "统计异常值不一定是错误数据，请结合业务场景判断。"


def numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.select_dtypes(include="number")
            if not pd.api.types.is_bool_dtype(frame[c])
            and not pd.api.types.is_complex_dtype(frame[c])]


def finite_values(series: pd.Series) -> pd.Series:
    return series.dropna().loc[lambda s: ~s.isin([float("inf"), float("-inf")])]


def quality_score(missing: float, duplicates: float, outliers: float,
                  *, has_data: bool = True) -> float | None:
    if not has_data:
        return None
    ratios = (missing, duplicates, outliers)
    if any(not math.isfinite(r) or not 0 <= r <= 1 for r in ratios):
        raise ValueError("Ratios must be finite and between 0 and 1.")
    return round(max(0.0, min(100.0, 100 * (1 - 0.5 * missing
                                         - 0.3 * duplicates - 0.2 * outliers))), 2)


def analyze(frame: pd.DataFrame) -> dict:
    data = normalize_missing(frame)
    rows, columns = data.shape
    cells = rows * columns
    missing = [{"column": str(c), "count": int(data[c].isna().sum()),
                "ratio": float(data[c].isna().mean()) if rows else 0.0} for c in data]
    missing_count = sum(c["count"] for c in missing)
    missing_ratio = missing_count / cells if cells else 0.0
    duplicates = int(data.duplicated(keep="first").sum()) if columns else 0
    duplicate_ratio = duplicates / rows if rows else 0.0
    outliers = []
    applicable_cells = 0
    outlier_count = 0
    for column in numeric_columns(data):
        series = data[column]
        finite = finite_values(series)
        item = {"column": str(column), "sample_count": int(len(finite)),
                "nonfinite_count": int(series.isin([float("inf"), float("-inf")]).sum()),
                "status": "applicable", "count": None, "ratio": None,
                "q1": None, "q3": None, "iqr": None, "lower": None, "upper": None}
        if len(finite) < 4:
            item["status"] = "insufficient_samples"
        elif finite.nunique() <= 1:
            item["status"] = "constant"
        else:
            q1, q3 = (float(x) for x in finite.quantile([0.25, 0.75]))
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            if not all(math.isfinite(x) for x in (q1, q3, iqr, lower, upper)):
                item["status"] = "nonfinite_bounds"
            elif iqr == 0:
                item["status"] = "zero_iqr"
            else:
                count = int(((finite < lower) | (finite > upper)).sum())
                item.update(q1=q1, q3=q3, iqr=iqr, lower=lower, upper=upper,
                            count=count, ratio=count / len(finite))
                applicable_cells += len(finite)
                outlier_count += count
        outliers.append(item)
    outlier_ratio = outlier_count / applicable_cells if applicable_cells else 0.0
    return {
        "rows": rows, "columns": columns,
        "field_types": {str(c): str(data[c].dtype) for c in data},
        "missing": {"count": missing_count, "ratio": missing_ratio, "by_column": missing},
        "duplicates": {"count": duplicates, "ratio": duplicate_ratio, "keep": "first"},
        "outliers": {"method": "IQR (1.5)", "minimum_samples": 4,
                     "count": outlier_count, "applicable_cells": applicable_cells,
                     "ratio": outlier_ratio, "by_column": outliers, "warning": IQR_WARNING},
        "score": quality_score(missing_ratio, duplicate_ratio, outlier_ratio,
                               has_data=bool(cells)),
        "scoring": {"formula": SCORE_FORMULA, "M": missing_ratio, "D": duplicate_ratio,
                    "O": outlier_ratio, "weights": {"M": 0.5, "D": 0.3, "O": 0.2},
                    "missing_definition": "空值、空字符串及纯空白字符串；分母为全部单元格。",
                    "duplicate_definition": "整行比较，首次出现有效，其余重复行计数；分母为全部行。",
                    "outlier_definition": "仅计入样本不少于4且IQR>0的数值列的有限非缺失单元格；无适用列时O=0。",
                    "disclaimer": "启发式经验参考，不代表经过科学验证的数据质量标准；无单元格时暂无评分。"},
    }


def build_report(loaded: LoadedData, *, analyzed_at: datetime | None = None) -> dict:
    timestamp = analyzed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("Analysis timestamp must include a timezone.")
    return {"schema_version": "1.0", "analyzed_at": timestamp.isoformat(),
            "file": {"name": loaded.filename, "size_bytes": loaded.size_bytes,
                     "encoding": loaded.encoding, "sheet": loaded.sheet},
            "analysis": analyze(loaded.frame)}


def report_json(report: dict) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
