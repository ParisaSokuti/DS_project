#!/usr/bin/env python3
"""
Database Table Inspector for Hokm Game
Shows contents of all tables in the database
"""
import asyncio
import asyncpg
import json
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Database connection configurations to try
DB_CONFIGS = [
    {
        'name': 'Default Configuration',
        'dsn': 'postgresql://hokm_admin:hokm_secure_2024!@localhost:5432/hokm_game'
    },
    {
        'name': 'Alternative hokm_user',
        'dsn': 'postgresql://hokm_user:hokm_secure_2024!@localhost:5432/hokm_game'
    },
    {
        'name': 'Postgres user',
        'dsn': 'postgresql://postgres:@localhost:5432/hokm_game'
    },
    {
        'name': 'Postgres with password',
        'dsn': 'postgresql://postgres:password@localhost:5432/hokm_game'
    },
    {
        'name': 'Your user',
        'dsn': 'postgresql://parisasokuti:@localhost:5432/hokm_game'
    }
]

async def test_connection(dsn: str) -> Tuple[bool, str]:
    """Test database connection."""
    try:
        conn = await asyncpg.connect(dsn)
        result = await conn.fetchval("SELECT current_user, current_database()")
        await conn.close()
        return True, result
    except Exception as e:
        return False, str(e)

async def get_table_info(conn) -> List[Dict]:
    """Get information about all tables."""
    query = """
    SELECT 
        table_schema,
        table_name,
        table_type,
        is_insertable_into,
        (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name AND table_schema = t.table_schema) as column_count
    FROM information_schema.tables t
    WHERE table_schema IN ('public', 'hokm_game')
    ORDER BY table_schema, table_name;
    """
    
    result = await conn.fetch(query)
    return [dict(row) for row in result]

async def get_table_columns(conn, table_name: str, schema_name: str = 'public') -> List[Dict]:
    """Get column information for a table."""
    query = """
    SELECT 
        column_name,
        data_type,
        is_nullable,
        column_default,
        character_maximum_length
    FROM information_schema.columns
    WHERE table_name = $1 AND table_schema = $2
    ORDER BY ordinal_position;
    """
    
    result = await conn.fetch(query, table_name, schema_name)
    return [dict(row) for row in result]

async def get_table_row_count(conn, table_name: str, schema_name: str = 'public') -> int:
    """Get row count for a table."""
    try:
        query = f"SELECT COUNT(*) FROM {schema_name}.{table_name}"
        result = await conn.fetchval(query)
        return result
    except Exception as e:
        return 0

async def get_table_sample_data(conn, table_name: str, schema_name: str = 'public', limit: int = 5) -> List[Dict]:
    """Get sample data from a table."""
    try:
        query = f"SELECT * FROM {schema_name}.{table_name} ORDER BY CASE WHEN EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = $1 AND table_schema = $2 AND column_name = 'created_at') THEN created_at ELSE NULL END DESC LIMIT {limit}"
        result = await conn.fetch(query, table_name, schema_name)
        
        # Convert to dict and handle special types
        sample_data = []
        for row in result:
            row_dict = {}
            for key, value in row.items():
                if isinstance(value, datetime):
                    row_dict[key] = value.isoformat()
                elif isinstance(value, dict) or isinstance(value, list):
                    row_dict[key] = json.dumps(value, default=str)
                else:
                    row_dict[key] = str(value) if value is not None else None
            sample_data.append(row_dict)
        
        return sample_data
    except Exception as e:
        return []

async def inspect_database(dsn: str):
    """Inspect database contents."""
    print(f"🔍 Connecting to database...")
    conn = await asyncpg.connect(dsn)
    
    try:
        # Get current user and database
        user_info = await conn.fetchval("SELECT current_user, current_database()")
        print(f"✅ Connected as: {user_info}")
        
        # Get all tables
        tables = await get_table_info(conn)
        print(f"\n📊 Found {len(tables)} tables/views:")
        
        for table in tables:
            table_name = table['table_name']
            table_schema = table['table_schema']
            table_type = table['table_type']
            column_count = table['column_count']
            
            print(f"\n{'='*60}")
            print(f"📋 TABLE: {table_schema}.{table_name} ({table_type})")
            print(f"{'='*60}")
            
            # Get row count
            row_count = await get_table_row_count(conn, table_name, table_schema)
            print(f"📊 Rows: {row_count:,}")
            print(f"📊 Columns: {column_count}")
            
            # Get column info
            columns = await get_table_columns(conn, table_name, table_schema)
            print(f"\n📋 COLUMNS:")
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                default = f", DEFAULT: {col['column_default']}" if col['column_default'] else ""
                length = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
                print(f"  • {col['column_name']}: {col['data_type']}{length} {nullable}{default}")
            
            # Get sample data if table has rows
            if row_count > 0:
                sample_data = await get_table_sample_data(conn, table_name, table_schema)
                if sample_data:
                    print(f"\n📋 SAMPLE DATA (up to 5 rows):")
                    for i, row in enumerate(sample_data, 1):
                        print(f"  Row {i}:")
                        for key, value in row.items():
                            # Truncate long values
                            if value and len(str(value)) > 100:
                                display_value = str(value)[:100] + "..."
                            else:
                                display_value = value
                            print(f"    {key}: {display_value}")
                        print()
                else:
                    print(f"\n📋 No sample data available")
            else:
                print(f"\n📋 Table is empty")
        
        # Additional statistics
        print(f"\n{'='*60}")
        print(f"📊 DATABASE SUMMARY")
        print(f"{'='*60}")
        
        if tables:
            total_rows = 0
            for table in tables:
                row_count = await get_table_row_count(conn, table['table_name'], table['table_schema'])
                total_rows += row_count
            
            non_empty_tables = 0
            for table in tables:
                row_count = await get_table_row_count(conn, table['table_name'], table['table_schema'])
                if row_count > 0:
                    non_empty_tables += 1
            
            print(f"Total tables: {len(tables)}")
            print(f"Non-empty tables: {non_empty_tables}")
            print(f"Total rows across all tables: {total_rows:,}")
            
            # Show tables with data
            if non_empty_tables > 0:
                print(f"\nTables with data:")
                for table in tables:
                    row_count = await get_table_row_count(conn, table['table_name'], table['table_schema'])
                    if row_count > 0:
                        print(f"  • {table['table_schema']}.{table['table_name']}: {row_count:,} rows")
            else:
                print("\nAll tables are empty - no data has been inserted yet.")
        else:
            print("No tables found in the database!")
            print("The database schema may not have been created yet.")
            
            # Check if we can see any schemas
            schemas = await conn.fetch("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1')")
            print(f"\nAvailable schemas:")
            for schema in schemas:
                print(f"  • {schema['schema_name']}")
        
        # Check database version and status
        pg_version = await conn.fetchval("SELECT version()")
        print(f"\nPostgreSQL version: {pg_version}")
        
    finally:
        await conn.close()

async def main():
    """Main function to inspect database."""
    print("🗄️  DATABASE TABLE INSPECTOR")
    print("="*60)
    
    # Try different connection configurations
    working_dsn = None
    for config in DB_CONFIGS:
        print(f"\n🔍 Testing {config['name']}...")
        success, result = await test_connection(config['dsn'])
        
        if success:
            print(f"✅ Success! Connected as: {result}")
            working_dsn = config['dsn']
            break
        else:
            print(f"❌ Failed: {result}")
    
    if not working_dsn:
        print("\n❌ Could not connect to any database configuration!")
        print("Please check:")
        print("1. PostgreSQL is running")
        print("2. Database 'hokm_game' exists")
        print("3. User credentials are correct")
        return
    
    print(f"\n🚀 Inspecting database contents...")
    await inspect_database(working_dsn)

if __name__ == "__main__":
    asyncio.run(main())
