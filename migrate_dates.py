import sqlite3
import re
import json

def convert_to_iso(date_str):
    if not date_str or date_str == 'N/A':
        return date_str
    
    # Check if already ISO
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
        
    # Check if DD/MM/YYYY
    match = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', str(date_str))
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
        
    return date_str

def run_migration():
    print("Starting database date migration...")
    conn = sqlite3.connect("contracts.db")
    cursor = conn.cursor()
    
    # Migrate contracts table
    cursor.execute("SELECT id, date, expiry_date FROM contracts")
    rows = cursor.fetchall()
    
    updated_count = 0
    for row in rows:
        c_id, date, expiry = row
        new_date = convert_to_iso(date)
        new_expiry = convert_to_iso(expiry)
        
        if new_date != date or new_expiry != expiry:
            cursor.execute("UPDATE contracts SET date=?, expiry_date=? WHERE id=?", (new_date, new_expiry, c_id))
            updated_count += 1
            
    print(f"Migrated {updated_count} rows in contracts table.")
    
    # Migrate contract_versions table (JSON data)
    cursor.execute("SELECT id, contract_data FROM contract_versions")
    rows = cursor.fetchall()
    
    updated_versions = 0
    for row in rows:
        v_id, contract_data_json = row
        try:
            data = json.loads(contract_data_json)
            changed = False
            
            if 'date' in data:
                old_date = data['date']
                new_date = convert_to_iso(old_date)
                if old_date != new_date:
                    data['date'] = new_date
                    changed = True
                    
            if 'expiry_date' in data:
                old_expiry = data['expiry_date']
                new_expiry = convert_to_iso(old_expiry)
                if old_expiry != new_expiry:
                    data['expiry_date'] = new_expiry
                    changed = True
                    
            if changed:
                cursor.execute("UPDATE contract_versions SET contract_data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), v_id))
                updated_versions += 1
        except Exception as e:
            print(f"Error parsing version {v_id}: {e}")
            
    print(f"Migrated {updated_versions} rows in contract_versions table.")
    
    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    run_migration()
