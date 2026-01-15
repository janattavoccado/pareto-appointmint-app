"""
PHONE NUMBER NORMALIZATION FIX FOR booking_agent.py

Add this function after parse_time_string() around line 345.
Then update the extract_reservation_info() prompt and add normalization call.
"""

# ============================================================================
# ADD THIS FUNCTION after parse_time_string() (around line 345)
# ============================================================================

def normalize_phone_number(phone_str: str) -> str:
    """
    Normalize phone number from spoken format to numeric format.
    Examples:
    - "plus 4 6 4 0 8 0 2 3" -> "+46408023"
    - "plus 385 91 123 4567" -> "+385911234567"
    - "0 9 1 1 2 3 4 5 6 7" -> "0911234567"
    - "091-123-4567" -> "0911234567"
    - "oh nine one two three" -> "09123"
    """
    if not phone_str:
        return phone_str
    
    # Convert to lowercase for processing
    phone = phone_str.lower().strip()
    
    # Word to digit mapping
    word_to_digit = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        'oh': '0', 'o': '0', 'ten': '10'
    }
    
    # Replace word numbers with digits
    for word, digit in word_to_digit.items():
        # Use word boundaries to avoid partial matches
        phone = phone.replace(f' {word} ', f' {digit} ')
        phone = phone.replace(f' {word}', f' {digit}')
        phone = phone.replace(f'{word} ', f'{digit} ')
        if phone == word:
            phone = digit
    
    # Handle "plus" at the beginning
    has_plus = 'plus' in phone or phone.startswith('+')
    
    # Remove all non-digit characters
    result = ''
    for char in phone:
        if char.isdigit():
            result += char
    
    # Add + if it was there originally
    if has_plus and result and not result.startswith('+'):
        result = '+' + result
    
    return result if result else phone_str


# ============================================================================
# UPDATE the extraction prompt in extract_reservation_info() around line 382
# Change the phone line from:
#   - phone: Phone number (any format)
# To:
#   - phone: Phone number (convert spoken digits to numbers, e.g., "plus four six" -> "+46", "oh nine one" -> "091")
# ============================================================================


# ============================================================================
# ADD phone normalization call after extracting phone
# In the step handling code, wherever you set res.phone = extracted['phone']
# Change it to: res.phone = normalize_phone_number(extracted['phone'])
#
# For example, around line 558-559, change:
#   if extracted.get('phone'):
#       res.phone = extracted['phone']
# To:
#   if extracted.get('phone'):
#       res.phone = normalize_phone_number(extracted['phone'])
# ============================================================================


# ============================================================================
# QUICK PATCH: Find and replace all occurrences
# Search for: res.phone = extracted['phone']
# Replace with: res.phone = normalize_phone_number(extracted['phone']) if extracted.get('phone') else None
#
# Or use this simpler approach - normalize in the extraction function itself
# ============================================================================
