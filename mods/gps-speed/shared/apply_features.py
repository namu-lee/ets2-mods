import argparse
import json
from pathlib import Path

from view.apply import apply_gps_view


GPS_FEATURES = {"view": apply_gps_view}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply the selected GPS features to the staged mod source.")
    parser.add_argument("staging_directory", type=Path)
    args = parser.parse_args()

    config_path = Path.cwd() / "mod.json"
    features = json.loads(config_path.read_text(encoding="utf-8")).get("features", [])
    if not isinstance(features, list):
        parser.error(f"Set features to a list in {config_path}.")
    if any(not isinstance(feature, str) or feature not in GPS_FEATURES for feature in features):
        parser.error(f"Unsupported features in {config_path}. Choose from {', '.join(GPS_FEATURES)}.")
    if len(features) != len(set(features)):
        parser.error(f"List each GPS feature once in {config_path}.")

    for feature in features:
        GPS_FEATURES[feature](args.staging_directory)
