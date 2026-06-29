"""Background master sync triggered on login."""
from __future__ import annotations


from planning_suite.db.engine import Database
from planning_suite.services.google_sheets import GoogleSheetsManager


def sync_masters_from_sheets(user_id: int, db: Database | None = None) -> tuple[bool, str]:
    """Pull all masters from Google Sheets into session state and log sync."""
    db = db or Database()
    try:
        sheets = GoogleSheetsManager()
        all_masters = sheets.get_all_masters()
        if "masters" not in st.session_state:
            st.session_state.masters = {}

        synced = 0
        for master_type, df in all_masters.items():
            if df is None:
                continue
            st.session_state.masters[master_type] = df
            db.log_master_sync({
                "master_type": master_type,
                "user_id": user_id,
                "records_synced": len(df),
                "status": "success",
            })
            synced += 1

        if synced == 0:
            return False, "No master data returned from Google Sheets."
        return True, f"Auto-synced {synced} master dataset(s) from Google Sheets."
    except Exception as exc:
        return False, str(exc)


def maybe_auto_sync_on_login(user: dict, db: Database) -> None:
    """Run master auto-sync once per session when the user preference is enabled."""
    prefs = st.session_state.get("user_preferences") or db.get_user_preferences(user["id"])
    if not prefs.get("auto_sync_masters"):
        return

    flag = f"_auto_sync_done_{user['id']}"
    if st.session_state.get(flag):
        return
    st.session_state[flag] = True

    ok, message = sync_masters_from_sheets(user["id"], db)
    if ok:
        st.toast(message, icon="✅")
    else:
        st.toast(f"Auto-sync skipped: {message}", icon="⚠️")


def load_user_preferences(user_id: int, db: Database | None = None) -> dict:
    """Load preferences into session state."""
    db = db or Database()
    prefs = db.get_user_preferences(user_id)
    st.session_state.user_preferences = prefs
    return prefs
