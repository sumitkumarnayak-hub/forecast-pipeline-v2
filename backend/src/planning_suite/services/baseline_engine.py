"""
Headless baseline engine — raw data fetch, RDS cache, previous baseline.

No Streamlit dependency. Used by FastAPI baseline routes and Auto-Pilot.
"""
from __future__ import annotations

import logging
import os
import time

import numpy as np
import pandas as pd
import pandera as pa
import polars as pl
import pyreadr
import trino
from pydantic import BaseModel, Field, field_validator

from planning_suite.config import (
    DP_LOGICS_FOLDER,
    FF_MASTERS_XLSX,
    OUTPUT_PATH,
    RDS_6W_PATH,
)
from planning_suite.core.dataframe import clean_sheet_df
from planning_suite.db.engine import Database
from planning_suite.services.analytics_6w import OUTPUT_RDS_CACHE, build_rds_parquet_cache
from planning_suite.services.baseline_io import P_MASTER_READ_RANGE, p_master_enrichment_maps
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.services.helpers import normalize_base_plan_columns
from planning_suite.services.sheets_session import get_sheets_manager

logger = logging.getLogger(__name__)

HUBS_TO_EXCLUDE = ["INDORE", "KKD", "RAIPUR", "NAGDRM", "VDR"]

RAW_DATA_COLUMNS_TO_KEEP = [
    "city_name",
    "product_id",
    "hub_name",
    "process_dt",
    "sales",
    "group_flag",
    "group_instances",
    "grp_r7_plan",
    "grp_r7_inv",
    "grp_r7_plan_rev",
    "grp_r7_inv_rev",
    "grp_BasePlan",
    "grp_BaseRev",
    "r7_plan",
    "r7_inv",
    "r7_plan_rev",
    "r7_inv_rev",
    "BasePlan",
    "flag",
    "instances",
]

RAW_DATA_SCHEMA = pa.DataFrameSchema(
    {
        "city_name": pa.Column(str, required=True),
        "product_id": pa.Column(required=True),
        "hub_name": pa.Column(str, required=True),
        "process_dt": pa.Column(pa.DateTime, required=True, coerce=True),
        "sales": pa.Column(required=True),
        "group_flag": pa.Column(required=True),
        "group_instances": pa.Column(required=True),
        "grp_r7_plan": pa.Column(required=True),
        "grp_r7_inv": pa.Column(required=True),
        "grp_r7_plan_rev": pa.Column(required=True),
        "grp_r7_inv_rev": pa.Column(required=True),
        "grp_BasePlan": pa.Column(required=True),
        "grp_BaseRev": pa.Column(required=True),
        "r7_plan": pa.Column(required=True),
        "r7_inv": pa.Column(required=True),
        "r7_plan_rev": pa.Column(required=True),
        "r7_inv_rev": pa.Column(required=True),
        "BasePlan": pa.Column(required=True),
        "flag": pa.Column(required=True),
        "instances": pa.Column(required=True),
    },
    strict=False,
)

FINAL_RAW_COLS = [
    "process_dt",
    "Sub-category",
    "week",
    "day",
    "product_id",
    "product_name",
    "sku class prod",
    "city_name",
    "hub_name",
    "sales",
    "final_sales",
    "simple_flag_when_SP_0",
    "simple_instances_when_SP_0",
    "simple_group_flag_when_SP_0",
    "simple_group_instances_when_SP_0",
]


class RawDataDateRange(BaseModel):
    start_date: pd.Timestamp = Field(...)
    end_date: pd.Timestamp = Field(...)

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value):
        return pd.to_datetime(value).normalize()

    @field_validator("end_date")
    @classmethod
    def _validate_window(cls, value, info):
        start = info.data.get("start_date")
        if start is not None and start > value:
            raise ValueError("Start date must be before end date.")
        if start is not None and (value - start).days + 1 > 7:
            raise ValueError("Select a maximum of 7 days.")
        return value


def _load_p_master_df(sheets_manager: GoogleSheetsManager) -> tuple[pd.DataFrame | None, str]:
    if os.path.exists(FF_MASTERS_XLSX):
        try:
            local_df = pd.read_excel(FF_MASTERS_XLSX, sheet_name="P Master")
            if local_df is not None and not local_df.empty:
                return clean_sheet_df(local_df), "local Product_Masters.xlsx"
        except Exception:
            pass

    for attempt in range(3):
        remote_df = sheets_manager.read_worksheet_uncached(
            "demand_planning_masters",
            "product_master",
            P_MASTER_READ_RANGE,
        )
        if remote_df is not None and not remote_df.empty:
            return clean_sheet_df(remote_df), "Google Sheets"
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    return None, ""


def _load_avl_flag_df(sheets_manager: GoogleSheetsManager) -> pd.DataFrame | None:
    local_path = os.path.join(DP_LOGICS_FOLDER, "Avl_Flag.xlsx")
    if os.path.exists(local_path):
        try:
            local_df = pd.read_excel(local_path)
            if local_df is not None and not local_df.empty:
                return local_df
        except Exception:
            pass
    return sheets_manager.read_worksheet_uncached("hub_level_planning", "avl_flag", "A:F")


class BaselineEngine:
    """Headless baseline data operations (no Streamlit)."""

    def __init__(self, *, db: Database | None = None) -> None:
        self.db = db or Database()
        self._pipeline_sheets: GoogleSheetsManager | None = None

    def use_pipeline_sheets(self, sheets: GoogleSheetsManager | None) -> None:
        self._pipeline_sheets = sheets

    @property
    def sheets_manager(self) -> GoogleSheetsManager:
        if self._pipeline_sheets is not None:
            return self._pipeline_sheets
        return get_sheets_manager()

    def load_rds_cached(self) -> pd.DataFrame:
        """Load 6w RDS via parquet cache under OUTPUT_PATH."""
        cache_path = OUTPUT_RDS_CACHE
        rds_path = RDS_6W_PATH

        use_cache = False
        if os.path.exists(cache_path) and rds_path and os.path.exists(rds_path):
            try:
                use_cache = os.path.getmtime(cache_path) >= os.path.getmtime(rds_path)
            except OSError:
                use_cache = False
        elif os.path.exists(cache_path) and (not rds_path or not os.path.exists(rds_path)):
            use_cache = True

        if use_cache:
            logger.info("Loading RDS from parquet cache: %s", cache_path)
            df = pd.read_parquet(cache_path)
        else:
            built = build_rds_parquet_cache()
            if built and os.path.exists(built):
                logger.info("Built RDS parquet cache: %s", built)
                df = pd.read_parquet(built)
            elif rds_path and os.path.exists(rds_path):
                logger.info("Reading RDS file: %s", rds_path)
                result = pyreadr.read_r(rds_path)
                df = next(iter(result.values()))
                OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
                df.to_parquet(cache_path, index=False)
            else:
                raise FileNotFoundError(
                    f"6w RDS not found. Set RDS_6W_PATH or sync analytics/6w_v3.rds to cloud storage."
                )

        df["process_dt"] = pd.to_datetime(df["process_dt"])
        return df

    def _validate_raw_input_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        return RAW_DATA_SCHEMA.validate(df, lazy=True)

    def _filter_raw_data_polars(
        self,
        df: pd.DataFrame,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> tuple[pd.DataFrame, int]:
        missing_cols = [c for c in RAW_DATA_COLUMNS_TO_KEEP if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Raw RDS data is missing required columns: {missing_cols}")

        lf = pl.from_pandas(df, include_index=False).lazy()
        date_start = pd.Timestamp(start_date).to_pydatetime()
        date_end = pd.Timestamp(end_date).to_pydatetime()

        in_range = lf.filter(
            (pl.col("process_dt") >= date_start) & (pl.col("process_dt") <= date_end)
        )
        before_exclusion = in_range.select(pl.len()).collect().item()

        filtered = (
            in_range.filter(~pl.col("hub_name").is_in(HUBS_TO_EXCLUDE))
            .filter(
                pl.col("product_id").is_not_null()
                & (pl.col("product_id").cast(pl.Utf8).str.strip_chars() != "")
                & pl.col("hub_name").is_not_null()
                & (pl.col("hub_name").cast(pl.Utf8).str.strip_chars() != "")
                & pl.col("process_dt").is_not_null()
            )
            .select(RAW_DATA_COLUMNS_TO_KEEP)
            .collect()
            .to_pandas()
        )
        excluded_count = before_exclusion - len(filtered)
        filtered["process_dt"] = pd.to_datetime(filtered["process_dt"])
        return filtered, excluded_count

    def fetch_liquidation_data(self, start_date, end_date) -> pd.DataFrame:
        start = pd.Timestamp(start_date).strftime("%Y-%m-%d")
        end = pd.Timestamp(end_date).strftime("%Y-%m-%d")
        try:
            conn = trino.dbapi.connect(
                host="trino.internal.dp.licious.com",
                port=80,
                user="default",
                catalog="hive",
                schema="planning",
                http_scheme="http",
            )
            cursor = conn.cursor()
            query = f"""
SELECT fnl4.dt, fnl4.hubid, map.hub_name, map.city_name, fnl4.productid,
       fnl4.productname, fnl4.liq_discount_perc, fnl4.packets_sold,
       fnl4.gross_revenue AS "gross_revenue (mrp)"
FROM (
    SELECT dt, hubid, productid, productname, liq_discount_perc,
           SUM(productqty) AS packets_sold, SUM(mrpproductpricef) AS gross_revenue
    FROM (
        SELECT *, ROUND((mrpproductpricef - productdiscountf) * 100.00 / mrpproductpricef, 0) AS liq_discount_perc
        FROM (
            SELECT *, CASE WHEN pormotionlevers_string LIKE '%"type":"LIQUIDATION"%' THEN 1 ELSE 0 END AS flag
            FROM (
                SELECT *, array_join(transform(promotionlevers, x -> format('{{"leverid":"%s","type":"%s"}}', x.leverid, x.type)), ',', '[]') AS pormotionlevers_string
                FROM b2c_supplychain.order_item_events_fact
                WHERE status != 'Rejected'
                  AND (yr > year(current_date - interval '84' day)
                       OR (yr = year(current_date - interval '84' day) AND mon >= month(current_date - interval '84' day)))
            ) fnl
        ) fnl2 WHERE flag = 1
    ) fnl3
    WHERE CAST(dt AS DATE) BETWEEN CAST(date_parse('{start}', '%Y-%m-%d') AS DATE)
                               AND CAST(date_parse('{end}', '%Y-%m-%d') AS DATE)
    GROUP BY dt, hubid, productid, productname, liq_discount_perc
) fnl4
LEFT JOIN pipeline.city_mapping_ba map ON CAST(map.hub_id AS VARCHAR) = fnl4.hubid
"""
            cursor.execute(query)
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            liq_df = pd.DataFrame(rows, columns=columns)
            liq_df["process_dt"] = pd.to_datetime(liq_df["dt"], errors="coerce")
            if "productid" in liq_df.columns and "product_id" not in liq_df.columns:
                liq_df.rename(columns={"productid": "product_id"}, inplace=True)
            liq_df["packets_sold"] = pd.to_numeric(liq_df["packets_sold"], errors="coerce").fillna(0)
            liq_df["product_id"] = liq_df["product_id"].astype(str)
            liq_df = liq_df.groupby(["hub_name", "product_id", "process_dt"], as_index=False)[
                "packets_sold"
            ].sum()
            return liq_df[["hub_name", "product_id", "process_dt", "packets_sold"]]
        except Exception as exc:
            logger.warning("Liquidation fetch failed (%s) — final_sales will equal sales", exc)
            return pd.DataFrame(columns=["hub_name", "product_id", "process_dt", "packets_sold"])

    def fetch_raw_data_from_rds(
        self,
        start_date,
        end_date,
        *,
        product_parity: bool = False,
        sheets_manager: GoogleSheetsManager | None = None,
    ) -> pd.DataFrame | None:
        date_range = RawDataDateRange(start_date=start_date, end_date=end_date)
        start_date = date_range.start_date
        end_date = date_range.end_date

        df = self.load_rds_cached()
        filtered_df, _ = self._filter_raw_data_polars(df, start_date, end_date)

        if filtered_df.empty:
            logger.warning("No RDS rows for %s → %s", start_date.date(), end_date.date())
            return None

        self._validate_raw_input_schema(filtered_df)

        columns_to_keep = [
            "city_name",
            "product_id",
            "hub_name",
            "process_dt",
            "sales",
            "group_flag",
            "group_instances",
            "grp_r7_plan",
            "grp_r7_inv",
            "grp_r7_plan_rev",
            "grp_r7_inv_rev",
            "grp_BasePlan",
            "grp_BaseRev",
            "r7_plan",
            "r7_inv",
            "r7_plan_rev",
            "r7_inv_rev",
            "BasePlan",
            "flag",
            "instances",
        ]
        filtered_df = filtered_df[columns_to_keep]

        filtered_df["wgt_flag"] = filtered_df["flag"] * filtered_df["r7_plan_rev"]
        filtered_df["wgt_instances"] = filtered_df["instances"] * filtered_df["r7_plan_rev"]
        filtered_df["new_grp_flag"] = np.where(
            filtered_df["r7_plan"] == 0,
            0,
            filtered_df["group_flag"] * filtered_df["grp_r7_plan_rev"],
        )
        filtered_df["new_grp_instances"] = np.where(
            filtered_df["r7_plan"] == 0,
            0,
            filtered_df["group_instances"] * filtered_df["grp_r7_plan_rev"],
        )

        gsm = sheets_manager or self.sheets_manager
        p_master = _load_avl_flag_df(gsm)
        if p_master is None or p_master.empty:
            logger.warning("Avl_Flag master unavailable — proceeding without merge")
            merged_df = filtered_df.copy()
            merged_df["Anchor ID"] = merged_df["product_id"]
        else:
            merged_df = filtered_df.merge(p_master, on="product_id", how="left")
            if "Anchor ID" in merged_df.columns:
                merged_df["Anchor ID"] = merged_df["Anchor ID"].fillna(merged_df["product_id"])
            else:
                merged_df["Anchor ID"] = merged_df["product_id"]

        merged_df["plan_sum"] = merged_df.groupby(["hub_name", "process_dt", "Anchor ID"])[
            "r7_inv"
        ].transform("sum")
        merged_df["simple_flag_when_SP_0"] = np.where(
            merged_df["plan_sum"] == 0, merged_df["group_flag"], merged_df["flag"]
        )
        merged_df["simple_instances_when_SP_0"] = np.where(
            merged_df["plan_sum"] == 0, merged_df["group_instances"], merged_df["instances"]
        )
        merged_df["simple_group_flag_when_SP_0"] = np.where(
            merged_df["plan_sum"] == 0, merged_df["group_flag"], merged_df["group_flag"]
        )
        merged_df["simple_group_instances_when_SP_0"] = np.where(
            merged_df["plan_sum"] == 0,
            merged_df["group_instances"],
            merged_df["group_instances"],
        )
        merged_df = merged_df.drop_duplicates(
            subset=["city_name", "hub_name", "product_id", "process_dt"]
        )

        if product_parity:
            merged_df["process_dt"] = pd.to_datetime(merged_df["process_dt"], errors="coerce")
            merged_df["week"] = merged_df["process_dt"].dt.isocalendar().week.astype(int)
            merged_df["day"] = merged_df["process_dt"].dt.strftime("%a")
            product_cols = [
                "city_name",
                "hub_name",
                "product_id",
                "process_dt",
                "week",
                "day",
                "sales",
                "simple_flag_when_SP_0",
                "simple_instances_when_SP_0",
                "simple_group_flag_when_SP_0",
                "simple_group_instances_when_SP_0",
            ]
            return merged_df[[c for c in product_cols if c in merged_df.columns]].copy()

        liq_df = self.fetch_liquidation_data(start_date, end_date)
        if not liq_df.empty:
            merged_df["product_id"] = merged_df["product_id"].astype(str)
            merged_df = merged_df.merge(
                liq_df, on=["hub_name", "product_id", "process_dt"], how="left"
            )
            merged_df["packets_sold"] = pd.to_numeric(
                merged_df["packets_sold"], errors="coerce"
            ).fillna(0)
        else:
            merged_df["packets_sold"] = 0
        merged_df["final_sales"] = np.maximum(merged_df["sales"] - merged_df["packets_sold"], 0)

        merged_df["week"] = merged_df["process_dt"].dt.isocalendar().week.astype(int)
        merged_df["day"] = merged_df["process_dt"].dt.strftime("%a")

        try:
            p_master_df, _ = _load_p_master_df(gsm)
            if p_master_df is not None and not p_master_df.empty:
                sku_map, name_map, category_map, _ = p_master_enrichment_maps(p_master_df)
                merged_df["sku class prod"] = merged_df["product_id"].map(sku_map)
                merged_df["product_name"] = merged_df["product_id"].map(name_map)
                merged_df["Sub-category"] = merged_df["product_id"].map(category_map)
            else:
                raise ValueError("P Master empty")
        except Exception as exc:
            logger.warning("SKU enrichment failed (%s)", exc)
            merged_df["sku class prod"] = None
            merged_df["product_name"] = None
            merged_df["Sub-category"] = None

        final_df = merged_df[[c for c in FINAL_RAW_COLS if c in merged_df.columns]]

        if "hub_name" in final_df.columns:
            mask = final_df["hub_name"].astype(str).str.upper().str.startswith(("PAW", "OFF"))
            final_df = final_df[~mask].copy()
        dedup_keys = [c for c in ["hub_name", "product_id", "process_dt"] if c in final_df.columns]
        if dedup_keys:
            final_df = final_df.drop_duplicates(subset=dedup_keys, keep="first").reset_index(
                drop=True
            )

        logger.info("Raw data fetch complete: %s rows", len(final_df))
        return final_df

    def load_rds_cached_baseline(self) -> pd.DataFrame:
        df = self.load_rds_cached()
        if "Week" not in df.columns:
            df["process_dt"] = pd.to_datetime(df["process_dt"], errors="coerce")
            df = df.dropna(subset=["process_dt"])
            df["Week"] = df["process_dt"].dt.isocalendar().week.astype(int)
        if "day" not in df.columns:
            df["day"] = df["process_dt"].dt.strftime("%a")
        return df

    def fetch_previous_baseline(
        self, week_number: int, year_number: int | None = None
    ) -> pd.DataFrame | None:
        try:
            full_df = self.load_rds_cached_baseline()
            week_mask = full_df["Week"] == int(week_number)

            if year_number is not None:
                year_mask = full_df["process_dt"].dt.year == int(year_number)
                baseline_df = full_df[week_mask & year_mask].copy()
                if baseline_df.empty:
                    return None
            else:
                baseline_df = full_df[week_mask].copy()
                if baseline_df.empty:
                    return None

            if os.path.exists(FF_MASTERS_XLSX):
                pm_raw = pd.read_excel(FF_MASTERS_XLSX)
                pm_raw.rename(columns={c: c.strip() for c in pm_raw.columns}, inplace=True)
                id_col = next(
                    (c for c in pm_raw.columns if c.strip().lower() == "product id"), None
                )
                cat_col = next(
                    (c for c in pm_raw.columns if "sub" in c.lower() and "cat" in c.lower()),
                    None,
                )
                name_col = next(
                    (
                        c
                        for c in pm_raw.columns
                        if "product" in c.lower() and "name" in c.lower()
                    ),
                    None,
                )
                sku_col = next((c for c in pm_raw.columns if "sku" in c.lower()), None)

                if id_col:
                    pm = pm_raw[[c for c in [id_col, cat_col, name_col, sku_col] if c]].copy()
                    pm.rename(
                        columns={
                            id_col: "product_id",
                            cat_col: "Sub-category",
                            name_col: "product_name",
                            sku_col: "sku class prod",
                        },
                        inplace=True,
                    )
                    pm = pm.dropna(subset=["product_id"]).drop_duplicates(subset=["product_id"])
                    baseline_df.drop(
                        columns=["Sub-category", "product_name", "sku class prod"],
                        errors="ignore",
                        inplace=True,
                    )
                    baseline_df = baseline_df.merge(pm, on="product_id", how="left")
                else:
                    for col in ["Sub-category", "product_name", "sku class prod"]:
                        baseline_df[col] = ""
            else:
                for col in ["Sub-category", "product_name", "sku class prod"]:
                    baseline_df[col] = ""

            baseline_df = normalize_base_plan_columns(baseline_df)
            final_cols = [
                c
                for c in [
                    "process_dt",
                    "Sub-category",
                    "Week",
                    "day",
                    "product_id",
                    "product_name",
                    "city_name",
                    "hub_name",
                    "BasePlan",
                    "sku class prod",
                ]
                if c in baseline_df.columns
            ]
            baseline_df = baseline_df[final_cols]
            dedup_keys = [
                c for c in ["hub_name", "product_id", "process_dt"] if c in baseline_df.columns
            ]
            if dedup_keys:
                baseline_df = baseline_df.drop_duplicates(subset=dedup_keys, keep="first").reset_index(
                    drop=True
                )
            return baseline_df
        except FileNotFoundError:
            raise
        except Exception as exc:
            logger.exception("Previous baseline fetch failed: %s", exc)
            return None


def get_baseline_engine(*, sheets: GoogleSheetsManager | None = None) -> BaselineEngine:
    engine = BaselineEngine()
    if sheets is not None:
        engine.use_pipeline_sheets(sheets)
    return engine
