import html
import urllib.parse

def encode_file_path(path):
    """
    Encode file path for safe use in HTML and URLs
    
    Args:
        path (str): Original file path
    
    Returns:
        str: Encoded file path with HTML entities and URL encoding
    """
    # First, replace backslashes with forward slashes for consistency
    path = path.replace('\\', '/')
    
    # URL encode the path
    url_encoded_path = urllib.parse.quote(path)
    
    # Convert to HTML entities for additional safety
    html_encoded_path = html.escape(url_encoded_path)
    
    return html_encoded_path

def decode_file_path(encoded_path):
    """
    Decode file path from HTML entities and URL encoding
    
    Args:
        encoded_path (str): Encoded file path
    
    Returns:
        str: Original file path
    """
    # Unescape HTML entities
    html_decoded_path = html.unescape(encoded_path)
    
    # URL decode the path
    path = urllib.parse.unquote(html_decoded_path)
    
    return path
