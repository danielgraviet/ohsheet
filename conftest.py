import os

# Provide stub values for required env vars so Settings() can instantiate
# during test collection without a fully populated .env file.
os.environ.setdefault("CANVAS_TOKEN", "test-token")
os.environ.setdefault("CANVAS_DOMAIN", "test.instructure.com")
os.environ.setdefault("SPREADSHEET_ID", "test-sheet-id")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("GOOGLE_CREDS_JSON", '{"type":"service_account"}')
# Multi-tenant stubs
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "TluxwB3fV_GWoGNrlFG2QAFGlMqXDcmJb9y4BHD9xfk=")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key-32chars!!")
os.environ.setdefault("APP_BASE_URL", "http://localhost:8000")