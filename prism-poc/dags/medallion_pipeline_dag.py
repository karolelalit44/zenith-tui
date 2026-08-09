from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from include.medallion_tasks import extract_raw_data, transform_silver_data, aggregate_gold_data

default_args = {
    "owner": "prism-team",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="prism_medallion_pipeline",
    default_args=default_args,
    description="Scheduled Medallion Architecture Pipeline (Bronze -> Silver -> Gold)",
    schedule_interval="@daily",
    start_datetime=datetime(2026, 1, 1),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["prism", "medallion", "scheduled"],
) as dag:

    bronze_task = PythonOperator(
        task_id="extract_bronze",
        python_callable=extract_raw_data,
    )

    silver_task = PythonOperator(
        task_id="transform_silver",
        python_callable=transform_silver_data,
    )

    gold_task = PythonOperator(
        task_id="aggregate_gold",
        python_callable=aggregate_gold_data,
    )

    bronze_task >> silver_task >> gold_task
