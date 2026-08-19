from datetime import datetime, timedelta
import os
from airflow import DAG
from airflow.operators.bash import BashOperator

# Path to the root of your project
# Ensure this is correctly set to where your forecast-pipeline-v2 repository lives on the Airflow worker
PROJECT_ROOT = os.environ.get("FORECAST_PIPELINE_ROOT", "/path/to/your/forecast-pipeline-v2")

default_args = {
    'owner': 'data_team',
    'depends_on_past': False,
    'start_date': datetime(2026, 8, 1),
    'email_on_failure': False, # Disabled as requested
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'forecast_pipeline_daily',
    default_args=default_args,
    description='Runs the Forecast Pipeline (Raw Data -> Baseline -> FF Hub Automation)',
    schedule_interval='30 2 * * *', # 2:30 AM UTC = 8:00 AM IST
    catchup=False,
    tags=['forecast', 'pipeline'],
) as dag:

    # Execute the master runner script
    # We navigate to the project root and run it to ensure relative paths resolve correctly
    run_master_pipeline = BashOperator(
        task_id='run_master_pipeline',
        bash_command=f'cd {PROJECT_ROOT} && python backend/pipeline/run_pipeline.py',
    )

    run_master_pipeline
