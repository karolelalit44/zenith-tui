import csv
import os
import sys


def analyze_prices(csv_path, target_day):
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    prices = []
    
    with open(csv_path, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            try:
                day_val = int(row['day'])
                if day_val == int(target_day):
                    prices.append(float(row['price']))
            except (ValueError, KeyError):
                continue

    if not prices:
        print(f"No product price data found for day: {target_day}")
        return

    avg_price = sum(prices) / len(prices)
    highest_price = max(prices)
    lowest_price = min(prices)

    print(f"\n--- Price Analysis for Day {target_day} ---")
    print(f"Total entries found: {len(prices)}")
    print(f"Average Price : ${avg_price:.2f}")
    print(f"Highest Price : ${highest_price:.2f}")
    print(f"Lowest Price  : ${lowest_price:.2f}")

if __name__ == "__main__":
    csv_file = "prices.csv"
    
    if len(sys.argv) > 1:
        day_input = sys.argv[1]
    else:
        day_input = input("Enter the day number (e.g. 1, 10, 15): ")
        
    analyze_prices(csv_file, day_input)
