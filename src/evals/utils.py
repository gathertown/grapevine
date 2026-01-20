import os
import re

RUNS_DIR = "src/evals/runs"

GATHER_INTERNAL_STAGING_TENANT_ID = "878f6fb522b441d1"  # as of 11/4/25


def find_latest_experiment(runs_dir: str = "runs") -> str | None:
    """Find the latest experiment directory."""
    if not os.path.exists(runs_dir):
        return None

    # Look for experiment directories (experiment_YYYYMMDD_HHMMSS)
    experiment_dirs = [
        os.path.join(runs_dir, d)
        for d in os.listdir(runs_dir)
        if os.path.isdir(os.path.join(runs_dir, d)) and d.startswith("experiment_")
    ]

    if not experiment_dirs:
        return None

    # Sort by the timestamp in the directory name (experiment_YYYYMMDD_HHMMSS)
    def extract_timestamp(dir_path):
        dir_name = os.path.basename(dir_path)
        try:
            # Use regex to find timestamp pattern (YYYYMMDD_HHMMSS) anywhere in the name
            match = re.search(r"\d{8}_\d{6}", dir_name)
            if match:
                return match.group()
            return "00000000_000000"  # fallback if no timestamp found
        except:
            return "00000000_000000"  # fallback for malformed names

    return max(experiment_dirs, key=extract_timestamp)
