# Prism POC - Airflow Medallion Architecture

A production-ready Apache Airflow proof-of-concept implementing the Medallion Architecture (Bronze -> Silver -> Gold) with 2 dependent DAGs, 3 dependent trigger/ingestion tasks, scheduled execution, and automated testing.

## Project Structure

```text
prism-poc/
├── dags/
│   ├── operational_dag.py     # DAG 1: Scheduled ingestion with 3 dependent trigger tasks
│   └── medallion_pipeline_dag.py # DAG 2: Silver & Gold transformation dependent on Operational DAG
├── include/
│   └── medallion_tasks.py     # Python business logic for Bronze, Silver, Gold layers
├── tests/
│   └── test_dags.py           # Unit tests validating DAG integrity & medallion task execution
├── Dockerfile                 # Custom Airflow Docker image builder
├── docker-compose.yaml        # Complete containerized Airflow stack (Celery/Local executor setup)
└── README.md                  # Project documentation
```

## Architecture & Features

1. **Medallion Architecture**:
   - **Bronze Layer**: Raw data ingestion (`operational_dag.py` with 3 dependent trigger/ingestion tasks: API, Stream, DB Snapshot).
   - **Silver Layer**: Cleaned, filtered, and standardized data (`medallion_pipeline_dag.py`).
   - **Gold Layer**: Aggregated, business-ready dimensional data models (`medallion_pipeline_dag.py`).

2. **DAGs & Dependencies**:
   - **DAG 1 (`prism_operational_dag`)**: Scheduled hourly. Runs 3 dependent trigger tasks (`trigger_source_api` >> `trigger_stream_ingest` >> `trigger_db_snapshot`).
   - **DAG 2 (`prism_analytics_dag`)**: Triggered or dependent on DAG 1 completion. Executes Silver transformation followed by Gold aggregation (`silver_transformation_task` >> `gold_aggregation_task`).

## Getting Started & Running Containerized Airflow

### Prerequisites
- Docker & Docker Compose

### 1. Initialize Airflow DB & Environment
```bash
cd prism-poc
docker compose up airflow-init
```

### 2. Start the Full Airflow Stack
```bash
docker compose up -d
```

### 3. Access Airflow Webserver
Open your browser at [http://localhost:8080](http://localhost:8080)
- **Username**: `airflow`
- **Password**: `airflow`

### 4. Run Automated Tests
You can run the unit test suite inside the container or Python environment:
```bash
docker compose run --rm airflow-worker python -m unittest discover -s tests
```
