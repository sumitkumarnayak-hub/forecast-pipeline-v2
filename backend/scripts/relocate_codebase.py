#!/usr/bin/env python3
"""
Relocation and import refactoring script for the backend restructure.
Performs the directory relocation and automatically rewrites import statements
across the codebase to match the new structure using a smart line-by-line resolver.
"""

import os
import shutil
import re
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Mapping: Old path relative to backend/ -> New path relative to backend/
MAPPING = {
    # 1. Routers
    "app/routers/auth.py": "features/auth/router.py",
    "app/routers/autopilot.py": "features/autopilot/router.py",
    "app/routers/baseline.py": "features/baseline/router.py",
    "app/routers/dashboard.py": "features/dashboard/router.py",
    "app/routers/insights.py": "features/insights/router.py",
    "app/routers/final_plan.py": "features/final_plan/router.py",
    "app/routers/new_product_launch.py": "features/product_launch/router.py",
    "app/routers/settings.py": "features/settings/router.py",
    "app/routers/validation.py": "features/validation/router.py",
    "app/routers/master_data.py": "features/master_data/router.py",
    "app/routers/demo_filter.py": "features/shared/demo_filter_router.py",

    # 2. Config & Core modules
    "src/planning_suite/config.py": "app/config.py",
    "src/planning_suite/cloud_paths.py": "core/shared/cloud_paths.py",
    "src/planning_suite/google_credentials.py": "core/shared/google_credentials.py",

    # 3. Security
    "src/planning_suite/core/auth.py": "core/security/auth.py",
    "src/planning_suite/core/auth_tokens.py": "core/security/tokens.py",
    "src/planning_suite/core/permissions.py": "core/security/permissions.py",
    "app/auth_cookies.py": "core/security/auth_cookies.py",
    "app/deps.py": "app/dependencies.py",
    "app/logging_config.py": "app/logging.py",
    "app/production.py": "app/production.py",  # Keep under app/

    # 4. Database
    "src/planning_suite/db/engine.py": "core/database/engine.py",
    "src/planning_suite/db/models.py": "core/database/models.py",

    # 5. Storage
    "src/planning_suite/storage/base.py": "core/storage/base.py",
    "src/planning_suite/storage/local.py": "core/storage/local.py",
    "src/planning_suite/storage/drive.py": "core/storage/drive.py",
    "src/planning_suite/storage/supabase_backend.py": "core/storage/supabase.py",
    "src/planning_suite/storage/sync.py": "core/storage/sync.py",
    "src/planning_suite/storage/factory.py": "core/storage/factory.py",
    "src/planning_suite/storage/artifacts.py": "core/storage/artifacts.py",

    # 6. Core Utils & UI
    "src/planning_suite/core/dataframe.py": "core/utils/dataframe.py",
    "src/planning_suite/core/session_store.py": "core/utils/session_store.py",
    "src/planning_suite/ui/nav.py": "core/ui/nav.py",
    "src/planning_suite/ui/pages/optimized_baseline.py": "core/ui/pages/optimized_baseline.py",

    # 7. Features: Product Launch
    "src/planning_suite/features/new_product_launch.py": "features/product_launch/core.py",
    "src/planning_suite/services/npl_wizard.py": "features/product_launch/wizard.py",
    "src/planning_suite/services/npl_sheet_reads.py": "features/product_launch/sheet_reads.py",
    "src/planning_suite/services/ff_input_watcher.py": "features/product_launch/watcher.py",
    "src/planning_suite/services/product_launch_sync.py": "features/product_launch/sync.py",
    "src/planning_suite/automation/new_product_launch_sync.py": "features/product_launch/auto_sync.py",

    # 8. Features: Baseline
    "src/planning_suite/services/baseline_comparison.py": "features/baseline/comparison.py",
    "src/planning_suite/services/baseline_engine.py": "features/baseline/engine.py",
    "src/planning_suite/services/baseline_engine_compare.py": "features/baseline/engine_compare.py",
    "src/planning_suite/services/baseline_io.py": "features/baseline/io.py",
    "src/planning_suite/services/baseline_manual.py": "features/baseline/manual.py",
    "src/planning_suite/services/baseline_wave_ops.py": "features/baseline/wave_ops.py",

    # 9. Features: Autopilot
    "src/planning_suite/services/manual_autopilot_sync.py": "features/autopilot/sync.py",
    "src/planning_suite/automation/autopilot_state.py": "features/autopilot/state.py",
    "src/planning_suite/automation/autopilot_steps.py": "features/autopilot/steps.py",
    "src/planning_suite/automation/autopilot_ui_config.py": "features/autopilot/ui_config.py",
    "src/planning_suite/automation/optimized_autopilot.py": "features/autopilot/optimized.py",

    # 10. Features: Dashboard / Insights
    "src/planning_suite/services/dashboard_analytics.py": "features/dashboard/analytics.py",
    "src/planning_suite/services/dashboard_cache.py": "features/dashboard/cache.py",
    "src/planning_suite/services/dashboard_revenue_trends.py": "features/dashboard/revenue_trends.py",
    "src/planning_suite/services/analytics_6w.py": "features/dashboard/analytics_6w.py",
    "src/planning_suite/services/analytics_reports.py": "features/dashboard/analytics_reports.py",
    "src/planning_suite/services/insights_analytics.py": "features/insights/analytics.py",

    # 11. Features: Final Plan
    "src/planning_suite/services/final_plan_engine.py": "features/final_plan/engine.py",
    "src/planning_suite/services/final_plan_inputs.py": "features/final_plan/inputs.py",
    "src/planning_suite/services/final_plan_sync.py": "features/final_plan/sync.py",
    "src/planning_suite/services/hub_sync.py": "features/final_plan/hub_sync.py",

    # 12. Features: Hub Launch
    "src/planning_suite/services/hub_launch_sync.py": "features/hub_launch/sync.py",
    "src/planning_suite/automation/new_hub_launch_sync.py": "features/hub_launch/auto_sync.py",

    # 13. Features: Master Data
    "src/planning_suite/services/master_data_excel.py": "features/master_data/excel.py",
    "src/planning_suite/automation/master_data_sync.py": "features/master_data/sync.py",

    # 14. Features: Validation
    "src/planning_suite/services/output_validation.py": "features/validation/output_validation.py",
    "src/planning_suite/services/validation_history.py": "features/validation/history.py",
    "src/planning_suite/services/validation_input.py": "features/validation/input.py",
    "src/planning_suite/services/validation_service.py": "features/validation/service.py",
    "src/planning_suite/core/validations/master_rules.py": "features/validation/rules.py",
    "src/planning_suite/core/validations/runner.py": "features/validation/runner.py",

    # 15. Features: Settings
    "src/planning_suite/services/settings_service.py": "features/settings/service.py",

    # 16. Shared common services
    "src/planning_suite/services/demo_filter_dataset.py": "core/shared/demo_filter_dataset.py",
    "src/planning_suite/services/demo_filter_store.py": "core/shared/demo_filter_store.py",
    "src/planning_suite/services/google_sheets.py": "core/shared/google_sheets.py",
    "src/planning_suite/services/email_service.py": "core/shared/email.py",
    "src/planning_suite/services/api_cache.py": "core/shared/api_cache.py",
    "src/planning_suite/services/cache_warmup.py": "core/shared/cache_warmup.py",
    "src/planning_suite/services/sheets_cache.py": "core/shared/sheets_cache.py",
    "src/planning_suite/services/sheets_session.py": "core/shared/sheets_session.py",
    "src/planning_suite/services/sheets_throttle.py": "core/shared/sheets_throttle.py",
    "src/planning_suite/services/parquet_cache.py": "core/shared/parquet_cache.py",
    "src/planning_suite/services/raw_actuals_cache.py": "core/shared/raw_actuals_cache.py",
    "src/planning_suite/services/workflow_notifications.py": "core/shared/workflow_notifications.py",
    "src/planning_suite/services/pipeline_flow.py": "core/shared/pipeline_flow.py",
    "src/planning_suite/services/pipeline_state.py": "core/shared/pipeline_state.py",
    "src/planning_suite/services/sync_versioning.py": "core/shared/sync_versioning.py",
    "src/planning_suite/services/system_details.py": "core/shared/system_details.py",
    "src/planning_suite/services/storage_status.py": "core/shared/storage_status.py",
    "src/planning_suite/services/helpers.py": "core/shared/helpers.py",
    "src/planning_suite/services/login_sync.py": "core/shared/login_sync.py",
    "src/planning_suite/services/audit_context.py": "core/shared/audit_context.py",
}

STRING_REPLACEMENTS = [
    # General services -> core/shared/
    ("core.shared.google_sheets", "core.shared.google_sheets"),
    ("core.shared.email", "core.shared.email"),
    ("core.shared.api_cache", "core.shared.api_cache"),
    ("core.shared.cache_warmup", "core.shared.cache_warmup"),
    ("core.shared.sheets_cache", "core.shared.sheets_cache"),
    ("core.shared.sheets_session", "core.shared.sheets_session"),
    ("core.shared.sheets_throttle", "core.shared.sheets_throttle"),
    ("core.shared.parquet_cache", "core.shared.parquet_cache"),
    ("core.shared.raw_actuals_cache", "core.shared.raw_actuals_cache"),
    ("core.shared.workflow_notifications", "core.shared.workflow_notifications"),
    ("core.shared.pipeline_flow", "core.shared.pipeline_flow"),
    ("core.shared.pipeline_state", "core.shared.pipeline_state"),
    ("core.shared.sync_versioning", "core.shared.sync_versioning"),
    ("core.shared.system_details", "core.shared.system_details"),
    ("core.shared.storage_status", "core.shared.storage_status"),
    ("core.shared.helpers", "core.shared.helpers"),
    ("core.shared.login_sync", "core.shared.login_sync"),
    ("core.shared.audit_context", "core.shared.audit_context"),
    ("core.shared.demo_filter_dataset", "core.shared.demo_filter_dataset"),
    ("core.shared.demo_filter_store", "core.shared.demo_filter_store"),

    # Features: product_launch
    ("features.product_launch.wizard", "features.product_launch.wizard"),
    ("features.product_launch.sheet_reads", "features.product_launch.sheet_reads"),
    ("features.product_launch.watcher", "features.product_launch.watcher"),
    ("features.product_launch.sync", "features.product_launch.sync"),
    ("features.product_launch.core", "features.product_launch.core"),
    ("features.product_launch.auto_sync", "features.product_launch.auto_sync"),

    # Features: baseline
    ("features.baseline.comparison", "features.baseline.comparison"),
    ("features.baseline.engine", "features.baseline.engine"),
    ("features.baseline.engine_compare", "features.baseline.engine_compare"),
    ("features.baseline.io", "features.baseline.io"),
    ("features.baseline.manual", "features.baseline.manual"),
    ("features.baseline.wave_ops", "features.baseline.wave_ops"),

    # Features: autopilot
    ("features.autopilot.sync", "features.autopilot.sync"),
    ("features.autopilot.state", "features.autopilot.state"),
    ("features.autopilot.steps", "features.autopilot.steps"),
    ("features.autopilot.ui_config", "features.autopilot.ui_config"),
    ("features.autopilot.optimized", "features.autopilot.optimized"),

    # Features: dashboard / insights
    ("features.dashboard.analytics", "features.dashboard.analytics"),
    ("features.dashboard.cache", "features.dashboard.cache"),
    ("features.dashboard.revenue_trends", "features.dashboard.revenue_trends"),
    ("features.dashboard.analytics_6w", "features.dashboard.analytics_6w"),
    ("features.dashboard.analytics_reports", "features.dashboard.analytics_reports"),
    ("features.insights.analytics", "features.insights.analytics"),

    # Features: final_plan
    ("features.final_plan.engine", "features.final_plan.engine"),
    ("features.final_plan.inputs", "features.final_plan.inputs"),
    ("features.final_plan.sync", "features.final_plan.sync"),
    ("features.final_plan.hub_sync", "features.final_plan.hub_sync"),

    # Features: hub_launch
    ("features.hub_launch.sync", "features.hub_launch.sync"),
    ("features.hub_launch.auto_sync", "features.hub_launch.auto_sync"),

    # Features: master_data
    ("features.master_data.excel", "features.master_data.excel"),
    ("features.master_data.sync", "features.master_data.sync"),

    # Features: validation
    ("features.validation.output_validation", "features.validation.output_validation"),
    ("features.validation.history", "features.validation.history"),
    ("features.validation.input", "features.validation.input"),
    ("features.validation.service", "features.validation.service"),
    ("features.validation.rules", "features.validation.rules"),
    ("features.validation.runner", "features.validation.runner"),

    # Features: settings
    ("features.settings.service", "features.settings.service"),

    # Core db, security, utils, storage, ui
    ("core.database.engine", "core.database.engine"),
    ("core.database.models", "core.database.models"),
    ("core.security.tokens", "core.security.tokens"),
    ("core.security.auth", "core.security.auth"),
    ("core.security.permissions", "core.security.permissions"),
    ("core.utils.dataframe", "core.utils.dataframe"),
    ("core.utils.session_store", "core.utils.session_store"),
    ("core.storage.base", "core.storage.base"),
    ("core.storage.local", "core.storage.local"),
    ("core.storage.drive", "core.storage.drive"),
    ("core.storage.supabase", "core.storage.supabase"),
    ("core.storage.sync", "core.storage.sync"),
    ("core.storage.factory", "core.storage.factory"),
    ("core.storage.artifacts", "core.storage.artifacts"),
    ("core.ui.nav", "core.ui.nav"),
    ("core.ui.pages.optimized_baseline", "core.ui.pages.optimized_baseline"),

    # config, credentials, paths
    ("app.config", "app.config"),
    ("core.shared.cloud_paths", "core.shared.cloud_paths"),
    ("core.shared.google_credentials", "core.shared.google_credentials"),

    # App packages
    ("core.security.auth_cookies", "core.security.auth_cookies"),
    ("app.dependencies", "app.dependencies"),
    ("app.logging", "app.logging"),
    ("features.auth.router", "features.auth.router"),
    ("features.autopilot.router", "features.autopilot.router"),
    ("features.baseline.router", "features.baseline.router"),
    ("features.dashboard.router", "features.dashboard.router"),
    ("features.insights.router", "features.insights.router"),
    ("features.final_plan.router", "features.final_plan.router"),
    ("features.product_launch.router", "features.product_launch.router"),
    ("features.settings.router", "features.settings.router"),
    ("features.validation.router", "features.validation.router"),
    ("features.master_data.router", "features.master_data.router"),
    ("features.shared.demo_filter_router", "features.shared.demo_filter_router"),
]


def create_directories():
    print("Creating new directory structures...")
    dirs = [
        "app",
        "core/database",
        "core/security",
        "core/storage",
        "core/shared",
        "core/utils",
        "core/ui/pages",
        "features/auth",
        "features/autopilot",
        "features/baseline",
        "features/dashboard",
        "features/final_plan",
        "features/hub_launch",
        "features/insights",
        "features/master_data",
        "features/product_launch",
        "features/settings",
        "features/validation",
        "features/shared",
    ]
    for d in dirs:
        p = BACKEND_DIR / d
        p.mkdir(parents=True, exist_ok=True)
        init_py = p / "__init__.py"
        if not init_py.exists():
            init_py.touch()


def relocate_files():
    print("Relocating files to new structures...")
    for old_rel, new_rel in MAPPING.items():
        if old_rel == new_rel:
            print(f"Skipping copy for identical path: {old_rel}")
            continue
        old_path = BACKEND_DIR / old_rel
        new_path = BACKEND_DIR / new_rel
        if old_path.exists():
            print(f"Moving {old_rel} -> {new_rel}")
            new_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_path, new_path)
            # Remove old file
            old_path.unlink()
        else:
            print(f"Warning: Source file {old_rel} does not exist.")


def resolve_import_line(line: str) -> str:
    # Match from planning_suite.xxx import yyy [as zzz]
    m = re.match(r"^(\s*)from\s+planning_suite\.(\w+)\s+import\s+(\w+)(.*)$", line)
    if m:
        indent, subpkg, name, rest = m.groups()
        old_rel = f"src/planning_suite/{subpkg}/{name}.py"
        if old_rel in MAPPING:
            new_rel = MAPPING[old_rel]
            parts = new_rel.replace(".py", "").split("/")
            parent_pkg = ".".join(parts[:-1])
            mod_name = parts[-1]
            if " as " in rest:
                return f"{indent}from {parent_pkg} import {mod_name}{rest}\n"
            else:
                return f"{indent}from {parent_pkg} import {mod_name} as {name}{rest}\n"

    # Match from planning_suite.xxx.yyy import zzz [as aaa]
    m = re.match(r"^(\s*)from\s+planning_suite\.(\w+)\.(\w+)\s+import\s+(\w+)(.*)$", line)
    if m:
        indent, subpkg, name1, name2, rest = m.groups()
        old_rel = f"src/planning_suite/{subpkg}/{name1}.py"
        if old_rel in MAPPING:
            new_rel = MAPPING[old_rel]
            parts = new_rel.replace(".py", "").split("/")
            parent_pkg = ".".join(parts[:-1])
            mod_name = parts[-1]
            return f"{indent}from {parent_pkg}.{mod_name} import {name2}{rest}\n"
        # Check subpkg folder
        old_rel = f"src/planning_suite/{subpkg}/{name1}/{name2}.py"
        if old_rel in MAPPING:
            new_rel = MAPPING[old_rel]
            parts = new_rel.replace(".py", "").split("/")
            parent_pkg = ".".join(parts[:-1])
            mod_name = parts[-1]
            return f"{indent}from {parent_pkg} import {mod_name} as {name2}{rest}\n"

    # Match from planning_suite import xxx [as yyy]
    m = re.match(r"^(\s*)from\s+planning_suite\s+import\s+(\w+)(.*)$", line)
    if m:
        indent, name, rest = m.groups()
        old_rel = f"src/planning_suite/{name}.py"
        if old_rel in MAPPING:
            new_rel = MAPPING[old_rel]
            parts = new_rel.replace(".py", "").split("/")
            parent_pkg = ".".join(parts[:-1])
            mod_name = parts[-1]
            if " as " in rest:
                return f"{indent}from {parent_pkg} import {mod_name}{rest}\n"
            else:
                return f"{indent}from {parent_pkg} import {mod_name} as {name}{rest}\n"

    # Match from app.routers import xxx [as yyy]
    m = re.match(r"^(\s*)from\s+app\.routers\s+import\s+(\w+)(.*)$", line)
    if m:
        indent, name, rest = m.groups()
        old_rel = f"app/routers/{name}.py"
        if old_rel in MAPPING:
            new_rel = MAPPING[old_rel]
            parts = new_rel.replace(".py", "").split("/")
            parent_pkg = ".".join(parts[:-1])
            mod_name = parts[-1]
            if " as " in rest:
                return f"{indent}from {parent_pkg} import {mod_name}{rest}\n"
            else:
                return f"{indent}from {parent_pkg} import {mod_name} as {name}{rest}\n"

    # General replacements
    for old_str, new_str in STRING_REPLACEMENTS:
        line = line.replace(old_str, new_str)
    return line


def rewrite_imports_in_file(file_path: Path):
    if not file_path.is_file() or file_path.suffix != ".py":
        return
    
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=False)
    except UnicodeDecodeError:
        return

    new_lines = []
    for line in lines:
        new_lines.append(resolve_import_line(line))
        
    content = "\n".join(new_lines) + "\n"
    file_path.write_text(content, encoding="utf-8")
    print(f"Updated imports in: {file_path.relative_to(BACKEND_DIR)}")


def rewrite_all_imports():
    print("Scanning python files to rewrite imports...")
    # Walk through entire backend folder
    for root, _, files in os.walk(BACKEND_DIR):
        root_path = Path(root)
        if "venv" in root_path.parts or ".pytest_cache" in root_path.parts:
            continue
        for file in files:
            if file.endswith(".py"):
                rewrite_imports_in_file(root_path / file)


def clean_unused_directories():
    print("Cleaning up old directories...")
    # Remove app/routers directory if empty
    routers_dir = BACKEND_DIR / "app" / "routers"
    if routers_dir.exists() and not any(routers_dir.iterdir()):
        shutil.rmtree(routers_dir)
        print("Removed empty app/routers/")

    # Remove src/planning_suite/ completely
    old_src = BACKEND_DIR / "src"
    if old_src.exists():
        shutil.rmtree(old_src)
        print("Removed legacy src/ directory")


def main():
    create_directories()
    relocate_files()
    rewrite_all_imports()
    clean_unused_directories()
    print("Relocation completed successfully!")


if __name__ == "__main__":
    main()
