"""
New hub launch — Hub_Changes tab (pipeline params) + P-H Master cloning.

Ported from Product/PH Master clone_from_source_hub_mapping logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import pandas as pd

from planning_suite.config import HUB_CHANGES_COLUMNS, SHEETS_CONFIG
from planning_suite.core.dataframe import clean_sheet_df

PH_KEY_COLUMNS = ["product_id", "hub_name", "city_name"]
HUB_MAPPING_READ_RANGE = "A:F"  # match master_data.py — ignore duplicate columns past F
HUB_MAPPING_REQUIRED = ["hub_id", "hub_name", "city_id", "city_name", "Hub_active"]
PRODUCT_ID_HEADER_CANDIDATES = ["product_id", "Product ID", "product id"]


@dataclass
class HubLaunchMapping:
    new_hub: str
    source_hub: str
    product_ids: list[str] = field(default_factory=list)
    add_hub_mapping: bool = True
    city_name: str = ""
    hub_id: str = ""


def parse_product_ids_cell(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [p.strip() for p in str(value).split(",") if p.strip()]


def parse_add_hub_mapping_cell(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return True
    return str(value).strip().lower() in ("true", "yes", "y", "t", "1", "a")


def _normalize(text: Any) -> str:
    return "".join(ch.lower() for ch in str(text).strip() if ch.isalnum())


def _dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Keep first occurrence when Google Sheets returns duplicate headers."""
    if df is None or df.empty:
        return df
    if not df.columns.duplicated().any():
        return df
    return df.loc[:, ~df.columns.duplicated(keep="first")].copy()


def _col_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return one column as Series (first match if headers are duplicated)."""
    if col not in df.columns:
        raise KeyError(f"Column '{col}' not in dataframe")
    sel = df.loc[:, col]
    if isinstance(sel, pd.DataFrame):
        sel = sel.iloc[:, 0]
    return sel


def _find_header(headers: Sequence[str], candidates: Sequence[str]) -> str | None:
    lookup = {_normalize(h): h for h in headers}
    for cand in candidates:
        match = lookup.get(_normalize(cand))
        if match:
            return match
    return None


def _read_hub_mapping_df(sheets_manager) -> pd.DataFrame | None:
    """Read Hub Mapping using canonical A:F range (legacy Master Data behaviour)."""
    raw = sheets_manager.read_worksheet_uncached(
        "demand_planning_masters", "hub_mapping", HUB_MAPPING_READ_RANGE,
    )
    if raw is None or raw.empty:
        return raw
    return clean_sheet_df(raw)


def _repair_misplaced_hub_mapping_rows(
    sheets_manager,
    needed_hubs: set[str],
    *,
    dry_run: bool = False,
) -> list[str]:
    """
    Fix rows where hub data landed in duplicate columns (O:F) instead of A:F.

    Observed when the full-width sheet is read without range limiting.
    """
    if not needed_hubs:
        return []

    hm_ws_name = SHEETS_CONFIG["demand_planning_masters"]["worksheets"]["hub_mapping"]
    ws = sheets_manager._get_worksheet_quiet("demand_planning_masters", hm_ws_name)
    if ws is None:
        return []

    rows = ws.get_all_values()
    messages: list[str] = []
    repairs: list[tuple[int, list[str]]] = []

    for row_idx, row in enumerate(rows[1:], start=2):
        padded = row + [""] * max(0, 20 - len(row))
        primary_hub = padded[1].strip()
        if primary_hub:
            continue
        orphan_hub = padded[15].strip() if len(padded) > 15 else ""
        if orphan_hub not in needed_hubs:
            continue
        a_f = [padded[i].strip() if len(padded) > i else "" for i in range(14, 20)]
        if not a_f[1]:
            continue
        repairs.append((row_idx, a_f))
        messages.append(f"Repaired misplaced Hub Mapping row for '{orphan_hub}' (row {row_idx}).")

    if repairs and not dry_run:
        for row_idx, a_f in repairs:
            ws.update(range_name=f"A{row_idx}:F{row_idx}", values=[a_f], value_input_option="RAW")

    return messages


def normalize_hub_changes_df(df: pd.DataFrame) -> pd.DataFrame:
    """Align column names to canonical HUB_CHANGES_COLUMNS."""
    if df is None or df.empty:
        return pd.DataFrame(columns=HUB_CHANGES_COLUMNS)

    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    rename_map: dict[str, str] = {}
    for canonical in HUB_CHANGES_COLUMNS:
        match = _find_header(out.columns.tolist(), [canonical, canonical.replace("_", " ")])
        if match and match != canonical:
            rename_map[match] = canonical
    if rename_map:
        out = out.rename(columns=rename_map)

    for col in HUB_CHANGES_COLUMNS:
        if col not in out.columns:
            out[col] = ""

    out = out[HUB_CHANGES_COLUMNS]
    out = out[out.astype(str).apply(lambda r: any(v.strip() for v in r), axis=1)].reset_index(drop=True)
    if "add_hub_mapping" in out.columns:
        out["add_hub_mapping"] = out["add_hub_mapping"].apply(
            lambda v: "TRUE" if parse_add_hub_mapping_cell(v) else "FALSE"
        )
    return out


def extract_hub_launch_mappings(hub_changes_df: pd.DataFrame) -> list[HubLaunchMapping]:
    """New Hub rows with optional product_ids / add_hub_mapping from Pipeline Params UI."""
    df = normalize_hub_changes_df(hub_changes_df)
    if df.empty:
        return []

    mappings: list[HubLaunchMapping] = []
    seen: set[str] = set()
    new_hub_mask = df["Type"].astype(str).str.strip() == "New Hub"
    for row in df.loc[new_hub_mask].itertuples(index=False):
        new_hub = str(getattr(row, "Hub_name", "")).strip()
        source_hub = str(getattr(row, "Source_Hub", "")).strip()
        if not new_hub or not source_hub or new_hub in seen:
            continue
        seen.add(new_hub)
        product_ids_val = getattr(row, "product_ids", "")
        add_hub_val = getattr(row, "add_hub_mapping", "TRUE")
        mappings.append(HubLaunchMapping(
            new_hub=new_hub,
            source_hub=source_hub,
            product_ids=parse_product_ids_cell(product_ids_val),
            add_hub_mapping=parse_add_hub_mapping_cell(add_hub_val),
            city_name=str(getattr(row, "city_name", "")).strip(),
            hub_id=str(getattr(row, "Hub_id", "")).strip(),
        ))
    return mappings


def extract_new_hub_ph_mappings(hub_changes_df: pd.DataFrame) -> list[tuple[str, str]]:
    """Backward-compatible (new_hub, source_hub) pairs."""
    return [(m.new_hub, m.source_hub) for m in extract_hub_launch_mappings(hub_changes_df)]


def update_hub_changes_row_fields(
    sheets_manager,
    hub_name: str,
    *,
    product_ids: Sequence[str] | None = None,
    add_hub_mapping: bool | None = None,
) -> bool:
    """Persist manual UI fields for one hub back to Pipeline Params Hub_Changes tab."""
    df = normalize_hub_changes_df(sheets_manager.read_hub_changes_table(seed_from_legacy=False))
    if df.empty or "Hub_name" not in df.columns:
        return False

    hub_col = "Hub_name"
    mask = _col_series(df, hub_col).astype(str).str.strip() == hub_name.strip()
    if not mask.any():
        return False

    if product_ids is not None:
        df.loc[mask, "product_ids"] = ",".join(p.strip() for p in product_ids if p.strip())
    if add_hub_mapping is not None:
        df.loc[mask, "add_hub_mapping"] = "TRUE" if add_hub_mapping else "FALSE"

    return sheets_manager.write_hub_changes_to_pipeline_params(df)


def load_hub_changes_for_baseline(sheets_manager) -> pd.DataFrame:
    """Load hub changes for the baseline engine (pipeline params tab, legacy fallback)."""
    raw = sheets_manager.read_hub_changes_table()
    return normalize_hub_changes_df(raw)


def validate_hub_mapping_rows(hub_mapping_df: pd.DataFrame, new_hubs: Sequence[str]) -> list[str]:
    """Ensure each new hub exists in Hub Mapping with required fields populated."""
    if hub_mapping_df is None or hub_mapping_df.empty:
        return [f"Hub Mapping is empty; cannot validate new hub '{h}'." for h in new_hubs]

    hub_mapping_df = _dedupe_columns(hub_mapping_df)
    headers = [str(c).strip() for c in hub_mapping_df.columns]
    hub_col = _find_header(headers, ["hub_name", "Hub Name", "hub"])
    if not hub_col:
        return ["Hub Mapping missing hub_name column."]

    required = [h for h in headers if _normalize(h) in {_normalize(c) for c in HUB_MAPPING_REQUIRED}]
    names = _col_series(hub_mapping_df, hub_col).astype(str).str.strip()
    by_hub: dict[str, dict] = {}
    for idx, name in names.items():
        if name:
            by_hub[name] = hub_mapping_df.loc[idx].to_dict()

    errors: list[str] = []
    city_name_col = _find_header(headers, ["city_name", "City Name", "city"])
    optional_blank = {_normalize("hub_id"), _normalize("city_id")}
    for hub in new_hubs:
        row = by_hub.get(hub)
        if row is None:
            errors.append(f"Hub Mapping missing row for new hub '{hub}'.")
            continue
        for col in required:
            if str(row.get(col, "")).strip():
                continue
            ncol = _normalize(col)
            if ncol in optional_blank:
                if ncol == _normalize("city_id") and city_name_col and str(row.get(city_name_col, "")).strip():
                    continue
                if ncol == _normalize("hub_id"):
                    continue
            errors.append(f"Hub Mapping row for '{hub}' has blank '{col}'.")
    return errors


def _apply_hub_changes_to_mapping_row(
    new_row: dict[str, Any],
    headers: list[str],
    h_hub_col: str,
    mapping: HubLaunchMapping,
) -> dict[str, Any]:
    """Apply Hub_Changes fields onto a Hub Mapping row (matches legacy Master Data UI)."""
    new_row[h_hub_col] = mapping.new_hub
    city_col = _find_header(headers, ["city_name", "City Name", "city"])
    if city_col and mapping.city_name:
        new_row[city_col] = mapping.city_name
    hub_id_col = _find_header(headers, ["Hub_id", "hub_id", "Hub ID"])
    if hub_id_col and mapping.hub_id:
        new_row[hub_id_col] = mapping.hub_id
    active_col = _find_header(
        headers, ["Hub_active", "hub_active", "Hub Active", "Hub_active (A?)"],
    )
    if active_col:
        new_row[active_col] = "A"
    return new_row


def _build_new_hub_mapping_row(
    mapping: HubLaunchMapping,
    headers: list[str],
    h_hub_col: str,
    hub_mapping_df: pd.DataFrame,
    hub_series: pd.Series,
) -> tuple[dict[str, Any], str]:
    """
    Build a Hub Mapping row for a new hub.

    Matches master_data.py: clone from Source_Hub when present, else blank template
    filled from Hub_Changes (city_name, Hub_id).
    """
    src_rows = (
        hub_mapping_df[hub_series == mapping.source_hub]
        if mapping.source_hub
        else hub_mapping_df.iloc[0:0]
    )
    if not src_rows.empty:
        new_row = src_rows.iloc[0].to_dict()
        note = f"cloned Hub Mapping from source '{mapping.source_hub}'"
    else:
        new_row = {h: "" for h in headers}
        note = (
            f"new Hub Mapping row from Hub_Changes"
            f" (source '{mapping.source_hub}' not in sheet)"
        )
        city_col = _find_header(headers, ["city_name", "City Name", "city"])
        city_id_col = _find_header(headers, ["city_id", "City_id", "City ID"])
        if city_col and city_id_col and mapping.city_name:
            peer_city = _col_series(hub_mapping_df, city_col).astype(str).str.strip()
            peers = hub_mapping_df[peer_city == mapping.city_name]
            if not peers.empty:
                new_row[city_id_col] = str(peers.iloc[0].get(city_id_col, "")).strip()
    return _apply_hub_changes_to_mapping_row(new_row, headers, h_hub_col, mapping), note


def ensure_hub_mapping_rows(
    sheets_manager,
    mappings: Sequence[HubLaunchMapping],
    *,
    dry_run: bool = False,
) -> tuple[list[str], pd.DataFrame | None]:
    """Append Hub Mapping rows for new hubs when add_hub_mapping=TRUE and row is missing."""
    messages: list[str] = []
    to_add = [m for m in mappings if m.add_hub_mapping]
    if not to_add:
        return messages, None

    needed = {m.new_hub for m in to_add}
    messages.extend(_repair_misplaced_hub_mapping_rows(
        sheets_manager, needed, dry_run=dry_run,
    ))

    hub_mapping_df = _read_hub_mapping_df(sheets_manager)
    if hub_mapping_df is None or hub_mapping_df.empty:
        return [f"Hub Mapping empty; cannot add {m.new_hub}" for m in to_add], None

    headers = list(hub_mapping_df.columns)
    h_hub_col = _find_header(headers, ["hub_name", "Hub Name", "hub"])
    if not h_hub_col:
        return ["Hub Mapping missing hub_name column."], hub_mapping_df

    hm_ws_name = SHEETS_CONFIG["demand_planning_masters"]["worksheets"]["hub_mapping"]
    hub_ws = sheets_manager._get_worksheet_quiet("demand_planning_masters", hm_ws_name)
    if hub_ws is None:
        return ["Hub Mapping worksheet not found."], hub_mapping_df

    existing = set(_col_series(hub_mapping_df, h_hub_col).astype(str).str.strip())
    inserts: list[list[str]] = []
    pending_rows: list[dict[str, Any]] = []
    hub_series = _col_series(hub_mapping_df, h_hub_col).astype(str).str.strip()

    for m in to_add:
        if m.new_hub in existing:
            messages.append(f"Hub Mapping already has '{m.new_hub}' — skipped.")
            continue
        new_row, note = _build_new_hub_mapping_row(m, headers, h_hub_col, hub_mapping_df, hub_series)
        inserts.append([str(new_row.get(h, "")) for h in headers])
        pending_rows.append(new_row)
        existing.add(m.new_hub)
        messages.append(f"Hub Mapping row prepared for '{m.new_hub}' ({note}).")

    if inserts and not dry_run:
        sheets_manager.append_rows_to_worksheet(
            "demand_planning_masters",
            "hub_mapping",
            inserts,
            worksheet=hub_ws,
            value_input_option="RAW",
        )
        messages.append(f"Appended {len(inserts)} row(s) to Hub Mapping.")

    if pending_rows:
        hub_mapping_df = pd.concat(
            [hub_mapping_df, pd.DataFrame(pending_rows, columns=headers)],
            ignore_index=True,
        )

    return messages, hub_mapping_df


def _build_column_mapping(target_headers: Sequence[str], source_headers: Sequence[str]) -> dict[str, str]:
    source_lookup = {_normalize(h): h for h in source_headers}
    mapping: dict[str, str] = {}
    for th in target_headers:
        match = source_lookup.get(_normalize(th))
        if match:
            mapping[th] = match
    return mapping


def _build_key(row: dict[str, Any], key_columns: Sequence[str]) -> tuple[str, ...]:
    return tuple(str(row.get(c, "")).strip() for c in key_columns)


@dataclass
class HubPhCloneResult:
    mappings_processed: int = 0
    rows_inserted: int = 0
    duplicates_skipped: int = 0
    mapping_report: list[dict[str, Any]] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.validation_errors


def clone_ph_master_from_hub_mappings(
    sheets_manager,
    mappings: Sequence[HubLaunchMapping] | Sequence[tuple[str, str]],
    *,
    key_columns: Sequence[str] | None = None,
    dry_run: bool = False,
) -> HubPhCloneResult:
    """
    Clone P-H Master rows from source_hub → new_hub for each mapping pair.
    Appends new rows to Demand Planning Masters → P-H Master tab.
    """
    result = HubPhCloneResult()
    if not mappings:
        return result

    launch_mappings: list[HubLaunchMapping] = []
    for m in mappings:
        if isinstance(m, HubLaunchMapping):
            launch_mappings.append(m)
        else:
            launch_mappings.append(HubLaunchMapping(new_hub=m[0], source_hub=m[1]))

    key_columns = list(key_columns or PH_KEY_COLUMNS)
    dpm_tabs = SHEETS_CONFIG["demand_planning_masters"]["worksheets"]
    ph_ws_name = dpm_tabs["product_hub_master"]

    # 1) Add missing Hub Mapping rows first (legacy Master Data order).
    hm_msgs, hub_mapping_df = ensure_hub_mapping_rows(
        sheets_manager, launch_mappings, dry_run=dry_run,
    )
    for msg in hm_msgs:
        result.mapping_report.append({"hub_mapping": msg})

    ph_ws = sheets_manager._get_worksheet_quiet("demand_planning_masters", ph_ws_name)
    if ph_ws is None:
        result.validation_errors.append("P-H Master worksheet not found.")
        return result

    if hub_mapping_df is None:
        hub_mapping_df = _read_hub_mapping_df(sheets_manager)

    ph_data = ph_ws.get_all_values()
    if not ph_data:
        result.validation_errors.append("P-H Master worksheet is empty.")
        return result

    ph_headers = [str(h).strip() for h in ph_data[0]]
    ph_records = [
        {ph_headers[i]: (row[i] if i < len(row) else "") for i in range(len(ph_headers))}
        for row in ph_data[1:]
    ]

    hub_col = _find_header(ph_headers, ["hub_name", "Hub Name", "hub"])
    if not hub_col:
        result.validation_errors.append("P-H Master missing hub_name column.")
        return result

    hub_headers = list(hub_mapping_df.columns) if hub_mapping_df is not None else []
    h_hub_col = _find_header(hub_headers, ["hub_name", "Hub Name", "hub"]) if hub_headers else None
    h_col_map = _build_column_mapping(ph_headers, hub_headers) if hub_headers else {}
    hub_lookup: dict[str, dict[str, Any]] = {}
    if h_hub_col and hub_mapping_df is not None:
        hm_names = _col_series(hub_mapping_df, h_hub_col).astype(str).str.strip()
        for idx, name in hm_names.items():
            if name:
                hub_lookup[name] = hub_mapping_df.loc[idx].to_dict()

    new_hubs = sorted({m.new_hub for m in launch_mappings})
    result.validation_errors = validate_hub_mapping_rows(hub_mapping_df, new_hubs)
    if result.validation_errors:
        return result

    pid_col = _find_header(ph_headers, PRODUCT_ID_HEADER_CANDIDATES)
    key_cols = [_find_header(ph_headers, [k, k.replace("_", " ")]) or k for k in key_columns]
    key_cols = [c for c in key_cols if c in ph_headers]

    ph_df = pd.DataFrame(ph_records)
    if ph_df.empty:
        result.validation_errors.append("P-H Master has no data rows.")
        return result

    for c in key_cols:
        ph_df[c] = ph_df[c].astype(str).str.strip()
    existing_keys = set(map(tuple, ph_df[key_cols].values.tolist()))
    inserts: list[list[str]] = []

    for cfg in launch_mappings:
        new_hub, source_hub = cfg.new_hub, cfg.source_hub
        source_mask = ph_df[hub_col].astype(str).str.strip() == source_hub
        if cfg.product_ids and pid_col:
            allowed = {p.strip() for p in cfg.product_ids}
            source_mask &= ph_df[pid_col].astype(str).str.strip().isin(allowed)
        source_df = ph_df.loc[source_mask].copy()
        if source_df.empty:
            result.mapping_report.append({
                "new_hub": new_hub,
                "source_hub": source_hub,
                "status": "error",
                "message": "Source hub has no matching rows in P-H Master"
                + (f" (product_ids filter: {','.join(cfg.product_ids)})" if cfg.product_ids else ""),
            })
            continue

        cloned_df = source_df.copy()
        new_hub_data = hub_lookup.get(new_hub, {})
        if new_hub_data and h_col_map:
            for ph_col, h_col in h_col_map.items():
                if h_col in new_hub_data and ph_col in cloned_df.columns:
                    cloned_df[ph_col] = str(new_hub_data.get(h_col, "")).strip()
        cloned_df[hub_col] = new_hub

        new_keys = list(map(tuple, cloned_df[key_cols].values.tolist()))
        dup_mask = [k in existing_keys for k in new_keys]
        inserted = sum(1 for d in dup_mask if not d)
        skipped = sum(dup_mask)
        result.duplicates_skipped += skipped

        for k, is_dup in zip(new_keys, dup_mask):
            if not is_dup:
                existing_keys.add(k)

        to_write = cloned_df.loc[[not d for d in dup_mask]]
        if not to_write.empty:
            inserts.extend(
                to_write.reindex(columns=ph_headers, fill_value="")
                .fillna("")
                .astype(str)
                .values.tolist()
            )

        result.mapping_report.append({
            "new_hub": new_hub,
            "source_hub": source_hub,
            "status": "ok",
            "rows_inserted": inserted,
            "duplicates_skipped": skipped,
            "product_ids_filter": ",".join(cfg.product_ids) if cfg.product_ids else "(all)",
        })

    result.mappings_processed = len(launch_mappings)
    result.rows_inserted = len(inserts)

    if inserts and not dry_run:
        GoogleSheetsManager.batch_append_rows(ph_ws, inserts, value_input_option="RAW")

    return result
