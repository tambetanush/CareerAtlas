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
        for cmd in [["uv", "pip", "install", "psycopg2-binary"], [sys.executable, "-m", "pip", "install", "psycopg2-binary"], ["pip", "install", "psycopg2-binary"]]:
            try:
                subprocess.run(cmd, check=True)
                import psycopg2
                return psycopg2
            except Exception:
                continue
        print("Failed to install psycopg2-binary automatically. Please run: uv pip install psycopg2-binary")
        sys.exit(1)

def run_migrations():
    psycopg2 = ensure_psycopg2()
    
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    
    supabase_url = os.getenv("SUPABASE_URL", "")
    if not supabase_url or "placeholder" in supabase_url:
        print("Error: SUPABASE_URL not configured in .env")
        sys.exit(1)
        
    try:
        project_ref = supabase_url.split("//")[1].split(".")[0]
    except Exception:
        print(f"Error: Could not parse project ref from SUPABASE_URL: {supabase_url}")
        sys.exit(1)
        
    print(f"Parsed Supabase Project Ref: {project_ref}")
    
    password = os.getenv("SUPABASE_DB_PASSWORD", "")
    if not password:
        password = input("Enter your Supabase database password: ").strip()
        
    if not password:
        print("Error: Database password is required.")
        sys.exit(1)
        
    conn = None
    for port in [5432, 6543]:
        host = f"db.{project_ref}.supabase.co"
        print(f"Attempting to connect to {host}:{port}...")
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user="postgres",
                password=password,
                host=host,
                port=port,
                connect_timeout=10
            )
            print(f"Connected successfully on port {port}!")
            break
        except Exception as e:
            print(f"Failed to connect on port {port}: {e}")
            
    if not conn:
        print("\nCould not connect to the database. Check your password/network.")
        sys.exit(1)
        
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Check existing tables
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    existing_tables = {row[0] for row in cursor.fetchall()}
    print(f"Existing public tables: {sorted(list(existing_tables))}")
    
    # 1. Create missing tables from 001_schema.sql
    schema_tables = {
        "profiles": """
            CREATE TABLE profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) UNIQUE NOT NULL,
                name TEXT NOT NULL,
                headline TEXT,
                email TEXT,
                location TEXT,
                github TEXT,
                summary TEXT,
                completeness INTEGER DEFAULT 0,
                target_role_id TEXT,
                resume_key TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        "skills": """
            CREATE TABLE skills (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                level TEXT NOT NULL,
                evidence TEXT,
                source TEXT DEFAULT 'resume',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        "experience_items": """
            CREATE TABLE experience_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                role TEXT NOT NULL,
                company TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                bullets JSONB DEFAULT '[]'::jsonb,
                sort_order INTEGER DEFAULT 0
            );
        """,
        "education_items": """
            CREATE TABLE education_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                school TEXT NOT NULL,
                degree TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT
            );
        """,
        "project_items": """
            CREATE TABLE project_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                tech TEXT[] DEFAULT '{}',
                link TEXT,
                sort_order INTEGER DEFAULT 0
            );
        """,
        "target_roles": """
            CREATE TABLE target_roles (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                blurb TEXT NOT NULL,
                emoji TEXT NOT NULL,
                popular_skills TEXT[] DEFAULT '{}'
            );
        """,
        "skill_gaps": """
            CREATE TABLE skill_gaps (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                skill TEXT NOT NULL,
                category TEXT NOT NULL,
                relevance INTEGER NOT NULL,
                difficulty TEXT NOT NULL,
                prerequisites TEXT[] DEFAULT '{}',
                why TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        "milestones": """
            CREATE TABLE milestones (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                target_role TEXT,
                target_role_id TEXT,
                resume_id TEXT,
                phase TEXT NOT NULL,
                title TEXT NOT NULL,
                skill TEXT NOT NULL,
                status TEXT DEFAULT 'locked',
                estimated_weeks INTEGER NOT NULL,
                description TEXT NOT NULL,
                courses JSONB DEFAULT '[]'::jsonb,
                project JSONB DEFAULT '{}'::jsonb,
                checklist TEXT[] DEFAULT '{}',
                sort_order INTEGER DEFAULT 0,
                completed_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        "job_matches": """
            CREATE TABLE job_matches (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                job_id TEXT,
                query_role TEXT,
                user_location_preference TEXT,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                remote BOOLEAN DEFAULT FALSE,
                seniority TEXT NOT NULL,
                match_pct INTEGER NOT NULL,
                matched TEXT[] DEFAULT '{}',
                missing TEXT[] DEFAULT '{}',
                salary TEXT,
                posted_days INTEGER DEFAULT 0,
                description TEXT,
                external_url TEXT,
                score_json JSONB,
                explanation_json JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        "learning_pathways": """
            CREATE TABLE learning_pathways (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) NOT NULL,
                role_slug TEXT NOT NULL,
                target_role TEXT NOT NULL,
                pathway JSONB NOT NULL,
                sources TEXT[] DEFAULT '{}',
                iterations_used INTEGER DEFAULT 0,
                quality_score NUMERIC,
                quality_verdict JSONB,
                validation JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """
    }
    
    for table_name, create_sql in schema_tables.items():
        if table_name not in existing_tables:
            print(f"Creating table {table_name}...")
            cursor.execute(create_sql)
        else:
            print(f"Table {table_name} already exists.")
            
    # Enable RLS policies
    for table_name in schema_tables.keys():
        try:
            cursor.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
            print(f"Enabled RLS on {table_name}")
        except Exception as e:
            print(f"Warning enabling RLS on {table_name}: {e}")
            
    # Add owner-only policies
    policies = {
        "owner_all_experience": ("experience_items", "auth.uid() = user_id"),
        "owner_all_education": ("education_items", "auth.uid() = user_id"),
        "owner_all_projects": ("project_items", "auth.uid() = user_id"),
    }
    
    for p_name, (table, condition) in policies.items():
        cursor.execute(f"""
            SELECT 1 FROM pg_policies 
            WHERE schemaname = 'public' AND tablename = %s AND policyname = %s
        """, (table, p_name))
        if not cursor.fetchone():
            print(f"Creating policy {p_name} on {table}...")
            cursor.execute(f"""
                CREATE POLICY "{p_name}" ON {table}
                FOR ALL USING ({condition}) WITH CHECK ({condition});
            """)
            
    # Target roles public read
    cursor.execute("""
        SELECT 1 FROM pg_policies 
        WHERE schemaname = 'public' AND tablename = 'target_roles' AND policyname = 'public_read_roles'
    """)
    if not cursor.fetchone():
        print("Creating public read policy on target_roles...")
        cursor.execute('CREATE POLICY "public_read_roles" ON target_roles FOR SELECT USING (true);')
        
    # Seed roles
    cursor.execute("SELECT COUNT(*) FROM target_roles;")
    if cursor.fetchone()[0] == 0:
        print("Seeding target_roles...")
        seed_sql = (ROOT / "sql" / "003_seed_roles.sql").read_text(encoding="utf-8")
        cursor.execute(seed_sql)
        
    # Job matches structured columns
    job_matches_cols = ["job_id", "query_role", "user_location_preference", "score_json", "explanation_json"]
    for col in job_matches_cols:
        cursor.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'job_matches' AND column_name = %s
        """, (col,))
        if not cursor.fetchone():
            col_type = "JSONB" if "json" in col else "TEXT"
            print(f"Adding column {col} to job_matches...")
            cursor.execute(f"ALTER TABLE job_matches ADD COLUMN {col} {col_type};")
            
    # Milestones structured columns
    milestones_cols = {
        "target_role": "TEXT",
        "target_role_id": "TEXT",
        "resume_id": "TEXT",
        "completed_at": "TIMESTAMPTZ"
    }
    for col, col_type in milestones_cols.items():
        cursor.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'milestones' AND column_name = %s
        """, (col,))
        if not cursor.fetchone():
            print(f"Adding column {col} to milestones...")
            cursor.execute(f"ALTER TABLE milestones ADD COLUMN {col} {col_type};")

    # GitHub tables (006_github_analysis.sql)
    github_tables = {
        "github_tokens": """
            CREATE TABLE github_tokens (
                user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at TIMESTAMPTZ,
                github_user_id TEXT,
                github_username TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        "github_profiles": """
            CREATE TABLE github_profiles (
                user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
                analysis_summary TEXT,
                coding_behavior TEXT,
                inferred_skills TEXT[] DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """,
        "github_repositories": """
            CREATE TABLE github_repositories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
                repo_name TEXT NOT NULL,
                repo_url TEXT,
                is_owner BOOLEAN DEFAULT TRUE,
                description TEXT,
                primary_language TEXT,
                analysis_summary TEXT,
                coding_behavior TEXT,
                analyzed_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, repo_name)
            );
        """
    }
    
    for table_name, create_sql in github_tables.items():
        if table_name not in existing_tables:
            print(f"Creating table {table_name}...")
            cursor.execute(create_sql)
            cursor.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
            cursor.execute(f"""
                CREATE POLICY "Users can manage their own {table_name}"
                ON {table_name} FOR ALL USING (auth.uid() = user_id);
            """)
            
    # GitHub Hardening (007_github_hardening.sql)
    if "github_skill_evidence" not in existing_tables:
        print("Creating table github_skill_evidence...")
        cursor.execute("""
            CREATE TABLE github_skill_evidence (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
                skill TEXT NOT NULL,
                evidence TEXT,
                confidence TEXT DEFAULT 'low',
                source_repo TEXT,
                confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(user_id, skill, source_repo)
            );
        """)
        cursor.execute("ALTER TABLE github_skill_evidence ENABLE ROW LEVEL SECURITY;")
        cursor.execute("""
            CREATE POLICY "Users can manage their own github_skill_evidence"
            ON github_skill_evidence FOR ALL USING (auth.uid() = user_id);
        """)
        
    github_repos_cols = {
        "languages": "JSONB",
        "commit_count": "INTEGER",
        "first_commit_at": "TIMESTAMPTZ",
        "last_commit_at": "TIMESTAMPTZ"
    }
    for col, col_type in github_repos_cols.items():
        cursor.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = 'github_repositories' AND column_name = %s
        """, (col,))
        if not cursor.fetchone():
            print(f"Adding column {col} to github_repositories...")
            cursor.execute(f"ALTER TABLE github_repositories ADD COLUMN {col} {col_type};")
            
    print("\nDatabase migrations checked and applied successfully!")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    run_migrations()
