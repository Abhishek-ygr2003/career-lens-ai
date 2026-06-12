"""
CareerLens AI — collector/exceptions.py
Custom exceptions for the collection pipeline.
"""

class SessionExpiredError(Exception):
    """Raised when a collector's API session (cookies/tokens) has expired or been blocked."""
    pass
