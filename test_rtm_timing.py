#!/usr/bin/env python3
"""
Test script to measure RTM API call timing
"""

import sys
import time
from rtm_client import createRTM

def test_rtm_timing():
    # Read credentials
    try:
        with open('secrets.txt', 'r') as file:
            api_key = None
            shared_secret = None
            for line in file:
                if "api-key" in line.lower():
                    api_key = line.strip().split('=')[1]
                elif "shared-secret" in line.lower():
                    shared_secret = line.strip().split('=')[1]
    except FileNotFoundError:
        print("ERROR: secrets.txt not found")
        return
    
    # Read auth token
    try:
        with open('auth_token.txt', 'r') as file:
            auth_token = None
            for line in file:
                if 'home' in line:  # Look for the account you're using
                    auth_token = line.strip().split('=')[1]
                    break
    except FileNotFoundError:
        print("ERROR: auth_token.txt not found")
        return
    
    print(f"Testing RTM API call timing...")
    
    try:
        print("\n1. Testing createRTM...")
        start_time = time.time()
        rtm = createRTM(api_key, shared_secret, auth_token)
        elapsed = time.time() - start_time
        print(f"✓ createRTM successful ({elapsed:.2f}s)")
        
        print("\n2. Testing rtm.timelines.create()...")
        start_time = time.time()
        response = rtm.timelines.create()
        elapsed = time.time() - start_time
        print(f"✓ rtm.timelines.create() successful: {response.stat} ({elapsed:.2f}s)")
        
        print("\n3. Testing rtm.tasks.getList()...")
        start_time = time.time()
        list_id = "23595959"  # Your list ID
        rspTasks = rtm.tasks.getList(list_id=list_id, filter="status:incomplete")
        elapsed = time.time() - start_time
        print(f"✓ rtm.tasks.getList() successful ({elapsed:.2f}s)")
        
        print(f"\nTotal API calls completed successfully!")
        
    except Exception as e:
        print(f"✗ ERROR: {e}")

if __name__ == "__main__":
    test_rtm_timing()