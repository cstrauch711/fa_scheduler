import pandas as pd
import readline

## IATA Code Fixing and TimeZones
data = pd.read_csv("data/iata_timezones.csv")
iata_codes = data['iata'].to_list()

UNITED_HUBS = {"ORD", "IAH", "EWR", "DEN", "SFO", "LAX", "CLE", "GUM", "IAD"}

# 1. Define your specific visual OCR confusion costs.
# Baseline cost for a standard mismatch is 10.
# A likely OCR mistake costs much less (e.g., 2).
OCR_GLITCH_COSTS = {
    ('T', 'I'): 2,  # Underline turns T into I
    ('I', 'T'): 2,
    ('M', 'H'): 2,
    ('H', 'M'): 2,
    ('E', 'F'): 2,
    ('F', 'E'): 2,
    ('I', 'J'): 2,
    ('J', 'I'): 2,
}

def get_substitution_cost(char_a, char_b):
    if char_a == char_b:
        return 0
    return OCR_GLITCH_COSTS.get((char_a, char_b), 10)

def custom_weighted_distance(str1, str2, insert_cost=10, delete_cost=10):
    """Calculates Levenshtein distance using our custom OCR substitution weights."""
    len1, len2 = len(str1), len(str2)
    
    # Initialize the DP matrix
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    for i in range(len1 + 1):
        dp[i][0] = i * delete_cost
    for j in range(len2 + 1):
        dp[0][j] = j * insert_cost
        
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            char_a = str1[i - 1]
            char_b = str2[j - 1]
            
            sub_cost = get_substitution_cost(char_a, char_b)
            
            dp[i][j] = min(
                dp[i - 1][j] + delete_cost,      # Deletion
                dp[i][j - 1] + insert_cost,      # Insertion
                dp[i - 1][j - 1] + sub_cost      # Custom Substitution
            )
            
    return dp[len1][len2]

def find_closest_iata(ocr_input, valid_set=iata_codes, max_distance_cutoff=15):
    ocr_input = ocr_input.upper().strip()
    
    if ocr_input in valid_set:
        return ocr_input

    best_match = None
    lowest_distance = float('inf')

    for valid_code in valid_set:
        dist = custom_weighted_distance(ocr_input, valid_code)

        if valid_code in UNITED_HUBS:
            dist -= 3
        
        if dist < lowest_distance:
            lowest_distance = dist
            best_match = valid_code

    if lowest_distance <= max_distance_cutoff:
        return best_match
        
    return ocr_input

def airport_with_tz(code):
    if code not in iata_codes:
        #hamming
        code = find_closest_iata(code)
    # Timezone Lookup
    tz = data.loc[data['iata'] == code, 'timezone'].values[0]
    return (code, tz)

def prompt_for_correction(original_text: str) -> str:
    """Displays original_text pre-filled in the terminal prompt.

    Allows the user to press Enter to accept or edit inline.
    """

    def hook():
        # Pre-fills the input buffer with the extracted text
        readline.insert_text(original_text)
        readline.redisplay()

    readline.set_startup_hook(hook)
    try:
        # Prompt the user; press Enter to accept or edit directly
        corrected_text = input("Review text (Enter to keep / edit to fix): ")
    finally:
        # Always remove the hook so future input() calls aren't affected
        readline.set_startup_hook()

    return corrected_text