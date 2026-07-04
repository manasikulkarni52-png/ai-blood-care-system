import pyodbc

# 1. The Connection "Bridge"
def get_db_connection():
    try:
        # Standardized to use ODBC Driver 17 for your SHREEHP server
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=SHREEHP;' 
            'DATABASE=blood_care;'
            'Trusted_Connection=yes;'
            'TrustServerCertificate=yes;'
        )
        return conn
    except Exception as e:
        print(f"Primary Driver failed, trying fallback... Error: {e}")
        try:
            # Fallback for older drivers if Driver 17 isn't found
            conn = pyodbc.connect(
                'DRIVER={SQL Server};' 
                'SERVER=SHREEHP;' 
                'DATABASE=blood_care;'
                'Trusted_Connection=yes;'
                'TrustServerCertificate=yes;'
            )
            return conn
        except Exception as fallback_e:
            print(f"CRITICAL: Connection failed. Error: {fallback_e}")
            return None

# 2. The Table Creator (Run this once to setup)
def init_db():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        
        # Table 1: Health Records
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='health_records' AND xtype='U')
            CREATE TABLE health_records (
                id INT IDENTITY(1,1) PRIMARY KEY,
                hb FLOAT, 
                rbc FLOAT, 
                wbc FLOAT, 
                platelets FLOAT,
                result VARCHAR(100), 
                created_at DATETIME DEFAULT GETDATE()
            )
        """)
        
        # Table 2: Donors
       # Inside init_db() function
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='donors' AND xtype='U')
        CREATE TABLE donors (
            id INT IDENTITY(1,1) PRIMARY KEY,
            fullname VARCHAR(150),
            blood_group VARCHAR(5),
            phone VARCHAR(15),
            age INT,
            weight FLOAT,  -- Add this line!
            status VARCHAR(50) DEFAULT 'Eligible',
            created_at DATETIME DEFAULT GETDATE()
        )
    """)
        conn.commit()
        conn.close()
        print("Success: SQL Server Tables (Health & Donors) are ready!")
    else:
        print("Failed: Could not connect to SQL Server.")

# This ensures the script only runs when you manually execute 'python db.py'
if __name__ == "__main__":
    init_db()