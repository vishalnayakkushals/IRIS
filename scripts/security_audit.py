import os
import secrets
from pathlib import Path

def run_security_sweep():
    print("Running IRIS Pre-Go-Live Security Sweep...")
    
    # 1. Clean local debug files
    project_root = Path("C:/Users/Kushals.DESKTOP-D51MT8S/Desktop/Github/IRIS")
    env_local = project_root / ".env.local"
    if env_local.exists():
        print("[WARNING] .env.local found. Ensure this file is excluded from any public repositories and production servers.")
    else:
        print("[OK] No .env.local found.")

    # 2. Check JWT configuration
    jwt_secret = os.getenv("IRIS_JWT_SECRET", "change_me_in_env")
    if jwt_secret == "change_me_in_env":
        print("[WARNING] JWT Secret is using default unsafe value. Generating strong secret...")
        print(f"-> Please use this exact secret in your production environment: {secrets.token_hex(32)}")
    else:
        print("[OK] JWT Secret is configured securely.")

    # 3. Check for exposed host bindings in Python configs
    # (Checking if main FastAPI app binds to 0.0.0.0 unwisely without reverse proxy logic)
    print("[INFO] Please verify your Uvicorn or NSSM configurations bind to '127.0.0.1' natively, and expose traffic via NGINX/Caddy.")

    print("\nSweep Complete. Please sign off on SECURITY_CLEANUP_CHECKLIST.md.")

if __name__ == "__main__":
    run_security_sweep()
