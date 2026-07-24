# string_analyzer.py

# Function to analyze a string for numeric characters and vowels
def analyze_string(input_string):
    """Analyzes the input string for numeric characters and vowels.\n
    Args:\n        input_string (str): The string to be analyzed.\n
    Returns:\n        tuple: A tuple containing the count of numeric characters and vowels.\n    """
    numeric_count = sum(c.isdigit() for c in input_string)
    vowel_count = sum(1 for c in input_string.lower() if c in 'aeiou')
    return numeric_count, vowel_count

# Main program
if __name__ == "__main__":
    input_message = input("Please enter a string message: ")
    numeric, vowels = analyze_string(input_message)
    print("\nAnalysis Results:\n---------------")
    print(f"Numeric Characters: {numeric}")
    print(f"Vowels: {vowels}")

# --- Examples for Testing ---
# Uncomment and modify the input_message variable below for quick testing
# input_message = "Hello123World456"
# numeric, vowels = analyze_string(input_message)
# print(f"Numeric: {numeric}, Vowels: {vowels}")
