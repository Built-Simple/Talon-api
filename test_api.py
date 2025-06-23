#!/usr/bin/env python3
"""Test the Talon API locally"""

import requests
import json

# Test the API
BASE_URL = "http://localhost:5000"

print("Testing Talon API...")
print("=" * 50)

# 1. Test health check
print("\n1. Testing health check...")
try:
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
    print("Make sure the API is running: python talon_api.py")
    exit(1)

# 2. Test code analysis (free tier)
print("\n2. Testing code analysis...")
test_code = """
import requests
import pandas

def process_data():
    data = None
    result = data.process()  # This will cause AttributeError
    
    x = undefined_variable  # This will cause NameError
    
    with open('nonexistent.txt') as f:  # FileNotFoundError
        content = f.read()
    
    return 10 / 0  # ZeroDivisionError
"""

response = requests.post(
    f"{BASE_URL}/v1/analyze",
    json={"code": test_code}
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"\nFound {len(result['errors'])} potential errors:")
    for error in result['errors']:
        print(f"\n- Type: {error['type']}")
        print(f"  Line: {error['line']}")
        print(f"  Message: {error['message']}")
        print(f"  Prevention: {error['prevention']}")
        print(f"  Code: {error['code_snippet']}")
else:
    print(f"Error: {response.text}")

# 3. Test rate limiting
print("\n3. Testing free tier usage...")
response = requests.post(
    f"{BASE_URL}/v1/analyze",
    json={"code": "print('hello')"}
)
if response.status_code == 200:
    usage = response.json().get('usage', 'N/A')
    print(f"Free tier usage: {usage}/100")

print("\n✅ API test complete!")