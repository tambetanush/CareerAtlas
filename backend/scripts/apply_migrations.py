import os
import sys
import subprocess
from pathlib import Path
import urllib.parse

# Add parent directory to path to load config / environment
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def ensure_psycopg2():
    try:
        import psycopg2
        return psycopg2
    except ImportError:
        print("Installing 'psycopg2-binary' to connect to PostgreSQL...")
        # Try uv pip install first, then fall back to standard pip
        for cmd in [["uv", "pip", "install", "psycopg2-binary"], [sys.executable, "-m", "pip", "install", "psycopg2-binary"], ["pip", "install", "psycopg2-binary"]]:
            try:
                subprocess.run(cmd, check=True)
                import psycopg2
                return psycopg2
            except Exception:
                continue
        print("Failed to install psycopg2-binary automatically.")
        print("Please run: uv pip install psycopg2-binary")
        sys.exit(1)

def run_migrations():
    # Ensure dependencies are available
    psycopg2 = ensure_psycopg2()
    
    # Load env
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    
    supabase_url = os.getenv("SUPABASE_URL", "")
    if not supabase_url or "placeholder" in supabase_url:
        print("Error: SUPABASE_URL not configured in .env")
        sys.exit(1)
        
    # Extract project ref
    # E.g. https://lotcwutyfwnsdscmzhcl.supabase.co -> lotcwutyfwnsdscmzhcl
    try:
        project_ref = supabase_url.split("//")[1].split(".")[0]
    except Exception:
        print(f"Error: Could not parse project ref from SUPABASE_URL: {supabase_url}")
        sys.exit(1)
        
    print(f"Parsed Supabase Project Ref: {project_ref}")
    
    # Get password
    password = os.getenv("SUPABASE_DB_PASSWORD", "")
    if not password:
        password = input("Enter your Supabase database password: ").strip()
        
    if not password:
        print("Error: Database password is required.")
        sys.exit(1)
        
    escaped_password = urllib.parse.quote_plus(password)
    
    # Connect to PostgreSQL
    # Host is db.<project_ref>.supabase.co, Port is 5432 or 6543 (transaction pooler)
    # We will try both, starting with direct port 5432
    conn = None
    for port in [5432, 6543]:
        host = f"db.{project_ref}.supabase.co"
        print(f"Attempting to connect to {host}:{port}...")
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user="postgres",
                password=password, # psycopg2 handles raw password, connection string needs escaped
                host=host,
                port=port,
                connect_timeout=10
            )
            print(f"Connected successfully on port {port}!")
            break
        except Exception as e:
            print(f"Failed to connect on port {port}: {e}")
            
    if not conn:
        print("\nCould not connect to the database. Please check:")
        print("1. Your Supabase Database Password is correct.")
        print("2. Your internet connection and that database port 5432/6543 is not blocked by a firewall.")
        sys.exit(1)
        
    try:
        cursor = conn.cursor()
        
        # Read and apply 006_github_analysis.sql
        file_006 = ROOT / "sql" / "006_github_analysis.sql"
        print(f"\nApplying migration: {file_006.name}...")
        sql_006 = file_006.read_text(encoding="utf-8")
        cursor.execute(sql_006)
        conn.commit()
        print(f"Successfully applied {file_006.name}")
        
        # Read and apply 007_github_hardening.sql
        file_007 = ROOT / "sql" / "007_github_hardening.sql"
        print(f"\nApplying migration: {file_007.name}...")
        sql_007 = file_007.read_text(encoding="utf-8")
        cursor.execute(sql_007)
        conn.commit()
        print(f"Successfully applied {file_007.name}")
        
        print("\nAll database migrations applied successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\nError applying migration: {e}")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_migrations()
