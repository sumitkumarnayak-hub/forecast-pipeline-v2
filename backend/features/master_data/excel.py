"""Excel helpers for master data sync (headless — no Streamlit UI dependency)."""
from __future__ import annotations


def get_excel_writer_engine() -> str:
    """Return a pandas ExcelWriter engine available in this environment."""
    # xlsxwriter is much faster for large sheets (e.g. 100k+ row P-H Master).
    try:
        import xlsxwriter  # noqa: F401

        return "xlsxwriter"
    except ImportError:
        pass
    try:
        import openpyxl  # noqa: F401

        return "openpyxl"
    except ImportError as exc:
        raise ImportError(
            "No Excel writer available. Install xlsxwriter or openpyxl."
        ) from exc
