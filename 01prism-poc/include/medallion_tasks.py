import os
import json
import pandas as pd
from datetime import datetime

DATA_DIR = os.getenv("AIRFLOW_HOME", "/opt/airflow") + "/data"

def extract_raw_data(**context):
    os.makedirs(f"{DATA_DIR}/bronze", exist_ok=True)
    
    # Simulate raw incoming data (e.g., e-commerce transactions / logs)
    raw_records = [
        {"transaction_id": 101, "customer_id": 1, "product": "Laptop", "amount": 1200.00, "timestamp": "2026-08-01 10:00:00", "status": "completed"},
        {"transaction_id": 102, "customer_id": 2, "product": "Mouse", "amount": 25.50, "timestamp": "2026-08-01 10:05:00", "status": "completed"},
        {"transaction_id": 103, "customer_id": 1, "product": "Keyboard", "amount": 75.00, "timestamp": "2026-08-01 10:10:00", "status": "cancelled"},
        {"transaction_id": 104, "customer_id": 3, "product": "Monitor", "amount": 300.00, "timestamp": "2026-08-01 10:15:00", "status": "completed"},
        {"transaction_id": 105, "customer_id": 4, "product": "USB Cable", "amount": 12.99, "timestamp": "2026-08-01 10:20:00", "status": "completed"}
    ]
    
    file_path = f"{DATA_DIR}/bronze/raw_transactions.json"
    with open(file_path, "w") as f:
        json.dump(raw_records, f, indent=2)
    print(f"Bronze layer ingestion complete. Saved to {file_path}")

def transform_silver_data(**context):
    os.makedirs(f"{DATA_DIR}/silver", exist_ok=True)
    bronze_path = f"{DATA_DIR}/bronze/raw_transactions.json"
    
    df = pd.read_json(bronze_path)
    
    # Silver Layer: Clean data, filter out cancelled transactions, normalize timestamps
    df_clean = df[df["status"] == "completed"].copy()
    df_clean["timestamp"] = pd.to_datetime(df_clean["timestamp"])
    df_clean["processed_at"] = datetime.utcnow()
    
    # Drop sensitive or redundant columns if any, handle nulls
    df_clean = df_clean.dropna()
    
    silver_path = f"{DATA_DIR}/silver/clean_transactions.parquet"
    df_clean.to_parquet(silver_path, index=False)
    print(f"Silver layer transformation complete. Saved to {silver_path}")

def aggregate_gold_data(**context):
    os.makedirs(f"{DATA_DIR}/gold", exist_ok=True)
    silver_path = f"{DATA_DIR}/silver/clean_transactions.parquet"
    
    df = pd.read_parquet(silver_path)
    
    # Gold Layer: Business-level aggregation (Total revenue and purchase count per customer)
    gold_df = df.groupby("customer_id").agg(
        total_spent=("amount", "sum"),
        purchase_count=("transaction_id", "count"),
        avg_order_value=("amount", "mean")
    ).reset_index()
    
    gold_path = f"{DATA_DIR}/gold/customer_metrics.csv"
    gold_df.to_csv(gold_path, index=False)
    print(f"Gold layer aggregation complete. Saved to {gold_path}")
