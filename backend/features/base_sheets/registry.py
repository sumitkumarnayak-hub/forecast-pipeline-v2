"""
Base Sheets Registry
====================
This is the ONLY file you need to edit to manage base sheets.

STRUCTURE
---------
Sheets are organised into named GROUPS (shown as tabs in the portal).
Each group is a list of sheet entries.

HOW TO ADD A NEW SHEET
-----------------------
1. Pick the group it belongs to (or create a new group key).
2. Add a dict block inside that group's list:

    {
        "key":   "my_sheet",          # short unique ID — used in filenames & DB logs
        "label": "My Sheet Name",     # display name shown in the portal tab
        "url":   "https://docs.google.com/spreadsheets/d/SHEET_ID/edit?gid=TAB_GID#gid=TAB_GID",
    }

HOW TO ADD A NEW GROUP (TAB)
-----------------------------
Add a new top-level key to BASE_SHEETS_GROUPS:

    "My New Group": [
        { "key": "...", "label": "...", "url": "..." },
    ],

HOW TO UPDATE A URL
-------------------
Change the "url" value in the block below. Copy the full URL from Google Sheets
including the ?gid= part if you want a specific tab.

HOW TO REMOVE A SHEET
----------------------
Delete its dict block.
"""
from __future__ import annotations
import re


def _gid(url: str) -> int | None:
    """Auto-extract the tab gid from the URL (no manual entry needed)."""
    m = re.search(r"[?&#]gid=(\d+)", url)
    return int(m.group(1)) if m else None


# =============================================================================
#  ✏️  EDIT HERE — Add / rename / remove sheets and groups
# =============================================================================

BASE_SHEETS_GROUPS: dict[str, list[dict]] = {

    "Masters": [
        {
            "key":   "pl_master",
            "label": "P - L Master",
            "url":   "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=1348760312#gid=1348760312",
        },
        {
            "key":   "p_master",
            "label": "P Master",
            "url":   "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=1946014559#gid=1946014559",
        },
        {
            "key":   "ff_input",
            "label": "FF Input",
            "url":   "https://docs.google.com/spreadsheets/d/1khMPvdsSwsY75qG15TcdIUv_-qIm3Fg3GwtOkiMtWIs/edit?gid=1977483823#gid=1977483823",
        },
        {
            "key":   "htt_mapping",
            "label": "HTT Mapping",
            "url":   "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=268012973#gid=268012973",
        },
        {
            "key":   "pure_preorder",
            "label": "Pure Preorder",
            "url":   "https://docs.google.com/spreadsheets/d/1qHFovpLdeepHPv9qQbyDunK-01fBBgdaVMFoYRP3RNo/edit?gid=1010385281#gid=1010385281",
        },
        {
            "key":   "Hub_sku_master",
            "label": "Hub Sku Master",
            "url":   "https://docs.google.com/spreadsheets/d/1qHFovpLdeepHPv9qQbyDunK-01fBBgdaVMFoYRP3RNo/edit?gid=0#gid=0",
        },
    ],

    "Inv Buffer Masters": [
        {
            "key":   "hub_inv_buffer",
            "label": "Hub (Inv Buffer)",
            "url":   "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=1360980126#gid=1360980126",
        },
        {
            "key":   "cluster_v1",
            "label": "Cluster V1",
            "url":   "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=1821041592#gid=1821041592",
        },
        {
            "key":   "cluster_v2",
            "label": "Cluster V2",
            "url":   "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=565473997#gid=565473997",
        },
        {
            "key":   "no_buffer_inv_plan",
            "label": "No Buffer (Inv Plan)",
            "url":   "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=1707826992#gid=1707826992",
        },
        {
          "key" : "cogs" ,
          "label" : "COGS" ,
          "url" :"https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=1388449777#gid=1388449777" ,
        },
        {
          "key" : "Inv_buffer" ,
          "label" : "Inv Buffer" ,
          "url" :"https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=347303013#gid=347303013" ,
        },
        {
          "key" : "Consistent_issues_logics",
          "label" : "Consistent Issues Logics",
          "url" : "https://docs.google.com/spreadsheets/d/1qHFovpLdeepHPv9qQbyDunK-01fBBgdaVMFoYRP3RNo/edit?gid=1677138519#gid=1677138519",
        }
    ],

    # ── Add a new group (portal tab) here ────────────────────────────────────
    # "My New Group": [
    #     {
    #         "key":   "my_sheet_key",
    #         "label": "My Sheet",
    #         "url":   "https://docs.google.com/spreadsheets/d/SHEET_ID/edit?gid=TAB_GID",
    #     },
    # ],
    # ─────────────────────────────────────────────────────────────────────────

} 

# =============================================================================


# Build the flat BASE_SHEETS_REGISTRY dict used throughout the codebase.
# Auto-populates "gid" and "group" from the groups structure above.
BASE_SHEETS_REGISTRY: dict[str, dict] = {}
for _group_name, _entries in BASE_SHEETS_GROUPS.items():
    for _entry in _entries:
        BASE_SHEETS_REGISTRY[_entry["key"]] = {
            "label": _entry["label"],
            "url":   _entry["url"],
            "group": _group_name,
            "gid":   _gid(_entry["url"]),
        }
