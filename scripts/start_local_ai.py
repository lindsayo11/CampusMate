"""Start the local CampusMate preview with real AI and an isolated database.

On Windows, credentials can be kept in the current user's Credential Manager.
No credential is written into source files or passed as a command-line argument.
Run with the Windows Python that has pywin32, or provide process environment keys.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KEYS = {"DEEPSEEK_API_KEY", "DEEPSEEK_API_BASE", "DEEPSEEK_MODEL",
        "TAVILY_API_KEY", "TAVILY_API_BASE"}
TARGET = "CampusMate/local-ai/" + hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:16]


def save_ai_configuration(values):
    if os.name != "nt":
        raise RuntimeError("Use process environment variables on this platform.")
    import win32cred
    allowed = {key: value for key, value in values.items() if key in KEYS and isinstance(value, str)}
    if not allowed.get("DEEPSEEK_API_KEY", "").strip():
        raise RuntimeError("A model credential is required.")
    win32cred.CredWrite({"Type": win32cred.CRED_TYPE_GENERIC, "TargetName": TARGET,
                        "UserName": "CampusMate local AI", "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
                        "CredentialBlob": json.dumps(allowed)}, 0)


def load_ai_configuration():
    if os.name != "nt":
        return {}
    try:
        import win32cred
    except ImportError:
        return {}
    try:
        credential = win32cred.CredRead(TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception as exc:
        if getattr(exc, "winerror", None) == 1168:
            return {}
        raise RuntimeError("Unable to read CampusMate's local AI credential.") from None
    try:
        blob = credential["CredentialBlob"]
        values = json.loads(blob.decode("utf-16-le") if isinstance(blob, bytes) else blob)
        return {key: value for key, value in values.items() if key in KEYS and isinstance(value, str)}
    except (ValueError, AttributeError, KeyError):
        raise RuntimeError("CampusMate's local AI configuration is invalid.") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8001)
    parser.add_argument("--web-port", type=int, default=3000)
    args = parser.parse_args()
    saved = load_ai_configuration()
    env = {**os.environ, **saved}
    env.update({key: os.environ[key] for key in KEYS if os.environ.get(key)})
    if not env.get("DEEPSEEK_API_KEY", "").strip():
        parser.error("Configure DEEPSEEK_API_KEY securely before starting real AI; do not put it in this command.")
    python = ROOT / ("backend/.venv/Scripts/python.exe" if os.name == "nt" else "backend/.venv/bin/python")
    child = subprocess.Popen([str(python), str(ROOT / "scripts/preview_motion.py"),
        "--production", "--with-ai", "--api-port", str(args.api_port), "--web-port", str(args.web_port)],
        cwd=ROOT, env=env)
    saved.clear()
    env.clear()
    try:
        return child.wait()
    except KeyboardInterrupt:
        try:
            return child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.terminate()
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
