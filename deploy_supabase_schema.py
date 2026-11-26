import psycopg2
import sys

passwords = ["Testing-testing#iosapp#22", "[Testing-testing#iosapp#22]"]
host = "db.wiwkyjwhymkvhtribakw.supabase.co"
user = "postgres"
dbname = "postgres"
port = 5432

conn = None
working_password = None

for pw in passwords:
    try:
        print(f"Trying connection with password length {len(pw)}...")
        conn = psycopg2.connect(
            host=host,
            user=user,
            password=pw,
            dbname=dbname,
            port=port,
            sslmode="require",
            connect_timeout=10
        )
        working_password = pw
        print("Connected successfully to Supabase Postgres!")
        break
    except Exception as e:
        print(f"Connection failed: {e}")

if not conn:
    print("Could not connect with either password variant.")
    sys.exit(1)

# Read schema.sql
with open("supabase/schema.sql", "r", encoding="utf-8") as f:
    schema_sql = f.read()

cur = conn.cursor()
print("Executing supabase/schema.sql migration...")
cur.execute(schema_sql)
conn.commit()
print("Schema migration executed and committed successfully!")

# Verify created tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    ORDER BY table_name;
""")
tables = cur.fetchall()
print("\nTables in public schema:")
for t in tables:
    print(f"  - {t[0]}")

cur.close()
conn.close()
