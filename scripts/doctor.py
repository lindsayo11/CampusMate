"""Report configuration readiness without displaying credentials."""
import importlib.util
import os
import shutil
import sys

print("Python", sys.version.split()[0])
for executable in ("node", "npm", "docker"):
    print(executable, "available" if shutil.which(executable) else "missing")
for module in ("fastapi", "sqlalchemy", "httpx", "psycopg", "pytest"):
    print(module, "available" if importlib.util.find_spec(module) else "missing")
for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "ADMIN_USER_IDS"):
    print(name, "configured" if os.getenv(name) else "not configured")
print("Demo mode", os.getenv("DEMO_MODE", "false"))
