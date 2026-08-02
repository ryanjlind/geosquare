import os
import sys

# Ensure project root is on sys.path so 'app' package can be imported in tests
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
