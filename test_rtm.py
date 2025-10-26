#!/usr/bin/env python3
"""
Test script to debug RTM API hanging issues
"""

import sys
import signal
import time
from rtm_client import createRTM

def timeout_handler(signum, frame):
    print("TIMEOUT: RTM API call took too long!")
    raise TimeoutError("RTM API call timed out")

def test_rtm_calls():
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
    
    if not all([api_key, shared_secret, auth_token]):
        print("ERROR: Missing credentials")
        return
    
    print(f"Testing RTM API calls...")
    print(f"API Key: {api_key[:10]}...")
    print(f"Auth Token: {auth_token[:10]}...")
    
    # Set timeout for each API call
    signal.signal(signal.SIGALRM, timeout_handler)
    
    try:
        print("\n1. Testing createRTM...")
        signal.alarm(30)  # 30 second timeout
        rtm = createRTM(api_key, shared_secret, auth_token)
        signal.alarm(0)  # Cancel timeout
        print("✓ createRTM successful")
        
        print("\n2. Testing rtm.timelines.create()...")
        signal.alarm(10)  # 10 second timeout  
        response = rtm.timelines.create()
        signal.alarm(0)  # Cancel timeout
        print(f"✓ rtm.timelines.create() successful: {response.stat}")
        
        print("\n3. Testing rtm.tasks.getList()...")
        signal.alarm(10)  # 10 second timeout
        list_id = "23595959"  # Your list ID
        rspTasks = rtm.tasks.getList(list_id=list_id, filter="status:incomplete")
        signal.alarm(0)  # Cancel timeout
        print(f"✓ rtm.tasks.getList() successful")
        
        print("\nAll tests passed!")
        
    except TimeoutError as e:
        print(f"✗ TIMEOUT: {e}")
    except Exception as e:
        signal.alarm(0)  # Cancel timeout
        print(f"✗ ERROR: {e}")

if __name__ == "__main__":
    test_rtm_calls()