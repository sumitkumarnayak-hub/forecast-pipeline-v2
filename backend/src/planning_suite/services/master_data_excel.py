"""Excel helpers for master data sync (headless — no Streamlit UI dependency)."""
from __future__ import annotations


def get_excel_writer_engine() -> str:
    """Return a pandas ExcelWriter engine available in this environment."""
    try:
        import openpyxl  # noqa: F401

        return "openpyxl"
    except ImportError:
        pass
    try:
        import xlsxwriter  # noqa: F401

        return "xlsxwriter"
    except ImportError as exc:
        raise ImportError(
            "No Excel writer available. Install openpyxl or xlsxwriter."
        ) from exc
