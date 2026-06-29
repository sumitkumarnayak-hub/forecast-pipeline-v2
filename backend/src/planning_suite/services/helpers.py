"""
Helper utilities for the application
"""
import pandas as pd
import numpy as np
from datetime import datetime
import uuid


def generate_run_id(prefix="RUN"):
    """Generate unique run ID"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{timestamp}_{unique_id}"


def format_number(num, decimals=2):
    """Format number with thousands separator"""
    if pd.isna(num):
        return "N/A"
    try:
        return f"{num:,.{decimals}f}"
    except:
        return str(num)


def safe_division(numerator, denominator, default=0):
    """Safely divide two numbers"""
    try:
        if denominator == 0:
            return default
        return numerator / denominator
    except:
        return default


def normalize_base_plan_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map previous-baseline plan columns to the canonical ``BasePlan`` name."""
    if df is None or df.empty:
        return df
    if "BasePlan" in df.columns:
        return df
    out = df.copy()
    for col in ("Base_Plan (qty)", "Base_plan", "base_plan", "Base Plan", "base plan"):
        if col in out.columns:
            return out.rename(columns={col: "BasePlan"})
    lower_map = {c.strip().lower(): c for c in out.columns}
    for key in ("baseplan", "base_plan (qty)", "base_plan", "base plan"):
        if key in lower_map:
            return out.rename(columns={lower_map[key]: "BasePlan"})
    return out


def display_metric_card(title, value, delta=None, help_text=None):
    """Display a metric card with optional delta"""
    col1, col2 = st.columns([3, 1])
    with col1:
        st.metric(
            label=title,
            value=value,
            delta=delta,
            help=help_text
        )


def create_download_link(df, filename, file_format="xlsx"):
    """Create download button for DataFrame"""
    if file_format == "xlsx":
        output = df.to_excel(filename, index=False, engine='openpyxl')
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif file_format == "csv":
        output = df.to_csv(index=False)
        mime = "text/csv"
    else:
        raise ValueError(f"Unsupported format: {file_format}")
    
    return st.download_button(
        label=f"📥 Download {file_format.upper()}",
        data=output if file_format == "csv" else open(filename, 'rb').read(),
        file_name=filename,
        mime=mime
    )


def validate_dataframe(df, required_columns, unique_columns=None):
    """Validate DataFrame structure"""
    errors = []
    
    # Check for missing columns
    missing_cols = set(required_columns) - set(df.columns)
    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}")
    
    # Check for empty DataFrame
    if df.empty:
        errors.append("DataFrame is empty")
    
    # Check for duplicate values in unique columns
    if unique_columns:
        for col in unique_columns:
            if col in df.columns:
                duplicates = df[df.duplicated(subset=[col], keep=False)]
                if not duplicates.empty:
                    errors.append(f"Duplicate values found in column '{col}': {len(duplicates)} rows")
    
    # Check for missing values in required columns
    for col in required_columns:
        if col in df.columns:
            missing_count = df[col].isna().sum()
            if missing_count > 0:
                errors.append(f"Missing values in '{col}': {missing_count} rows")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def display_validation_results(validation_result):
    """Display validation results"""
    if validation_result["valid"]:
        st.success("✅ All validations passed!")
        return True
    else:
        st.error("❌ Validation failed:")
        for error in validation_result["errors"]:
            st.error(f"  • {error}")
        return False


def convert_date_columns(df, date_columns):
    """Convert specified columns to datetime"""
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def convert_numeric_columns(df, numeric_columns):
    """Convert specified columns to numeric"""
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def clean_percentage_column(series):
    """Clean percentage column (remove % sign and convert to decimal)"""
    if series.dtype == 'object':
        series = series.str.rstrip('%')
    return pd.to_numeric(series, errors='coerce') / 100


def format_timestamp(dt):
    """Format timestamp for display"""
    if pd.isna(dt):
        return "N/A"
    if isinstance(dt, str):
        dt = pd.to_datetime(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def create_summary_stats(df, metric_columns):
    """Create summary statistics for DataFrame"""
    stats = {}
    for col in metric_columns:
        if col in df.columns:
            stats[col] = {
                "sum": df[col].sum(),
                "mean": df[col].mean(),
                "median": df[col].median(),
                "min": df[col].min(),
                "max": df[col].max(),
                "count": df[col].count()
            }
    return stats


def display_dataframe_info(df, title="DataFrame Info"):
    """Display DataFrame information"""
    with st.expander(title):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Rows", f"{len(df):,}")
        with col2:
            st.metric("Columns", len(df.columns))
        with col3:
            st.metric("Memory", f"{df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        
        st.write("**Column Types:**")
        st.dataframe(pd.DataFrame({
            "Column": df.columns,
            "Type": df.dtypes.astype(str),
            "Non-Null": df.count().values,
            "Null": df.isna().sum().values
        }), use_container_width=True)


def show_progress_bar(current, total, text="Processing"):
    """Show progress bar"""
    progress = current / total
    st.progress(progress, text=f"{text}: {current}/{total} ({progress*100:.1f}%)")
