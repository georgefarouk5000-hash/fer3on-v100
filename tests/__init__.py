# FER3ON test package
# Keep Shadow/Phase 2/3 writes outside the repository during unittest runs.
import os
import tempfile

os.environ.setdefault(
	"FER3ON_TEST_DATA_DIR",
	tempfile.mkdtemp(prefix="fer3on-test-data-"),
)
