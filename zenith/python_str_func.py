def analyze_string():
    """
    Analyzes a hardcoded string and returns:
    - Count of numeric characters
    - Count of vowels (a, e, i, o, u, both cases)
    - Duplicate characters (characters appearing more than once)
    """
    # Static hardcoded string
    text = "Hello World 2024! This is a test string with numbers 12345 and duplicates: letters appear twice."

    # Count numeric characters
    numeric_count = sum(1 for char in text if char.isdigit())

    # Count vowels (both uppercase and lowercase)
    vowels = set('aeiouAEIOU')
    vowel_count = sum(1 for char in text if char in vowels)

    # Find duplicate characters (case-sensitive)
    char_frequency = {}
    for char in text:
        if char != ' ':  # Optionally ignore spaces; remove this line to include spaces
            char_frequency[char] = char_frequency.get(char, 0) + 1

    duplicates = {char: count for char, count in char_frequency.items() if count > 1}
    duplicate_count = len(duplicates)

    # Return results as a dictionary
    return {
        "string": text,
        "numeric_count": numeric_count,
        "vowel_count": vowel_count,
        "duplicate_characters": duplicates,
        "duplicate_count": duplicate_count,
        "total_length": len(text)
    }


if __name__ == "__main__":
    result = analyze_string()
    print(f"String: {result['string']}")
    print(f"Total length: {result['total_length']}")
    print(f"Numeric character count: {result['numeric_count']}")
    print(f"Vowel count: {result['vowel_count']}")
    print(f"Duplicate character count (unique chars appearing >1 time): {result['duplicate_count']}")
    print(f"Duplicate characters and their frequencies: {result['duplicate_characters']}")
