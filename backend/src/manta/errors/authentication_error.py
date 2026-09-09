class AuthenticationError(Exception):
    """Raised for any invalid-credentials or invalid-token condition; routes map this to 401."""
