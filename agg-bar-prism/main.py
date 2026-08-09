from fastapi import FastAPI, HTTPException
import pandas as pd
import os
from pathlib import Path

app = FastAPI(
    title="agg-bar-prism",
    description="Medallion Architecture (Bronze, Silver, Gold) Data Pipeline & API",
    version="1.0.0"
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_CSV_PATH = DATA_DIR / "raw_sales.csv"
BRONZE_CSV_PATH = DATA_DIR / "bronze_sales.csv"
SILVER_CSV_PATH = DATA_DIR / "silver_sales.csv"
GOLD_CSV_PATH = DATA_DIR / "gold_sales.csv"

@app.on_event("startup")
def startup_event():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RAW_CSV_PATH.exists():
        from .data_generator import generate_raw_csv
        generate_raw_csv(str(RAW_CSV_PATH))

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "agg-bar-prism",
        "data_dir_exists": DATA_DIR.exists(),
        "raw_data_exists": RAW_CSV_PATH.exists()
    }

@app.post("/bronze")
def process_bronze_layer():
    """
    Bronze Layer: Ingests raw CSV data, performs basic schema validation 
    and adds ingestion timestamp / row IDs.
    """
    if not RAW_CSV_PATH.exists():
        raise HTTPException(status_code=404, detail="Raw CSV source data not found.")
    
    try:
        df = pd.read_csv(RAW_CSV_PATH)
        # Manipulation: Add ingestion metadata, strip whitespace from columns
        df.columns = [c.strip().lower() for c in df.columns]
        df["ingested_at"] = pd.Timestamp.now().isoformat()
        df["bronze_record_id"] = [f"BRZ-{i:04d}" for i in range(len(df))]
        
        df.to_csv(BRONZE_CSV_PATH, index=False)
        
        return {
            "layer": "bronze",
            "message": "Raw data successfully ingested into Bronze layer",
            "rows_processed": len(df),
            "output_file": str(BRONZE_CSV_PATH.name),
            "sample": df.head(3).to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing Bronze layer: {str(e)}")

@app.post("/silver")
def process_silver_layer():
    """
    Silver Layer: Cleans bronze data, handles missing values, removes duplicates,
    and standardizes data types (e.g. converting date and numerical fields).
    """
    if not BRONZE_CSV_PATH.exists():
        # Fallback to run bronze if not yet run
        process_bronze_layer()
        
    try:
        df = pd.read_csv(BRONZE_CSV_PATH)
        
        # Manipulation: Clean data
        # 1. Drop duplicates
        initial_count = len(df)
        df = df.drop_duplicates()
        
        # 2. Fill missing numeric values with median or 0
        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
        if "quantity" in df.columns:
            df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)
            
        # 3. Standardize text fields
        if "customer" in df.columns:
            df["customer"] = df["customer"].astype(str).str.title().str.strip()
        if "product" in df.columns:
            df["product"] = df["product"].astype(str).str.upper().str.strip()
            
        # 4. Add calculated total_price
        if "amount" in df.columns and "quantity" in df.columns:
            df["total_price"] = df["amount"] * df["quantity"]
            
        df["silver_cleaned_at"] = pd.Timestamp.now().isoformat()
        df.to_csv(SILVER_CSV_PATH, index=False)
        
        return {
            "layer": "silver",
            "message": "Data cleaned and transformed into Silver layer",
            "initial_rows": initial_count,
            "cleaned_rows": len(df),
            "duplicates_removed": initial_count - len(df),
            "output_file": str(SILVER_CSV_PATH.name),
            "sample": df.head(3).to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing Silver layer: {str(e)}")

@app.post("/gold")
def process_gold_layer():
    """
    Gold Layer: Aggregates silver data for business reporting 
    (e.g., total sales by product and customer summary metrics).
    """
    if not SILVER_CSV_PATH.exists():
        process_silver_layer()
        
    try:
        df = pd.read_csv(SILVER_CSV_PATH)
        
        if "product" not in df.columns or "total_price" not in df.columns:
            raise HTTPException(status_code=400, detail="Required columns missing in Silver data.")
            
        # Manipulation: Aggregate sales by product
        gold_df = df.groupby("product").agg(
            total_sales=("total_price", "sum"),
            avg_amount=("amount", "mean"),
            total_units_sold=("quantity", "sum"),
            transaction_count=("product", "count")
        ).reset_index()
        
        gold_df["gold_aggregated_at"] = pd.Timestamp.now().isoformat()
        gold_df = gold_df.sort_values(by="total_sales", ascending=False)
        
        gold_df.to_csv(GOLD_CSV_PATH, index=False)
        
        return {
            "layer": "gold",
            "message": "Business aggregations calculated into Gold layer",
            "summary_records": len(gold_df),
            "output_file": str(GOLD_CSV_PATH.name),
            "data": gold_df.to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing Gold layer: {str(e)}")
