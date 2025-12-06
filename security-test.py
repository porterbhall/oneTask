# Security Test File - Contains Intentional Test Secrets
# This file is used to test GitHub secret scanning functionality
# These are NOT real secrets - they are test patterns only

def test_secret_detection():
    """Test function with fake secrets to trigger GitHub secret scanning"""
    
    # Fake GitHub Personal Access Token pattern (this will trigger detection)
    fake_github_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyzABCD"
    
    # Fake AWS Access Key pattern (this will trigger detection)  
    fake_aws_key = "AKIA1234567890ABCDEF"
    fake_aws_secret = "abcdefghijklmnopqrstuvwxyz1234567890ABCDEF"
    
    # Fake API key pattern
    fake_api_key = "sk_test_1234567890abcdefghijklmnopqrstuvwxyz"
    
    print("This file contains fake secrets for testing secret detection")
    print("These should be detected by GitHub secret scanning")
    
    return {
        "github_token": fake_github_token,
        "aws_access_key": fake_aws_key,
        "aws_secret_key": fake_aws_secret,
        "api_key": fake_api_key
    }

if __name__ == "__main__":
    test_secret_detection()