class NonRetryableError(Exception):
    """Raised when retrying will never succeed — billing quota, invalid API key, etc.
    The harness skips its retry loop and surfaces the message directly to the user."""
