# Weather CLI App

A simple Python CLI application that reads temperature data from a JSON file and computes the minimum, average, and maximum temperatures.

## Files

- `weather.py`: Main CLI application script.
- `temps.json`: Sample temperature data.
- `test_weather.py`: Unit test suite.

## Requirements

- Python 3.6+

## How to Run

1. Navigate to the `weather` directory:
   ```bash
   cd weather
   ```

2. Run the CLI app with default `temps.json`:
   ```bash
   python weather.py
   ```

   Or specify a custom JSON file:
   ```bash
   python weather.py --file temps.json
   ```

## How to Run Tests

Run unit tests using unittest:
```bash
python -m unittest test_weather.py
```
