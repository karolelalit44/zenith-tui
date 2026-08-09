import unittest
from datetime import datetime
from airflow.models import DagBag
from include.medallion_tasks import bronze_ingest, silver_transform, gold_aggregate

class TestPrismDagIntegrity(unittest.TestCase):
    def setUp(self):
        self.dagbag = DagBag(dag_folder="prism-poc/dags", include_examples=False)

    def test_no_import_errors(self):
        self.assertEqual(len(self.dagbag.import_errors), 0, f"DAG import errors: {self.dagbag.import_errors}")

    def test_dag_count(self):
        # We expect 2 DAGs: prism_operational_dag and prism_analytics_dag
        expected_dags = ['prism_operational_dag', 'prism_analytics_dag']
        for dag_id in expected_dags:
            self.assertIn(dag_id, self.dagbag.dags, f"DAG {dag_id} missing from DagBag")

    def test_medallion_tasks_execution(self):
        res_b = bronze_ingest('bronze_test')
        self.assertEqual(res_b['status'], 'success')
        
        res_s = silver_transform()
        self.assertEqual(res_s['status'], 'success')
        
        res_g = gold_aggregate()
        self.assertEqual(res_g['status'], 'success')

if __name__ == '__main__':
    unittest.main()
