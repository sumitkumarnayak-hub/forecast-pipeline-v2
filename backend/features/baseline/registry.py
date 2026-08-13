"""
Configuration Masters Registry
==============================
This is the single source of truth for Configuration Masters (DP Logics worksheets).
Each worksheet listed here will appear as a separate row card on the configure page,
with its own sync status, last updated time, and "Sync Now" button.

HOW TO ADD A NEW WORKSHEET
--------------------------
1. Pick a group (tab) or add a new one.
2. Add a new dict entry block under that group:

    {
        "key":   "MyNewWorksheet",          # Internal identifier & output filename (e.g. MyNewWorksheet.xlsx)
        "label": "My New Worksheet Label",  # User-friendly label shown in the UI
        "url":   "https://docs.google.com/spreadsheets/d/SHEET_ID/edit#gid=GID",  # Google Sheets URL
        "tab_name": "Sheet1",               # Specific tab title in the sheet (optional, defaults to key)
    }

No other file needs changing.
"""
from __future__ import annotations
import re


def _gid(url: str) -> int | None:
    """Auto-extract the tab gid from the URL (no manual entry needed)."""
    m = re.search(r"[?&#]gid=(\d+)", url)
    return int(m.group(1)) if m else None


# =============================================================================
#  ✏️  EDIT HERE — Add / rename / remove Configuration Masters worksheets
# =============================================================================
CONFIG_MASTERS_GROUPS: dict[str, list[dict]] = {
    "Configuration Masters": [
        {
            "key": "City_Cat",
            "label": "City Cat (Outlier)",
            "url": "https://docs.google.com/spreadsheets/d/1KtX8cxaBjc4tq6Gz1_BxSBS1FyIAc43ZRbFwlfHtQ4k/edit?gid=1448963036#gid=1448963036",
            "tab_name": "City_Cat",
        },
        {
            "key": "SellThroughFactor",
            "label": "Sell-Through Factor",
            "url": "https://docs.google.com/spreadsheets/d/1KtX8cxaBjc4tq6Gz1_BxSBS1FyIAc43ZRbFwlfHtQ4k/edit?gid=1938228461#gid=1938228461",
            "tab_name": "SellThroughFactor",
        },
        {
            "key":   "stf_hub",
            "label": "STF_hub",
            "url":   "https://docs.google.com/spreadsheets/d/1qHFovpLdeepHPv9qQbyDunK-01fBBgdaVMFoYRP3RNo/edit?gid=1723196652#gid=1723196652",
            "tab_name" : "STF_hub",
        },
        {
            "key": "City_drops",
            "label": "City Drops",
            "url": "https://docs.google.com/spreadsheets/d/1KtX8cxaBjc4tq6Gz1_BxSBS1FyIAc43ZRbFwlfHtQ4k/edit?gid=1875088945#gid=1875088945",
            "tab_name": "City_drops",
        },
        {
            "key": "Percentile",
            "label": "Percentile Settings",
            "url": "https://docs.google.com/spreadsheets/d/1KtX8cxaBjc4tq6Gz1_BxSBS1FyIAc43ZRbFwlfHtQ4k/edit?gid=1177650883#gid=1177650883",
            "tab_name": "Percentile",
        },
    ]
}
# =============================================================================


# Derived collections for backend compatibility
CONFIG_MASTERS_REGISTRY = {}
for _group_name, _entries in CONFIG_MASTERS_GROUPS.items():
    for _entry in _entries:
        CONFIG_MASTERS_REGISTRY[_entry["key"]] = {
            "label":    _entry["label"],
            "url":      _entry["url"],
            "group":    _group_name,
            "tab_name": _entry.get("tab_name", _entry["key"]),
            "gid":      _gid(_entry["url"]),
        }

DP_LOGICS_WORKSHEETS_DICT = {
    key: ("hub_level_planning", info["tab_name"])
    for key, info in CONFIG_MASTERS_REGISTRY.items()
}

DP_LOGICS_WORKSHEETS_LIST = list(CONFIG_MASTERS_REGISTRY.keys())
