import os
import sys
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Ensure we're running from the root of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_DIR = os.path.join(BASE_DIR, "pipeline")

SCRIPTS_TO_RUN = [
    "raw_data_6w.py",
    "baseline_parquet.py",
    "ff_hub_automation.py"
]

def run_script(script_name):
    script_path = os.path.join(PIPELINE_DIR, script_name)
    if not os.path.exists(script_path):
        logging.error(f"Script not found: {script_path}")
        return False
        
    logging.info(f"==================================================")
    logging.info(f"Starting {script_name}...")
    start_time = time.time()
    
    try:
        # Run the script using the current Python executable
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.dirname(BASE_DIR), # Run from project root
            check=True,
            capture_output=True,
            text=True
        )
        
        duration = time.time() - start_time
        logging.info(f"Successfully completed {script_name} in {duration:.2f} seconds.")
        return True
        
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        logging.error(f"FAILED {script_name} after {duration:.2f} seconds.")
        logging.error(f"Exit code: {e.returncode}")
        logging.error(f"STDOUT:\n{e.stdout}")
        logging.error(f"STDERR:\n{e.stderr}")
        return False

def main():
    logging.info("Starting Master Pipeline Runner")
    total_start_time = time.time()
    
    for script in SCRIPTS_TO_RUN:
        success = run_script(script)
        if not success:
            logging.error("Pipeline aborted due to failure.")
            sys.exit(1)
            
    total_duration = time.time() - total_start_time
    logging.info(f"==================================================")
    logging.info(f"Pipeline completed successfully in {total_duration:.2f} seconds.")
    sys.exit(0)

if __name__ == "__main__":
    main()
