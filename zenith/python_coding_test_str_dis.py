"""
String Analysis Module
Analyzes a hardcoded string and returns counts of:
- Numeric characters
- Vowels (both uppercase and lowercase)
- Duplicate characters (characters appearing more than once)
"""


def analyze_string():
    """
    Analyzes the hardcoded string and returns a dictionary with counts.
    
    Returns:
        dict: Contains counts of numeric characters, vowels, and duplicates
    """
    # Static hardcoded string
    input_string = "Hello World 2024! This is a Test String with Numbers 12345 and Vowels AEIOUaeiou."
    
    # Count numeric characters (digits 0-9)
    numeric_count = sum(1 for char in input_string if char.isdigit())
    
    # Count vowels (a, e, i, o, u - both uppercase and lowercase)
    vowels_set = set('aeiouAEIOU')
    vowel_count = sum(1 for char in input_string if char in vowels_set)
    
    # Count duplicate characters (characters appearing more than once)
    char_frequency = {}
    for char in input_string:
        char_frequency[char] = char_frequency.get(char, 0) + 1
    
    duplicate_count = sum(1 for count in char_frequency.values() if count > 1)
    duplicate_chars = {char: count for char, count in char_frequency.items() if count > 1}
    
    # Return results as a dictionary
    results = {
        "input_string": input_string,
        "numeric_count": numeric_count,
        "vowel_count": vowel_count,
        "duplicate_count": duplicate_count,
        "duplicate_characters": duplicate_chars
    }
    
    return results


if __name__ == "__main__":
    # Execute analysis and display results
    analysis_results = analyze_string()
    
    print("=" * 60)
    print("STRING ANALYSIS RESULTS")
    print("=" * 60)
    print(f"Input String: {analysis_results['input_string']}")
    print("-" * 60)
    print(f"Numeric Characters Count: {analysis_results['numeric_count']}")
    print(f"Vowel Characters Count:   {analysis_results['vowel_count']}")
    print(f"Duplicate Characters Count: {analysis_results['duplicate_count']}")
    print("-" * 60)
    print("Duplicate Characters (with frequency):")
    for char, count in sorted(analysis_results['duplicate_characters'].items()):
        print(f"  '{char}' appears {count} times")
    print("=" * 60)
