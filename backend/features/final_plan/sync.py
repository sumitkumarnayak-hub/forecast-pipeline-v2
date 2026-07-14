"""Sync logic for Final Plan inputs from Google Sheets."""
import os
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from app.config import (
    DP_LOGICS_SHEET_KEY,
    INV_LOGICS_SHEET_KEY,
    FF_INPUTS_FOLDER,
    FF_INV_LOGIC_FOLDER,
)
from core.shared.google_sheets import GoogleSheetsManager


INV_TABS = ["Hub(Inv_Buffer)", "cluster_mapping", "Cluster phase 2", "No_Buffer(Inv_Plan)"]

def _ws_to_df(ws, rng=None):
    data = ws.get(rng) if rng else ws.get_all_values()
    if len(data) < 2:
        return pd.DataFrame()
    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = [c.strip() for c in df.columns]
    return df

def sync_adhoc_from_sheet():
    os.makedirs(FF_INPUTS_FOLDER, exist_ok=True)
    gsm = GoogleSheetsManager()
    if not gsm.client:
        gsm.client = gsm._initialize_client()
    
    ss = gsm.client.open_by_key(DP_LOGICS_SHEET_KEY)
    ws_adj = ss.worksheet("Adhoc Adjustment")
    
    def _fetch_and_save_adj(args):
        ws_obj, rng, filename = args
        df = _ws_to_df(ws_obj, rng)
        df.to_excel(os.path.join(FF_INPUTS_FOLDER, filename), index=False)

    tasks = [
        (ws_adj, "A:D", "Adhoc_Adjustment.xlsx"),
        (ws_adj, "H:K", "Adhoc_Adjustment_City_Product.xlsx"),
        (ss.worksheet("Adhoc Adjustment Hub"), "A:F", "Adhoc_Adjustment_Hub.xlsx")
    ]
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(_fetch_and_save_adj, tasks))

def sync_inventory_from_sheet():
    os.makedirs(FF_INV_LOGIC_FOLDER, exist_ok=True)
    gsm = GoogleSheetsManager()
    if not gsm.client:
        gsm.client = gsm._initialize_client()
        
    ss = gsm.client.open_by_key(INV_LOGICS_SHEET_KEY)
    
    def _fetch_and_save_inv(tab_name):
        ws = ss.worksheet(tab_name)
        df = _ws_to_df(ws)
        df.to_excel(os.path.join(FF_INV_LOGIC_FOLDER, f"{tab_name}.xlsx"), index=False)

    with ThreadPoolExecutor(max_workers=len(INV_TABS)) as executor:
        list(executor.map(_fetch_and_save_inv, INV_TABS))
