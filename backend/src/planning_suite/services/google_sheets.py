"""
Google Sheets utilities for data sync
"""
import os
from pathlib import Path

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from planning_suite.config import (
    DP_LOGICS_SHEET_URL,
    GOOGLE_CREDENTIALS_PATH,
    HUB_CHANGES_COLUMNS,
    PIPELINE_PARAMS_HUB_CHANGES_TAB,
    PIPELINE_PARAMS_SHEET_URL,
    PIPELINE_PARAMS_VARIABLES_TAB,
    SHEETS_CONFIG,
)
from planning_suite.services.baseline_io import write_dp_logics_parquet_sidecar
from planning_suite.core.dataframe import clean_sheet_df

DP_LOGICS_WORKSHEETS = {
    "City_Cat": ("hub_level_planning", "outlier"),
    "SellThroughFactor": ("hub_level_planning", "sell_through"),
    "City_drops": ("hub_level_planning", "city_drops"),
    "Percentile": ("hub_level_planning", "percentile"),
    "Avl_Flag": ("hub_level_planning", "avl_flag"),
}


def _normalize_header(text: str) -> str:
    return "".join(ch.lower() for ch in str(text).strip() if ch.isalnum())


class GoogleSheetsManager:
    """Manages Google Sheets connections and data sync"""
    
    def __init__(self):
        self.client = self._initialize_client()

    @property
    def gc(self):
        """Alias for the gspread client (used by legacy call sites)."""
        if not self.client:
            self.client = self._initialize_client()
        return self.client
    
    
    def _initialize_client(_self):
        """Initialize Google Sheets client"""
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                GOOGLE_CREDENTIALS_PATH, scope
            )
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Failed to initialize Google Sheets client: {e}")
            return None
    
    def get_worksheet(self, sheet_category, worksheet_name):
        """Get specific worksheet from configured sheets"""
        try:
            return self._get_worksheet_quiet(sheet_category, worksheet_name)
        except Exception as e:
            print(f"Error accessing worksheet {worksheet_name}: {e}")
            return None

    def _get_worksheet_quiet(self, sheet_category, worksheet_name):
        """Get worksheet without surfacing Streamlit errors (for fallback chains)."""
        if not self.client:
            self.client = self._initialize_client()
        if not self.client:
            return None

        sheet_config = SHEETS_CONFIG.get(sheet_category)
        if not sheet_config:
            return None

        spreadsheet = self.client.open_by_url(sheet_config["url"])
        return spreadsheet.worksheet(worksheet_name)

    def _worksheet_data_to_df(self, worksheet, range_notation="") -> pd.DataFrame | None:
        if not worksheet:
            return None
        if range_notation:
            data = worksheet.get(range_notation)
        else:
            data = worksheet.get_all_values()
        if not data or len(data) < 2:
            return pd.DataFrame()
        return pd.DataFrame(data[1:], columns=data[0])

    def read_worksheet_uncached(
        self, sheet_category, worksheet_key, range_notation="", *, use_cache: bool = True
    ) -> pd.DataFrame | None:
        """Fresh worksheet read (optional TTL parquet cache)."""
        from planning_suite.services import sheets_cache

        if use_cache:
            path = sheets_cache.cache_path_for_category(
                sheet_category, worksheet_key, range_notation,
            )
            ttl = sheets_cache.ttl_for_worksheet(worksheet_key, sheet_category)
            cached = sheets_cache.get_cached_df(path, ttl)
            if cached is not None:
                return cached

        try:
            sheet_config = SHEETS_CONFIG.get(sheet_category)
            if not sheet_config:
                return None
            worksheet_name = sheet_config["worksheets"].get(worksheet_key, worksheet_key)
            from planning_suite.services.sheets_throttle import sheets_slot

            with sheets_slot():
                worksheet = self._get_worksheet_quiet(sheet_category, worksheet_name)
                df = self._worksheet_data_to_df(worksheet, range_notation)
            if use_cache and df is not None and not df.empty:
                path = sheets_cache.cache_path_for_category(
                    sheet_category, worksheet_key, range_notation,
                )
                sheets_cache.store_cached_df(path, clean_sheet_df(df))
            return df
        except Exception:
            return None
    
    
    def read_worksheet_to_df(_self, sheet_category, worksheet_key, range_notation=""):
        """Read worksheet data into pandas DataFrame"""
        try:
            df = _self.read_worksheet_uncached(sheet_category, worksheet_key, range_notation)
            if df is None:
                sheet_config = SHEETS_CONFIG.get(sheet_category)
                worksheet_name = (
                    sheet_config["worksheets"].get(worksheet_key, worksheet_key)
                    if sheet_config
                    else worksheet_key
                )
                print(f"Error reading worksheet {worksheet_name}")
            return df
        except Exception as e:
            print(f"Error reading worksheet {worksheet_key}: {e}")
            return None

    @staticmethod
    def _persist_dp_logics_table(df: pd.DataFrame, save_path: str) -> None:
        df.to_excel(save_path, index=False)
        try:
            write_dp_logics_parquet_sidecar(df, save_path)
        except Exception:
            pass
        if Path(save_path).name.lower().startswith("percentile"):
            try:
                from planning_suite.services.baseline_io import write_percentile_engine_sidecars
                write_percentile_engine_sidecars(Path(save_path).parent, df)
            except Exception:
                pass

    def sync_dp_logics_worksheets_to_folder(
        self,
        output_folder: str,
        worksheet_names: list[str] | None = None,
        *,
        allow_local_fallback: bool = True,
        parallel: bool = True,
        max_local_age_hours: float | None = None,
    ) -> dict[str, dict]:
        """
        Save DP Logics worksheets as local Excel files.

        Tries hub_level_planning config, then DP_LOGICS_SHEET_URL, then existing
        local files when allow_local_fallback is True.
        When parallel=True (default), fetches all worksheets in one batch API call.
        """
        worksheet_names = worksheet_names or list(DP_LOGICS_WORKSHEETS.keys())
        os.makedirs(output_folder, exist_ok=True)

        if max_local_age_hours is not None and max_local_age_hours > 0:
            fresh = self._dp_logics_local_fresh(output_folder, worksheet_names, max_local_age_hours)
            if fresh is not None:
                return fresh

        if parallel:
            try:
                return self._sync_dp_logics_parallel(
                    output_folder,
                    worksheet_names,
                    allow_local_fallback=allow_local_fallback,
                )
            except Exception:
                pass

        return self._sync_dp_logics_sequential(
            output_folder,
            worksheet_names,
            allow_local_fallback=allow_local_fallback,
        )

    @staticmethod
    def _dp_logics_local_fresh(
        output_folder: str,
        worksheet_names: list[str],
        max_age_hours: float,
    ) -> dict[str, dict] | None:
        """Return sidecar refresh result if all local xlsx files are younger than max_age_hours."""
        import time

        now = time.time()
        max_age_sec = max_age_hours * 3600
        results: dict[str, dict] = {}
        for ws_name in worksheet_names:
            save_path = os.path.join(output_folder, f"{ws_name}.xlsx")
            if not os.path.isfile(save_path):
                return None
            age = now - os.path.getmtime(save_path)
            if age > max_age_sec:
                return None
            try:
                df = pd.read_excel(save_path)
                if df.empty:
                    return None
                try:
                    write_dp_logics_parquet_sidecar(df, save_path)
                except Exception:
                    pass
                results[ws_name] = {
                    "status": "local",
                    "rows": len(df),
                    "source": "local_fresh",
                }
            except Exception:
                return None
        return results

    def _sync_dp_logics_parallel(
        self,
        output_folder: str,
        worksheet_names: list[str],
        *,
        allow_local_fallback: bool,
    ) -> dict[str, dict]:
        from planning_suite.config import HUB_LEVEL_PLANNING_SHEET_KEY, SHEETS_CONFIG

        ws_config = SHEETS_CONFIG["hub_level_planning"]["worksheets"]
        specs: list[tuple[str, str]] = []
        name_by_tab: dict[str, str] = {}
        for ws_name in worksheet_names:
            mapping = DP_LOGICS_WORKSHEETS.get(ws_name)
            if not mapping:
                continue
            _category, key = mapping
            tab_name = ws_config.get(key, key)
            specs.append((tab_name, ""))
            name_by_tab[tab_name] = ws_name

        raw = self.batch_read_worksheets(
            HUB_LEVEL_PLANNING_SHEET_KEY,
            specs,
            max_workers=len(specs) or 1,
        )

        results: dict[str, dict] = {}
        missing: list[str] = []
        for tab_name, ws_name in name_by_tab.items():
            save_path = os.path.join(output_folder, f"{ws_name}.xlsx")
            data = raw.get(tab_name) or []
            if not data or len(data) < 2:
                missing.append(ws_name)
                continue
            df = clean_sheet_df(pd.DataFrame(data[1:], columns=data[0]))
            if df.empty:
                missing.append(ws_name)
                continue
            self._persist_dp_logics_table(df, save_path)
            results[ws_name] = {
                "status": "synced",
                "rows": len(df),
                "source": "google_sheets_batch",
            }

        for ws_name in worksheet_names:
            if ws_name in results:
                continue
            save_path = os.path.join(output_folder, f"{ws_name}.xlsx")
            synced = False
            if allow_local_fallback and os.path.exists(save_path):
                try:
                    df = pd.read_excel(save_path)
                    if not df.empty:
                        try:
                            write_dp_logics_parquet_sidecar(df, save_path)
                        except Exception:
                            pass
                        results[ws_name] = {
                            "status": "local",
                            "rows": len(df),
                            "source": "local_cache",
                        }
                        synced = True
                except Exception:
                    pass
            if not synced:
                missing.append(ws_name)
                results[ws_name] = {"status": "missing", "rows": 0, "source": ""}

        if missing:
            raise FileNotFoundError(
                "Could not sync or find local copies of: "
                f"{', '.join(sorted(set(missing)))}. "
                "Use **Configure Parameters → Sync All** when Sheets is available, "
                "or ensure files exist in the DP Logics folder."
            )
        return results

    def _sync_dp_logics_sequential(
        self,
        output_folder: str,
        worksheet_names: list[str],
        *,
        allow_local_fallback: bool,
    ) -> dict[str, dict]:
        results: dict[str, dict] = {}
        missing: list[str] = []

        for ws_name in worksheet_names:
            save_path = os.path.join(output_folder, f"{ws_name}.xlsx")
            synced = False

            mapping = DP_LOGICS_WORKSHEETS.get(ws_name)
            if mapping:
                category, key = mapping
                df = self.read_worksheet_uncached(category, key)
                if df is not None and not df.empty:
                    self._persist_dp_logics_table(df, save_path)
                    results[ws_name] = {
                        "status": "synced",
                        "rows": len(df),
                        "source": "google_sheets",
                    }
                    synced = True

            if not synced:
                try:
                    ws = self.gc.open_by_url(DP_LOGICS_SHEET_URL).worksheet(ws_name)
                    df = self._worksheet_data_to_df(ws)
                    if df is not None and not df.empty:
                        self._persist_dp_logics_table(df, save_path)
                        results[ws_name] = {
                            "status": "synced",
                            "rows": len(df),
                            "source": "dp_logics_url",
                        }
                        synced = True
                except Exception:
                    pass

            if not synced and allow_local_fallback and os.path.exists(save_path):
                try:
                    df = pd.read_excel(save_path)
                    if not df.empty:
                        try:
                            write_dp_logics_parquet_sidecar(df, save_path)
                        except Exception:
                            pass
                        results[ws_name] = {
                            "status": "local",
                            "rows": len(df),
                            "source": "local_cache",
                        }
                        synced = True
                except Exception:
                    pass

            if not synced:
                missing.append(ws_name)
                results[ws_name] = {"status": "missing", "rows": 0, "source": ""}

        if missing:
            raise FileNotFoundError(
                "Could not sync or find local copies of: "
                f"{', '.join(missing)}. "
                "Use **Configure Parameters → Sync All** when Sheets is available, "
                "or ensure files exist in the DP Logics folder."
            )
        return results
    
    def write_df_to_worksheet(
        self, sheet_category, worksheet_key, df, clear_first=True, *, quiet: bool = False
    ):
        """Write DataFrame to worksheet"""
        try:
            sheet_config = SHEETS_CONFIG.get(sheet_category)
            if not sheet_config:
                if not quiet:
                    print(f"Unknown sheet category: {sheet_category}")
                return False

            worksheet_name = sheet_config["worksheets"].get(worksheet_key, worksheet_key)
            worksheet = self.get_worksheet(sheet_category, worksheet_name)
            if not worksheet:
                return False

            if clear_first:
                worksheet.clear()

            data = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
            worksheet.update("A1", data, value_input_option="RAW")
            return True
        except Exception as e:
            if not quiet:
                print(f"Error writing to worksheet {worksheet_name if 'worksheet_name' in locals() else worksheet_key}: {e}")
            return False

    def append_row_to_worksheet(self, sheet_category, worksheet_key, row_values, worksheet=None):
        """Append one row to a worksheet."""
        sheet_config = SHEETS_CONFIG.get(sheet_category)
        if not sheet_config:
            print(f"Unknown sheet category: {sheet_category}")
            return False
        ws = worksheet or self.get_worksheet(
            sheet_category,
            sheet_config["worksheets"].get(worksheet_key, worksheet_key),
        )
        if not ws:
            return False
        ws.append_row(row_values)
        return True

    def append_rows_to_worksheet(
        self, sheet_category, worksheet_key, rows, worksheet=None, value_input_option="RAW"
    ):
        """Append multiple rows to a worksheet (chunked batch append)."""
        sheet_config = SHEETS_CONFIG.get(sheet_category)
        if not sheet_config:
            print(f"Unknown sheet category: {sheet_category}")
            return False
        ws = worksheet or self.get_worksheet(
            sheet_category,
            sheet_config["worksheets"].get(worksheet_key, worksheet_key),
        )
        if not ws:
            return False
        return self.batch_append_rows(ws, rows, value_input_option=value_input_option)

    @staticmethod
    def batch_append_rows(worksheet, rows, *, value_input_option: str = "RAW", chunk_size: int = 5000) -> bool:
        """Append many rows in chunked API calls (replaces per-row append_row loops)."""
        if not rows:
            return True
        for start in range(0, len(rows), chunk_size):
            chunk = rows[start : start + chunk_size]
            worksheet.append_rows(chunk, value_input_option=value_input_option)
        return True

    def batch_read_worksheets(
        self,
        spreadsheet_key: str,
        worksheets: list[tuple[str, str]],
        *,
        max_workers: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, list]:
        """
        Fetch multiple worksheets from one spreadsheet in parallel.

        Each item in ``worksheets`` is ``(worksheet_name, range_notation)``;
        use ``""`` for ``get_all_values()``.
        When ``use_cache=True``, fresh reads are stored under ``outputs/sheets_cache/``.
        """
        from planning_suite.services import sheets_cache

        if use_cache:
            cached: dict[str, list] = {}
            to_fetch: list[tuple[str, str]] = []
            for name, range_notation in worksheets:
                path = sheets_cache.cache_path(spreadsheet_key, name, range_notation)
                ttl = sheets_cache.ttl_for_worksheet(name)
                df = sheets_cache.get_cached_df(path, ttl)
                if df is not None:
                    if df.empty:
                        cached[name] = []
                    else:
                        cols = df.columns.tolist()
                        cached[name] = [cols] + df.astype(str).where(df.notna(), "").values.tolist()
                else:
                    to_fetch.append((name, range_notation))
            if not to_fetch:
                return cached
            fresh = self._batch_fetch_worksheets(spreadsheet_key, to_fetch, max_workers=max_workers)
            for name, data in fresh.items():
                cached[name] = data
                df = sheets_cache.raw_to_df(data)
                if not df.empty:
                    spec = next((s for s in to_fetch if s[0] == name), None)
                    rng = spec[1] if spec else ""
                    sheets_cache.store_cached_df(
                        sheets_cache.cache_path(spreadsheet_key, name, rng),
                        df,
                    )
            return cached

        return self._batch_fetch_worksheets(spreadsheet_key, worksheets, max_workers=max_workers)

    def _batch_fetch_worksheets(
        self,
        spreadsheet_key: str,
        worksheets: list[tuple[str, str]],
        *,
        max_workers: int | None = None,
    ) -> dict[str, list]:
        from concurrent.futures import ThreadPoolExecutor
        from planning_suite.services.sheets_throttle import in_pipeline_mode

        if not self.client:
            self.client = self._initialize_client()
        if not self.client:
            return {}

        if not worksheets:
            return {}

        # One API round-trip for all ranges — much faster than N parallel get_all_values.
        if in_pipeline_mode() and len(worksheets) > 1:
            try:
                return self._batch_fetch_via_values_batch_get(spreadsheet_key, worksheets)
            except Exception:
                pass

        spreadsheet = self.client.open_by_key(spreadsheet_key)
        workers = max_workers or len(worksheets) or 1

        def _fetch(spec: tuple[str, str]) -> tuple[str, list]:
            name, range_notation = spec
            ws = spreadsheet.worksheet(name)
            if range_notation:
                data = ws.get(range_notation)
            else:
                data = ws.get_all_values()
            return name, data or []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            return dict(executor.map(_fetch, worksheets))

    def _batch_fetch_via_values_batch_get(
        self,
        spreadsheet_key: str,
        worksheets: list[tuple[str, str]],
    ) -> dict[str, list]:
        """Fetch multiple worksheet ranges in a single Sheets API batchGet call."""
        spreadsheet = self.client.open_by_key(spreadsheet_key)
        range_specs: list[str] = []
        names: list[str] = []
        for name, range_notation in worksheets:
            quoted = name.replace("'", "''")
            if range_notation:
                range_specs.append(f"'{quoted}'!{range_notation}")
            else:
                range_specs.append(f"'{quoted}'")
            names.append(name)

        batch = spreadsheet.values_batch_get(range_specs)
        value_ranges = batch.get("valueRanges") or []
        out: dict[str, list] = {}
        for idx, name in enumerate(names):
            if idx < len(value_ranges):
                out[name] = value_ranges[idx].get("values") or []
            else:
                out[name] = []
        return out

    def read_demand_planning_masters_parallel(
        self,
        *,
        progress=None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Parallel read of P Master, HTT, Hub Mapping, P-H Master (pipeline + manual sync)."""
        from planning_suite.config import DEMAND_PLANNING_SHEET_ID
        from planning_suite.core.dataframe import clean_sheet_df
        from planning_suite.services.product_launch_sync import (
            HUB_MASTER_READ_RANGE,
            P_MASTER_READ_RANGE,
            PH_MASTER_READ_RANGE,
        )

        specs = [
            ("P Master", P_MASTER_READ_RANGE),
            ("HTT Mapping", ""),
            ("Hub Mapping", HUB_MASTER_READ_RANGE),
            ("P-H Master", PH_MASTER_READ_RANGE),
        ]
        if progress:
            progress("Reading masters in parallel…", 0.15)

        raw = self.batch_read_worksheets(DEMAND_PLANNING_SHEET_ID, specs)

        def _to_df(name: str) -> pd.DataFrame:
            data = raw.get(name) or []
            if not data or len(data) < 2:
                return pd.DataFrame()
            return clean_sheet_df(pd.DataFrame(data[1:], columns=data[0]))

        return (
            _to_df("P Master"),
            _to_df("HTT Mapping"),
            _to_df("Hub Mapping"),
            _to_df("P-H Master"),
        )
    
    def sync_master_data(self, master_type):
        """Sync specific master data from Google Sheets"""
        master_configs = {
            "cluster_mapping": {
                "sheet_category": "cluster_master",
                "worksheet_key": "cluster_mapping"
            },
            "avl_flag": {
                "sheet_category": "hub_level_planning",
                "worksheet_key": "avl_flag"
            },
            "hub_changes": {
                "sheet_category": "pipeline_params",
                "worksheet_key": "hub_changes",
                "legacy_sheet_category": "new_hub_launch",
                "legacy_worksheet_key": "ff_input",
            },
            "outlier": {
                "sheet_category": "hub_level_planning",
                "worksheet_key": "outlier"
            },
            "city_drops": {
                "sheet_category": "hub_level_planning",
                "worksheet_key": "city_drops"
            },
            "percentile": {
                "sheet_category": "hub_level_planning",
                "worksheet_key": "percentile"
            },
            "hub_sku_master": {
                "sheet_category": "hub_level_planning",
                "worksheet_key": "hub_sku_master"
            },
            "sell_through": {
                "sheet_category": "hub_level_planning",
                "worksheet_key": "sell_through"
            },
            "product_master": {
                "sheet_category": "demand_planning_masters",
                "worksheet_key": "product_hub_master"
            }
        }
        
        config = master_configs.get(master_type)
        if not config:
            print(f"Unknown master type: {master_type}")
            return None

        if master_type == "hub_changes":
            return self.read_hub_changes_table()

        df = self.read_worksheet_to_df(
            config['sheet_category'],
            config['worksheet_key'],
            config.get('range', '')
        )
        
        return df
    
    def get_all_masters(self):
        """Get all master data in parallel using a ThreadPoolExecutor"""
        from concurrent.futures import ThreadPoolExecutor
        masters = {}
        master_types = [
            "product_master", "hub_changes", "outlier",
            "city_drops", "percentile", "sell_through",
            "cluster_mapping", "avl_flag", "hub_sku_master"
        ]
        
        def fetch_master(master_type):
            return master_type, self.sync_master_data(master_type)
            
        if True:
            with ThreadPoolExecutor(max_workers=len(master_types)) as executor:
                results = list(executor.map(fetch_master, master_types))
                
        for master_type, df in results:
            if df is not None:
                masters[master_type] = df
        return masters
    
    def _open_pipeline_params_spreadsheet(self):
        """Open the pipeline params spreadsheet (requires PIPELINE_PARAMS_SHEET_URL)."""
        if not PIPELINE_PARAMS_SHEET_URL:
            return None
        if not self.client:
            self.client = self._initialize_client()
        if not self.client:
            return None
        return self.client.open_by_url(PIPELINE_PARAMS_SHEET_URL)

    def _get_pipeline_params_worksheet(self, tab_name: str, *, fallback_index: int | None = 0):
        spreadsheet = self._open_pipeline_params_spreadsheet()
        if not spreadsheet:
            return None
        try:
            return spreadsheet.worksheet(tab_name)
        except Exception:
            if fallback_index is not None:
                return spreadsheet.get_worksheet(fallback_index)
            return None

    def ensure_pipeline_params_hub_changes_tab(self):
        """Create Hub_Changes tab on pipeline params sheet with canonical headers if missing."""
        spreadsheet = self._open_pipeline_params_spreadsheet()
        if not spreadsheet:
            return None
        try:
            ws = spreadsheet.worksheet(PIPELINE_PARAMS_HUB_CHANGES_TAB)
        except Exception:
            ws = spreadsheet.add_worksheet(
                title=PIPELINE_PARAMS_HUB_CHANGES_TAB,
                rows=1000,
                cols=len(HUB_CHANGES_COLUMNS),
            )
            ws.update("A1", [HUB_CHANGES_COLUMNS])
            return ws

        headers = ws.row_values(1)
        if not headers:
            ws.update("A1", [HUB_CHANGES_COLUMNS])
        else:
            existing = {_normalize_header(h) for h in headers if h}
            missing = [c for c in HUB_CHANGES_COLUMNS if _normalize_header(c) not in existing]
            if missing or len(headers) < len(HUB_CHANGES_COLUMNS):
                ws.update("A1", [HUB_CHANGES_COLUMNS])
        return ws

    def read_hub_changes_table(self, *, seed_from_legacy: bool = True) -> pd.DataFrame:
        """
        Read hub changes from pipeline params Hub_Changes tab.
        Optionally one-time seed from legacy FF Input when the tab is empty.
        """
        from planning_suite.services.hub_launch_sync import normalize_hub_changes_df

        self.ensure_pipeline_params_hub_changes_tab()
        ws = self._get_pipeline_params_worksheet(PIPELINE_PARAMS_HUB_CHANGES_TAB, fallback_index=None)
        if not ws:
            return pd.DataFrame(columns=HUB_CHANGES_COLUMNS)

        df = self._worksheet_data_to_df(ws)
        normalized = normalize_hub_changes_df(df if df is not None else pd.DataFrame())
        if not normalized.empty or not seed_from_legacy:
            return normalized

        legacy = self.read_worksheet_uncached("new_hub_launch", "ff_input")
        if legacy is None or legacy.empty:
            return normalized

        seeded = normalize_hub_changes_df(legacy)
        if not seeded.empty:
            self.write_hub_changes_to_pipeline_params(seeded)
        return seeded

    def write_hub_changes_to_pipeline_params(self, df: pd.DataFrame) -> bool:
        """Write hub changes DataFrame to pipeline params Hub_Changes tab."""
        from planning_suite.services.hub_launch_sync import normalize_hub_changes_df

        try:
            ws = self.ensure_pipeline_params_hub_changes_tab()
            if not ws:
                return False

            df_to_write = normalize_hub_changes_df(df)
            for col in ["Start_date", "End_date"]:
                if col in df_to_write.columns:
                    df_to_write[col] = df_to_write[col].astype(str)
            if "Percentage" in df_to_write.columns:
                df_to_write["Percentage"] = pd.to_numeric(df_to_write["Percentage"], errors="coerce")

            ws.clear()
            data = [df_to_write.columns.tolist()] + df_to_write.values.tolist()
            ws.update("A1", data)
            return True
        except Exception as e:
            print(f"Error writing hub changes to pipeline params: {e}")
            return False

    def write_hub_changes(self, df):
        """
        Write hub changes DataFrame to pipeline params Hub_Changes tab
        (falls back to legacy FF Input when pipeline params URL is unset).
        """
        if PIPELINE_PARAMS_SHEET_URL:
            return self.write_hub_changes_to_pipeline_params(df)

        try:
            df_to_write = df.copy()
            for col in ["Start_date", "End_date"]:
                if col in df_to_write.columns:
                    df_to_write[col] = df_to_write[col].astype(str)
            if "Percentage" in df_to_write.columns:
                df_to_write["Percentage"] = pd.to_numeric(df_to_write["Percentage"], errors="coerce")

            return self.write_df_to_worksheet(
                sheet_category="new_hub_launch",
                worksheet_key="ff_input",
                df=df_to_write,
                clear_first=True,
            )
        except Exception as e:
            print(f"Error writing hub changes to Google Sheets: {str(e)}")
            return False

    def read_pipeline_params(self):
        """Read pipeline execution parameters from Google Sheet"""
        try:
            from planning_suite.config import PIPELINE_PARAMS_SHEET_URL
            if not PIPELINE_PARAMS_SHEET_URL:
                print("PIPELINE_PARAMS_SHEET_URL is not set in .env")
                return {}
                
            if not self.client:
                self.client = self._initialize_client()
            if not self.client:
                return {}
                
            spreadsheet = self.client.open_by_url(PIPELINE_PARAMS_SHEET_URL)
            worksheet = self._get_pipeline_params_worksheet(
                PIPELINE_PARAMS_VARIABLES_TAB, fallback_index=0
            )
            if not worksheet:
                return {}
            data = worksheet.get_all_values()
            
            if not data or len(data) < 2:
                return {}
                
            # Parse rows into key-value dictionary, casting types as appropriate
            params = {}
            headers = [h.strip().lower() for h in data[0]]
            
            # Find column indices
            try:
                name_idx = headers.index("variable name")
                val_idx = headers.index("value")
            except ValueError:
                name_idx = 0
                val_idx = 1
                
            type_idx = headers.index("data type") if "data type" in headers else None
            
            for row in data[1:]:
                if len(row) <= max(name_idx, val_idx):
                    continue
                var_name = row[name_idx].strip()
                if not var_name:
                    continue
                raw_val = row[val_idx].strip()
                
                # Determine data type
                data_type = "string"
                if type_idx is not None and len(row) > type_idx:
                    data_type = row[type_idx].strip().lower()
                else:
                    if raw_val.lower() in ("true", "yes", "y", "t"):
                        data_type = "boolean"
                    elif raw_val.lower() in ("false", "no", "n", "f"):
                        data_type = "boolean"
                    elif raw_val.isdigit():
                        data_type = "integer"
                    else:
                        try:
                            float(raw_val)
                            data_type = "float"
                        except ValueError:
                            pass
                            
                # Cast value
                if data_type == "boolean":
                    val = raw_val.lower() in ("true", "yes", "y", "t", "1")
                elif data_type in ("integer", "int"):
                    try:
                        val = int(raw_val)
                    except ValueError:
                        val = 0
                elif data_type in ("float", "double", "decimal"):
                    try:
                        val = float(raw_val)
                    except ValueError:
                        val = 0.0
                else:
                    val = raw_val
                    
                params[var_name] = val
                
            return params
        except Exception as e:
            print(f"Error reading pipeline parameters: {e}")
            return {}

    def write_pipeline_params(self, params_dict):
        """Write updated pipeline parameters back to the Google Sheet"""
        try:
            from planning_suite.config import PIPELINE_PARAMS_SHEET_URL
            if not PIPELINE_PARAMS_SHEET_URL:
                print("PIPELINE_PARAMS_SHEET_URL is not set in .env")
                return False
                
            if not self.client:
                self.client = self._initialize_client()
            if not self.client:
                return False
                
            spreadsheet = self.client.open_by_url(PIPELINE_PARAMS_SHEET_URL)
            worksheet = self._get_pipeline_params_worksheet(
                PIPELINE_PARAMS_VARIABLES_TAB, fallback_index=0
            )
            if not worksheet:
                return False
            data = worksheet.get_all_values()
            
            if not data or len(data) < 2:
                headers = ["Variable Name", "Value", "Data Type", "Notes"]
                rows = []
            else:
                headers = data[0]
                rows = data[1:]
                
            headers_lower = [h.strip().lower() for h in headers]
            try:
                name_idx = headers_lower.index("variable name")
                val_idx = headers_lower.index("value")
            except ValueError:
                name_idx = 0
                val_idx = 1
                
            updated_vars = set()
            for row in rows:
                if len(row) <= max(name_idx, val_idx):
                    continue
                var_name = row[name_idx].strip()
                if var_name in params_dict:
                    raw_val = params_dict[var_name]
                    if isinstance(raw_val, bool):
                        row[val_idx] = "TRUE" if raw_val else "FALSE"
                    else:
                        row[val_idx] = str(raw_val)
                    updated_vars.add(var_name)
                    
            for var_name, val in params_dict.items():
                if var_name not in updated_vars:
                    new_row = [""] * len(headers)
                    new_row[name_idx] = var_name
                    if isinstance(val, bool):
                        new_row[val_idx] = "TRUE" if val else "FALSE"
                    else:
                        new_row[val_idx] = str(val)
                    type_idx = None
                    for t_opt in ["data-type", "data type"]:
                        if t_opt in headers_lower:
                            type_idx = headers_lower.index(t_opt)
                            break
                    if type_idx is not None:
                        if isinstance(val, bool):
                            new_row[type_idx] = "boolean"
                        elif isinstance(val, int):
                            new_row[type_idx] = "integer"
                        elif isinstance(val, float):
                            new_row[type_idx] = "float"
                        else:
                            new_row[type_idx] = "string"
                    rows.append(new_row)
                    
            updated_data = [headers] + rows
            worksheet.clear()
            worksheet.update("A1", updated_data)
            return True
        except Exception as e:
            print(f"Error writing pipeline parameters: {e}")
            return False
