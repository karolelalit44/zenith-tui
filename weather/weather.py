import argparse
import json
import sys
from pathlib import Path


def load_data(filepath="temps.json"):
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {filepath}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def calculate_stats(data):
    temps = [entry["temp"] for entry in data if "temp" in entry]
    if not temps:
        raise ValueError("No temperature data found.")
    return {
        "min": min(temps),
        "max": max(temps),
        "avg": sum(temps) / len(temps)
    }

def main():
    parser = argparse.ArgumentParser(description="Weather CLI - Calculate min, max, and average temperatures.")
    parser.add_argument("--file", default="temps.json", help="Path to JSON data file")
    args = parser.parse_args()

    try:
        data = load_data(args.file)
        stats = calculate_stats(data)
        print(f"Temperature Statistics (from {args.file}):")
        print(f"  Minimum: {stats['min']}°C")
        print(f"  Average: {stats['avg']:.2f}°C")
        print(f"  Maximum: {stats['max']}°C")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
