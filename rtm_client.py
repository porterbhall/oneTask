"""
RTM (Remember The Milk) API client wrapper for MilkBox application.
This module provides the createRTM function from the pyrtm library.
"""

# Now we can safely import from the rtm package since our file is named differently
from rtm import createRTM

# Re-export the function
__all__ = ['createRTM']