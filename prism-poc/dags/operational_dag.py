from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor
from include.medallion_tasks import bronze_ingest, silver_transform, gold_aggregate

default_args = {
    'owner': 'prism',
    'depends_on_past': False,
    'email_on_failure': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

with DAG(
    'prism_operational_dag',
    default_args=default_args,
    description='Operational DAG with 3 Triggers / Tasks & Scheduled Medallion Bronze layer',
    schedule_interval='@hourly',
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['prism', 'bronze', 'operational'],
) as dag:

    t1_trigger = PythonOperator(
        task_id='trigger_source_api',
        python_callable=bronze_ingest,
        op_kwargs={'layer': 'bronze_api'},
    )

    t2_trigger = PythonOperator(
        task_id='trigger_stream_ingest',
        python_callable=bronze_ingest,
        op_kwargs={'layer': 'bronze_stream'},
    )

    t3_trigger = PythonOperator(
        task_id='trigger_db_snapshot',
        python_callable=bronze_ingest,
        op_kwargs={'layer': 'bronze_db'},
    )

    # 3 triggers dependent on each other in sequence/parallel workflow
    t1_trigger >> t2_trigger >> t3_trigger
