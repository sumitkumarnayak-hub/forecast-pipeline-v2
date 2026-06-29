"""
Compare Final_Plan outputs from original vs optimized baseline engines.

Used by ``scripts/compare_baseline_engines.py`` after both scripts run in
``BASELINE_COMPARE_DIR`` compare mode.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

KEY_COLUMNS = ["hub_name", "SKU Class Prod", "day"]


@dataclass
class ColumnCompare:
    name: str
    in_original: bool
    in_optimized: bool
    dtype_original: str
    dtype_optimized: str
    dtype_match: bool
    nulls_original: int
    nulls_optimized: int
    numeric_sum_original: float | None = None
    numeric_sum_optimized: float | None = None
    numeric_sum_diff: float | None = None
    numeric_max_abs_diff: float | None = None
    numeric_mean_abs_diff: float | None = None
    rows_differing: int | None = None
    rows_compared: int | None = None
    match_pct: float | None = None
    sample_diffs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BaselineCompareReport:
    generated_at: str
    original_path: str
    optimized_path: str
    rows_original: int
    rows_optimized: int
    cols_original: int
    cols_optimized: int
    columns_only_in_original: list[str]
    columns_only_in_optimized: list[str]
    columns_common: list[str]
    column_order_match: bool
    duplicate_keys_original: int
    duplicate_keys_optimized: int
    keys_only_in_original: int
    keys_only_in_optimized: int
    keys_in_both: int
    key_columns_used: list[str]
    columns: list[ColumnCompare]
    final_plan_sum_original: float | None
    final_plan_sum_optimized: float | None
    final_plan_sum_diff: float | None
    sugg_plan_sum_original: float | None
    sugg_plan_sum_optimized: float | None
    base_plan_sum_original: float | None
    base_plan_sum_optimized: float | None
    overall_match: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _detect_key_columns(df: pd.DataFrame) -> list[str]:
    mapping = {
        "hub_name": ["hub_name", "hub"],
        "SKU Class Prod": ["sku class prod", "sku_class_prod", "sku class"],
        "day": ["day"],
    }
    found: list[str] = []
    lower = {c.strip().lower(): c for c in df.columns}
    for canonical, candidates in mapping.items():
        for cand in candidates:
            if cand in lower:
                found.append(lower[cand])
                break
    return found


def _normalize_keys(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in key_cols:
        out[c] = out[c].astype(str).str.strip()
    return out


def _is_numeric_series(a: pd.Series, b: pd.Series) -> bool:
    combined = pd.concat([a, b], ignore_index=True)
    numeric = pd.to_numeric(combined, errors="coerce")
    return numeric.notna().mean() > 0.9


def _series_stats(s: pd.Series) -> dict[str, Any]:
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().any():
        return {
            "nulls": int(s.isna().sum()),
            "sum": float(num.sum(skipna=True)),
            "mean": float(num.mean(skipna=True)),
            "std": float(num.std(skipna=True)),
            "min": float(num.min(skipna=True)),
            "max": float(num.max(skipna=True)),
        }
    return {
        "nulls": int(s.isna().sum()),
        "unique": int(s.nunique(dropna=True)),
    }


def compare_final_plan_frames(
    original: pd.DataFrame,
    optimized: pd.DataFrame,
    *,
    rtol: float = 1e-5,
    atol: float = 1e-4,
) -> BaselineCompareReport:
    notes: list[str] = []
    key_cols = _detect_key_columns(original)
    if not key_cols:
        key_cols = _detect_key_columns(optimized)
    if len(key_cols) < 3:
        notes.append(f"Could not detect all merge keys; using {key_cols}")

    cols_o = list(original.columns)
    cols_n = list(optimized.columns)
    set_o, set_n = set(cols_o), set(cols_n)
    common = [c for c in cols_o if c in set_n]
    only_o = sorted(set_o - set_n)
    only_n = sorted(set_n - set_o)
    order_match = cols_o == cols_n

    o = _normalize_keys(original, key_cols) if key_cols else original.copy()
    n = _normalize_keys(optimized, key_cols) if key_cols else optimized.copy()

    dup_o = int(o.duplicated(subset=key_cols).sum()) if key_cols else 0
    dup_n = int(n.duplicated(subset=key_cols).sum()) if key_cols else 0
    if dup_o:
        notes.append(f"Original has {dup_o:,} duplicate keys; compare uses first occurrence.")
        o = o.drop_duplicates(subset=key_cols, keep="first")
    if dup_n:
        notes.append(f"Optimized has {dup_n:,} duplicate keys; compare uses first occurrence.")
        n = n.drop_duplicates(subset=key_cols, keep="first")

    keys_only_o = keys_only_n = keys_both = 0
    merged = None
    if key_cols:
        keys_o = o[key_cols].drop_duplicates()
        keys_n = n[key_cols].drop_duplicates()
        tag_o = keys_o.assign(_src=1)
        tag_n = keys_n.assign(_src=2)
        key_union = tag_o.merge(tag_n, on=key_cols, how="outer", indicator=True)
        keys_only_o = int((key_union["_merge"] == "left_only").sum())
        keys_only_n = int((key_union["_merge"] == "right_only").sum())
        keys_both = int((key_union["_merge"] == "both").sum())
        merged = o.merge(n, on=key_cols, how="inner", suffixes=("_orig", "_opt"))

    column_results: list[ColumnCompare] = []
    overall_ok = True

    for col in sorted(set(common)):
        col_o = col
        col_n = col
        left = merged[f"{col}_orig"] if merged is not None and f"{col}_orig" in merged.columns else o[col]
        right = merged[f"{col}_opt"] if merged is not None and f"{col}_opt" in merged.columns else n[col]

        dtype_match = str(left.dtype) == str(right.dtype)
        cc = ColumnCompare(
            name=col,
            in_original=True,
            in_optimized=True,
            dtype_original=str(left.dtype),
            dtype_optimized=str(right.dtype),
            dtype_match=dtype_match,
            nulls_original=int(left.isna().sum()),
            nulls_optimized=int(right.isna().sum()),
        )

        if _is_numeric_series(left, right):
            lo = pd.to_numeric(left, errors="coerce")
            ro = pd.to_numeric(right, errors="coerce")
            cc.numeric_sum_original = float(lo.sum(skipna=True))
            cc.numeric_sum_optimized = float(ro.sum(skipna=True))
            cc.numeric_sum_diff = cc.numeric_sum_optimized - cc.numeric_sum_original
            both_valid = lo.notna() & ro.notna()
            cc.rows_compared = int(both_valid.sum())
            if both_valid.any():
                diff = (lo[both_valid] - ro[both_valid]).abs()
                cc.numeric_max_abs_diff = float(diff.max())
                cc.numeric_mean_abs_diff = float(diff.mean())
                cc.rows_differing = int((diff > atol).sum() if cc.numeric_max_abs_diff == cc.numeric_max_abs_diff else 0)
                close = np.isclose(lo[both_valid], ro[both_valid], rtol=rtol, atol=atol, equal_nan=True)
                cc.rows_differing = int((~close).sum())
                cc.match_pct = round(100.0 * float(close.mean()), 4)
                if cc.rows_differing and cc.rows_differing > 0:
                    overall_ok = False
                    idx = diff.nlargest(min(5, len(diff))).index
                    for i in idx[:5]:
                        cc.sample_diffs.append({
                            "index": int(i) if isinstance(i, (int, np.integer)) else str(i),
                            "original": float(lo.loc[i]) if pd.notna(lo.loc[i]) else None,
                            "optimized": float(ro.loc[i]) if pd.notna(ro.loc[i]) else None,
                            "abs_diff": float(diff.loc[i]),
                        })
            else:
                cc.match_pct = 100.0
        else:
            ls = left.astype(str).where(left.notna(), other=pd.NA)
            rs = right.astype(str).where(right.notna(), other=pd.NA)
            same = (ls == rs) | (ls.isna() & rs.isna())
            cc.rows_compared = int(len(same))
            cc.rows_differing = int((~same).sum())
            cc.match_pct = round(100.0 * float(same.mean()), 4) if len(same) else 100.0
            if cc.rows_differing:
                overall_ok = False

        column_results.append(cc)

    for col in only_o:
        column_results.append(ColumnCompare(
            name=col, in_original=True, in_optimized=False,
            dtype_original=str(original[col].dtype), dtype_optimized="",
            dtype_match=False, nulls_original=int(original[col].isna().sum()), nulls_optimized=0,
        ))
        overall_ok = False
    for col in only_n:
        column_results.append(ColumnCompare(
            name=col, in_original=False, in_optimized=True,
            dtype_original="", dtype_optimized=str(optimized[col].dtype),
            dtype_match=False, nulls_original=0, nulls_optimized=int(optimized[col].isna().sum()),
        ))
        overall_ok = False

    if len(original) != len(optimized):
        overall_ok = False
        notes.append(f"Row count differs: original={len(original):,}, optimized={len(optimized):,}")
    if only_o or only_n:
        overall_ok = False
    if keys_only_o or keys_only_n:
        overall_ok = False
        notes.append(f"Key mismatch: only in original={keys_only_o:,}, only in optimized={keys_only_n:,}")

    def _col_sum(df: pd.DataFrame, names: list[str]) -> float | None:
        for name in names:
            if name in df.columns:
                return float(pd.to_numeric(df[name], errors="coerce").sum(skipna=True))
        return None

    fp_o = _col_sum(original, ["Final_Plan", "final_plan"])
    fp_n = _col_sum(optimized, ["Final_Plan", "final_plan"])
    sp_o = _col_sum(original, ["sugg_plan"])
    sp_n = _col_sum(optimized, ["sugg_plan"])
    bp_o = _col_sum(original, ["Base_Plan (qty)", "BasePlan"])
    bp_n = _col_sum(optimized, ["Base_Plan (qty)", "BasePlan"])

    return BaselineCompareReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        original_path="",
        optimized_path="",
        rows_original=len(original),
        rows_optimized=len(optimized),
        cols_original=len(cols_o),
        cols_optimized=len(cols_n),
        columns_only_in_original=only_o,
        columns_only_in_optimized=only_n,
        columns_common=common,
        column_order_match=order_match,
        duplicate_keys_original=dup_o,
        duplicate_keys_optimized=dup_n,
        keys_only_in_original=keys_only_o,
        keys_only_in_optimized=keys_only_n,
        keys_in_both=keys_both,
        key_columns_used=key_cols,
        columns=column_results,
        final_plan_sum_original=fp_o,
        final_plan_sum_optimized=fp_n,
        final_plan_sum_diff=(fp_n - fp_o) if fp_o is not None and fp_n is not None else None,
        sugg_plan_sum_original=sp_o,
        sugg_plan_sum_optimized=sp_n,
        base_plan_sum_original=bp_o,
        base_plan_sum_optimized=bp_n,
        overall_match=overall_ok,
        notes=notes,
    )


def load_final_plan_parquet(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".pkl":
        return pd.read_pickle(path)
    return pd.read_parquet(path)


def format_report_text(report: BaselineCompareReport) -> str:
    lines = [
        "=" * 72,
        "BASELINE ENGINE OUTPUT COMPARISON",
        "=" * 72,
        f"Generated: {report.generated_at}",
        f"Original : {report.original_path}",
        f"Optimized: {report.optimized_path}",
        "",
        "SHAPE",
        f"  Rows    — original: {report.rows_original:,} | optimized: {report.rows_optimized:,}",
        f"  Columns — original: {report.cols_original} | optimized: {report.cols_optimized}",
        f"  Column order identical: {report.column_order_match}",
        f"  Keys used: {report.key_columns_used}",
        f"  Keys in both: {report.keys_in_both:,}",
        f"  Keys only in original: {report.keys_only_in_original:,}",
        f"  Keys only in optimized: {report.keys_only_in_optimized:,}",
        f"  Duplicate keys (original / optimized): {report.duplicate_keys_original} / {report.duplicate_keys_optimized}",
        "",
        "TOTALS",
        f"  Final_Plan sum — original: {report.final_plan_sum_original} | optimized: {report.final_plan_sum_optimized} | diff: {report.final_plan_sum_diff}",
        f"  sugg_plan sum  — original: {report.sugg_plan_sum_original} | optimized: {report.sugg_plan_sum_optimized}",
        f"  Base_Plan sum  — original: {report.base_plan_sum_original} | optimized: {report.base_plan_sum_optimized}",
        "",
    ]
    if report.columns_only_in_original:
        lines.append(f"Columns ONLY in original ({len(report.columns_only_in_original)}): {report.columns_only_in_original[:20]}")
    if report.columns_only_in_optimized:
        lines.append(f"Columns ONLY in optimized ({len(report.columns_only_in_optimized)}): {report.columns_only_in_optimized[:20]}")
    lines.append("")
    lines.append("COLUMN-BY-COLUMN (common columns with differences or dtype mismatch)")
    for cc in report.columns:
        if not cc.in_original or not cc.in_optimized:
            continue
        flag = (
            not cc.dtype_match
            or (cc.rows_differing or 0) > 0
            or (cc.numeric_sum_diff is not None and abs(cc.numeric_sum_diff) > 1e-4)
        )
        if not flag:
            continue
        lines.append(f"  [{cc.name}]")
        lines.append(f"    dtype: {cc.dtype_original} vs {cc.dtype_optimized} (match={cc.dtype_match})")
        lines.append(f"    nulls: {cc.nulls_original} vs {cc.nulls_optimized}")
        if cc.numeric_sum_diff is not None:
            lines.append(
                f"    sum: {cc.numeric_sum_original} vs {cc.numeric_sum_optimized} (diff={cc.numeric_sum_diff})"
            )
            lines.append(
                f"    max|diff|={cc.numeric_max_abs_diff} mean|diff|={cc.numeric_mean_abs_diff} "
                f"differing_rows={cc.rows_differing}/{cc.rows_compared} match%={cc.match_pct}"
            )
        elif cc.rows_differing is not None:
            lines.append(f"    differing_rows={cc.rows_differing}/{cc.rows_compared} match%={cc.match_pct}")
        if cc.sample_diffs:
            lines.append(f"    sample_diffs: {cc.sample_diffs[:3]}")
    lines.append("")
    if report.notes:
        lines.append("NOTES")
        for n in report.notes:
            lines.append(f"  - {n}")
    lines.append("")
    lines.append(f"OVERALL MATCH: {'YES' if report.overall_match else 'NO — see differences above'}")
    lines.append("=" * 72)
    return "\n".join(lines)


def save_report(report: BaselineCompareReport, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "baseline_compare_report.json"
    txt_path = out_dir / "baseline_compare_report.txt"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    txt_path.write_text(format_report_text(report), encoding="utf-8")
    return json_path, txt_path
