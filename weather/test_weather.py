import json
import os
import tempfile
import unittest

from weather import calculate_stats, load_data


class TestWeatherCLI(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8", suffix=".json")
        sample_data = [
            {"date": "2023-01-01", "temp": 10.0},
            {"date": "2023-01-02", "temp": 20.0},
            {"date": "2023-01-03", "temp": 30.0}
        ]
        json.dump(sample_data, self.temp_file)
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_load_data(self):
        data = load_data(self.temp_file.name)
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["temp"], 10.0)

    def test_calculate_stats(self):
        data = [
            {"temp": 10},
            {"temp": 20},
            {"temp": 30}
        ]
        stats = calculate_stats(data)
        self.assertEqual(stats["min"], 10)
        self.assertEqual(stats["max"], 30)
        self.assertEqual(stats["avg"], 20.0)

    def test_empty_data(self):
        with self.assertRaises(ValueError):
            calculate_stats([])

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_data("non_existent_file_12345.json")

if __name__ == "__main__":
    unittest.main()
