import os, tempfile

# Ensure DATA_DIR points to a writable temp directory so that importing
# main.py (which calls os.makedirs(DATA_DIR) at module level) does not fail
# when /app/data is not accessible (e.g., running tests locally on macOS).
_tmp_data = tempfile.mkdtemp(prefix="zorionbot_test_")
os.environ.setdefault("DATA_DIR", _tmp_data)
