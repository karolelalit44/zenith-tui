import csv
import os

def create_sample_csv():
    os.makedirs("data", exist_ok=True)
    filepath = "data/raw_transactions.csv"
    headers = ["transaction_id", "timestamp", "customer_id", "product", "category", "amount", "store_location"]
    rows = [
        ["T1001", "2026-08-01 10:15:00", "C001", "Laptop", "Electronics", "1200.50", "New York"],
        ["T1002", "2026-08-01 10:20:00", "C002", "Coffee Maker", "Appliance", "89.99", "Chicago"],
        ["T1003", "2026-08-01 11:05:00", "C003", "Running Shoes", "Sports", "120.00", "New York"],
        ["T1004", "2026-08-01 12:30:00", "C004", "Desk Chair", "Furniture", "250.00", "San Francisco"],
        ["T1005", "2026-08-01 13:15:00", "C001", "Mouse", "Electronics", "45.00", "New York"],
        ["T1006", "2026-08-01 14:00:00", "C005", "Notebook", "Stationery", "12.50", "Chicago"],
        ["T1007", "2026-08-01 15:20:00", "C002", "Blender", "Appliance", "65.00", "Chicago"],
        ["T1008", "2026-08-01 16:45:00", "C006", "Yoga Mat", "Sports", "35.00", "San Francisco"],
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"Created {filepath}")

if __name__ == "__main__":
    create_sample_csv()
