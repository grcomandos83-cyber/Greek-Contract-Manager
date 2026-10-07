import sqlite3
import json
import os
import shutil
import uuid
import logging
import re
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Generator, Tuple, Union
from constants import SPECIAL_FIELD_TRANSLATIONS
from utils import validate_date, get_contract_status

logger = logging.getLogger(__name__)

def _to_iso(date_str: Any) -> Any:
    if not date_str or date_str == 'N/A': return date_str
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', str(date_str))
    if m: return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return date_str

def _to_greek(date_str: Any) -> Any:
    if not date_str or date_str == 'N/A': return date_str
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', str(date_str))
    if m: return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return date_str

class DatabaseManager:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self._init_database()
        self._auto_migrate_dates()
        
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager για αυτόματη διαχείριση σύνδεσης"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row  # Για πρόσβαση με ονόματα στηλών
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_database(self) -> None:
        """Δημιουργία πινάκων αν δεν υπάρχουν"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Πίνακας συμβάσεων
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contracts (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    number TEXT NOT NULL,
                    date TEXT NOT NULL,
                    months TEXT,
                    type TEXT NOT NULL,
                    comments TEXT,
                    expiry_date TEXT,
                    pdf_path TEXT,
                    pdf_paths TEXT,
                    special_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Migrate existing single pdf_path to pdf_paths array
            self._migrate_pdf_paths(cursor)
            
            # FTS5 Virtual Table για γρηγορότερη αναζήτηση
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS contracts_fts USING fts5(
                    id UNINDEXED,
                    provider,
                    number,
                    type,
                    date,
                    comments,
                    expiry_date,
                    special_data,
                    content='contracts',
                    content_rowid='rowid'
                )
            ''')
            
            # FTS5 Triggers για auto-update
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS contracts_ai AFTER INSERT ON contracts BEGIN
                  INSERT INTO contracts_fts(rowid, id, provider, number, type, date, comments, expiry_date, special_data)
                  VALUES (new.rowid, new.id, new.provider, new.number, new.type, new.date, new.comments, new.expiry_date, new.special_data);
                END
            ''')
            
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS contracts_ad AFTER DELETE ON contracts BEGIN
                  INSERT INTO contracts_fts(contracts_fts, rowid, id, provider, number, type, date, comments, expiry_date, special_data)
                  VALUES('delete', old.rowid, old.id, old.provider, old.number, old.type, old.date, old.comments, old.expiry_date, old.special_data);
                END
            ''')
            
            cursor.execute('''
                CREATE TRIGGER IF NOT EXISTS contracts_au AFTER UPDATE ON contracts BEGIN
                  INSERT INTO contracts_fts(contracts_fts, rowid, id, provider, number, type, date, comments, expiry_date, special_data)
                  VALUES('delete', old.rowid, old.id, old.provider, old.number, old.type, old.date, old.comments, old.expiry_date, old.special_data);
                  INSERT INTO contracts_fts(rowid, id, provider, number, type, date, comments, expiry_date, special_data)
                  VALUES (new.rowid, new.id, new.provider, new.number, new.type, new.date, new.comments, new.expiry_date, new.special_data);
                END
            ''')
            
            # Πίνακας εκδόσεων συμβάσεων
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contract_versions (
                    id TEXT PRIMARY KEY,
                    contract_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT DEFAULT 'System',
                    change_description TEXT,
                    contract_data TEXT NOT NULL,
                    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE,
                    UNIQUE(contract_id, version_number)
                )
            ''')
            
            # Δημιουργία ευρετηρίου για γρηγορότερες αναζητήσεις
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_provider ON contracts(provider)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_type ON contracts(type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_expiry_date ON contracts(expiry_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_number ON contracts(number)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_contract_versions ON contract_versions(contract_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_version_date ON contract_versions(created_at)')

    def initialize_database(self) -> None:
        """Public wrapper to (re)initialize database schema safely."""
        self._init_database()
    
    def _migrate_pdf_paths(self, cursor) -> None:
        """Μετατροπή μεμονωμένων pdf_path σε pdf_paths array"""
        try:
            # Check if pdf_paths column exists
            cursor.execute("PRAGMA table_info(contracts)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'pdf_paths' not in columns:
                # Add pdf_paths column
                cursor.execute('ALTER TABLE contracts ADD COLUMN pdf_paths TEXT')
            
            # Migrate existing pdf_path values to pdf_paths
            cursor.execute('SELECT id, pdf_path, pdf_paths FROM contracts')
            rows = cursor.fetchall()
            
            for row in rows:
                contract_id, pdf_path, pdf_paths = row
                
                # If pdf_paths is empty but pdf_path exists, migrate it
                if (not pdf_paths or pdf_paths == '[]' or pdf_paths == '') and pdf_path:
                    pdf_paths_array = [pdf_path]
                    cursor.execute(
                        'UPDATE contracts SET pdf_paths = ? WHERE id = ?',
                        (json.dumps(pdf_paths_array), contract_id)
                    )
                # If pdf_paths doesn't exist, initialize as empty array
                elif not pdf_paths:
                    cursor.execute(
                        'UPDATE contracts SET pdf_paths = ? WHERE id = ?',
                        (json.dumps([]), contract_id)
                    )
        except Exception as e:
            # If migration fails, log but don't crash
            print(f"PDF migration warning: {e}")

    def _auto_migrate_dates(self) -> None:
        """Αυτόματη μετατροπή παλιών ημερομηνιών σε ISO (εκτελείται μία φορά κατά την εκκίνηση)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Έλεγχος αν υπάρχουν ημερομηνίες με "/"
            cursor.execute("SELECT id, date, expiry_date FROM contracts WHERE date LIKE '%/%' OR expiry_date LIKE '%/%'")
            rows = cursor.fetchall()
            
            if not rows:
                return # Δεν χρειάζεται migration
                
            logger.info("Auto-migrating legacy dates to ISO format...")
            for row in rows:
                c_id = row['id']
                d = _to_iso(row['date'])
                e = _to_iso(row['expiry_date'])
                cursor.execute("UPDATE contracts SET date=?, expiry_date=? WHERE id=?", (d, e, c_id))
            
            # Μετατροπή και για τα contract_versions
            cursor.execute("SELECT id, contract_data FROM contract_versions")
            versions = cursor.fetchall()
            for row in versions:
                try:
                    v_id = row['id']
                    data = json.loads(row['contract_data'])
                    changed = False
                    if 'date' in data and '/' in str(data['date']):
                        data['date'] = _to_iso(data['date'])
                        changed = True
                    if 'expiry_date' in data and '/' in str(data.get('expiry_date', '')):
                        data['expiry_date'] = _to_iso(data['expiry_date'])
                        changed = True
                    if changed:
                        cursor.execute("UPDATE contract_versions SET contract_data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), v_id))
                except Exception as e:
                    logger.error(f"Error auto-migrating version {row['id']}: {e}")
                    
            logger.info("Legacy dates migrated successfully.")
    
    def get_all_contracts(self) -> List[Dict[str, Any]]:
        """Λήψη όλων των συμβάσεων"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contracts ORDER BY created_at DESC')
            return [self._parse_contract_row(row) for row in cursor.fetchall()]

    def _parse_contract_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        """
        Μετατροπή sqlite row σε dict με:
        - σωστό parsing του pdf_paths JSON
        - ΔΕΝ ελέγχει filesystem (αυτό γίνεται lazy στο UI)
        """
        contract = dict(row)

        # Μετατροπή ημερομηνιών από ISO ξανά σε Ελληνική μορφή για το UI
        contract['date'] = _to_greek(contract.get('date'))
        contract['expiry_date'] = _to_greek(contract.get('expiry_date'))

        # Parse pdf_paths from JSON σε λίστα
        raw_pdf_paths = contract.get('pdf_paths')
        pdf_list: List[str] = []
        if raw_pdf_paths:
            try:
                loaded = json.loads(raw_pdf_paths)
                if isinstance(loaded, list):
                    pdf_list = [p for p in loaded if isinstance(p, str) and p]
            except (json.JSONDecodeError, TypeError):
                pdf_list = []

        contract['pdf_paths'] = pdf_list

        return contract
    
    def get_contract_by_id(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Λήψη σύμβασης με βάση το ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contracts WHERE id = ?', (contract_id,))
            row = cursor.fetchone()
            return self._parse_contract_row(row) if row else None
    
    def insert_contract(self, contract_data: Dict[str, Any]) -> None:
        """Εισαγωγή νέας σύμβασης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Μετατροπή special_data σε JSON string
            special_data_json = json.dumps(contract_data.get('special_data', {}), ensure_ascii=False)
            
            # Μετατροπή pdf_paths σε JSON string
            pdf_paths = contract_data.get('pdf_paths', [])
            if not isinstance(pdf_paths, list):
                pdf_paths = []
            pdf_paths_json = json.dumps(pdf_paths)
            
            # Keep backward compatibility with pdf_path
            pdf_path = contract_data.get('pdf_path', '')
            
            cursor.execute('''
                INSERT INTO contracts
                (id, provider, number, date, months, type, comments, expiry_date, pdf_path, pdf_paths, special_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                contract_data['id'],
                contract_data['provider'],
                contract_data['number'],
                _to_iso(contract_data['date']),
                contract_data['months'],
                contract_data['type'],
                contract_data.get('comments', ''),
                _to_iso(contract_data.get('expiry_date')),
                pdf_path,
                pdf_paths_json,
                special_data_json
            ))
    
    def update_contract(self, contract_data: Dict[str, Any]) -> None:
        """Ενημέρωση σύμβασης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Μετατροπή special_data σε JSON string
            special_data_json = json.dumps(contract_data.get('special_data', {}), ensure_ascii=False)
            
            # Μετατροπή pdf_paths σε JSON string
            pdf_paths = contract_data.get('pdf_paths', [])
            if not isinstance(pdf_paths, list):
                pdf_paths = []
            pdf_paths_json = json.dumps(pdf_paths)
            
            # Keep backward compatibility with pdf_path
            pdf_path = contract_data.get('pdf_path', '')
            
            cursor.execute('''
                UPDATE contracts
                SET provider = ?, number = ?, date = ?, months = ?, type = ?,
                    comments = ?, expiry_date = ?, pdf_path = ?, pdf_paths = ?, special_data = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                contract_data['provider'],
                contract_data['number'],
                _to_iso(contract_data['date']),
                contract_data['months'],
                contract_data['type'],
                contract_data.get('comments', ''),
                _to_iso(contract_data.get('expiry_date')),
                pdf_path,
                pdf_paths_json,
                special_data_json,
                contract_data['id']
            ))
    
    def delete_contract(self, contract_id: str) -> None:
        """Διαγραφή σύμβασης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM contracts WHERE id = ?', (contract_id,))
    
    def search_contracts_comprehensive(self, search_text: str, category_filter: str) -> List[Dict[str, Any]]:
        """
        ΟΛΟΚΛΗΡΩΜΕΝΗ ΑΝΑΖΗΤΗΣΗ σε όλα τα πεδία των συμβάσεων
        """
        if not search_text and category_filter == "Όλα":
            return self.get_all_contracts()
            
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Βασική αναζήτηση σε κύρια πεδία
            query = '''
                SELECT * FROM contracts 
                WHERE (
                    provider LIKE ? OR 
                    number LIKE ? OR 
                    type LIKE ? OR 
                    comments LIKE ? OR
                    date LIKE ? OR
                    expiry_date LIKE ? OR
                    months LIKE ?
                )
            '''
            search_term = f'%{search_text}%'
            params: List[Any] = [search_term, search_term, search_term, search_term, 
                                 search_term, search_term, search_term]
            
            if category_filter != "Όλα":
                # Χρήση TRIM/LOWER για ανεκτικότητα σε κενά/πεζά-κεφαλαία
                query += ' AND TRIM(LOWER(type)) = TRIM(LOWER(?))'
                params.append(category_filter)
            
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            contracts = [self._parse_contract_row(row) for row in cursor.fetchall()]
            
            # Επιπλέον αναζήτηση σε special_data (JSON fields)
            if search_text:
                contracts_with_special_data = []
                for contract in contracts:
                    # Έλεγχος αν το search_text υπάρχει στα special_data
                    if self._search_in_special_data(contract, search_text):
                        contracts_with_special_data.append(contract)
                
                # Προσθήκη συμβάσεων που βρέθηκαν μόνο μέσα από special_data
                additional_contracts = self._search_only_in_special_data(search_text, category_filter)
                all_contracts = contracts + additional_contracts
                
                # Αφαίρεση duplicates
                seen_ids = set()
                unique_contracts = []
                for contract in all_contracts:
                    if contract['id'] not in seen_ids:
                        seen_ids.add(contract['id'])
                        unique_contracts.append(contract)
                
                return unique_contracts
            
            return contracts
    
    def _search_in_special_data(self, contract: Dict[str, Any], search_text: str) -> bool:
        """Αναζήτηση στο special_data JSON field"""
        special_data_str = contract.get('special_data', '{}')
        if not special_data_str:
            return False
            
        try:
            special_data = json.loads(special_data_str)
            search_text_lower = search_text.lower()
            
            # Αναζήτηση σε όλες τις τιμές του special_data
            for key, value in special_data.items():
                if value and search_text_lower in str(value).lower():
                    return True
                    
            # Αναζήτηση στα μεταφρασμένα ονόματα των πεδίων
            for key, greek_name in SPECIAL_FIELD_TRANSLATIONS.items():
                if search_text_lower in greek_name.lower():
                    return True
                    
        except json.JSONDecodeError:
            return False
            
        return False
    
    def _search_only_in_special_data(self, search_text: str, category_filter: str) -> List[Dict[str, Any]]:
        """Αναζήτηση ΜΟΝΟ σε special_data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM contracts WHERE 1=1'
            params: List[Any] = []
            
            if category_filter != "Όλα":
                # Χρήση TRIM/LOWER για ανεκτικότητα σε κενά/πεζά-κεφαλαία
                query += ' AND TRIM(LOWER(type)) = TRIM(LOWER(?))'
                params.append(category_filter)
            
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            all_contracts = [self._parse_contract_row(row) for row in cursor.fetchall()]
            
            # Φιλτράρισμα μόνο εκείνων που έχουν το search_text στο special_data
            filtered_contracts = []
            for contract in all_contracts:
                if self._search_in_special_data(contract, search_text):
                    filtered_contracts.append(contract)
            
            return filtered_contracts
    
    def advanced_search_contracts(self, search_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Προχωρημένη αναζήτηση με πολλαπλά κριτήρια
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM contracts WHERE 1=1'
            params: List[Any] = []
            
            # Βασική αναζήτηση κειμένου
            if search_params.get('search_text'):
                search_term = f'%{search_params["search_text"]}%'
                query += ''' AND (
                    provider LIKE ? OR 
                    number LIKE ? OR 
                    type LIKE ? OR 
                    comments LIKE ? OR
                    date LIKE ? OR
                    expiry_date LIKE ? OR
                    months LIKE ?
                )'''
                params.extend([search_term, search_term, search_term, search_term,
                             search_term, search_term, search_term])
            
            # Φίλτρο κατηγορίας
            if search_params.get('category_filter') and search_params['category_filter'] != "Όλα":
                # Χρήση TRIM/LOWER για ανεκτικότητα σε κενά/πεζά-κεφαλαία
                query += ' AND TRIM(LOWER(type)) = TRIM(LOWER(?))'
                params.append(search_params['category_filter'])
            
            # Φίλτρο ημερομηνίας (whitelist για αποφυγή SQL injection)
            ALLOWED_DATE_COLUMNS = {'date', 'expiry_date'}
            date_type = search_params.get('date_type', 'date')
            if date_type not in ALLOWED_DATE_COLUMNS:
                date_type = 'date'
            
            if search_params.get('date_from') and validate_date(search_params['date_from']):
                query += f' AND {date_type} >= ?'
                params.append(_to_iso(search_params['date_from']))
            
            if search_params.get('date_to') and validate_date(search_params['date_to']):
                query += f' AND {date_type} <= ?'
                params.append(_to_iso(search_params['date_to']))
            
            # Φίλτρο PDF
            if search_params.get('has_pdf') is not None:
                if search_params['has_pdf']:
                    query += ' AND pdf_path IS NOT NULL AND pdf_path != ""'
                else:
                    query += ' AND (pdf_path IS NULL OR pdf_path = "")'
            
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            contracts = [self._parse_contract_row(row) for row in cursor.fetchall()]
            
            # Εφαρμογή φίλτρου κατάστασης στη Python
            if search_params.get('status_filter') and search_params['status_filter'] != "Όλες":
                contracts = [c for c in contracts if get_contract_status(c.get('expiry_date')) == search_params['status_filter']]
            
            # Φίλτρο special fields
            if search_params.get('special_field'):
                special_field_filters = search_params['special_field']
                filtered_contracts = []
                for contract in contracts:
                    special_data_str = contract.get('special_data', '{}')
                    try:
                        special_data = json.loads(special_data_str)
                        match = True
                        for field, value in special_field_filters.items():
                            if value and special_data.get(field) != value:
                                match = False
                                break
                        if match:
                            filtered_contracts.append(contract)
                    except json.JSONDecodeError:
                        continue
                contracts = filtered_contracts
            
            return contracts
    
    def get_contracts_by_type(self, contract_type: str) -> List[Dict[str, Any]]:
        """Λήψη συμβάσεων ανά τύπο"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Χρήση TRIM/LOWER για ανεκτικότητα σε κενά/πεζά-κεφαλαία
            cursor.execute(
                'SELECT * FROM contracts WHERE TRIM(LOWER(type)) = TRIM(LOWER(?)) ORDER BY created_at DESC',
                (contract_type,)
            )
            return [self._parse_contract_row(row) for row in cursor.fetchall()]
    
    def get_expiring_contracts(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Λήψη συμβάσεων που λήγουν σύντομα ή έχουν λήξει"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM contracts WHERE expiry_date IS NOT NULL ORDER BY expiry_date ASC')
            contracts = [self._parse_contract_row(row) for row in cursor.fetchall()]
            
            expiring_soon = []
            expired = []
            
            for contract in contracts:
                status = get_contract_status(contract.get('expiry_date'))
                if status == "EXPIRING_SOON":
                    expiring_soon.append(contract)
                elif status == "EXPIRED":
                    expired.append(contract)
            
            return expired, expiring_soon
    
    def get_statistics(self) -> Dict[str, Any]:
        """Στατιστικά για συμβάσεις"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Σύνολο συμβάσεων
            cursor.execute('SELECT COUNT(*) as total FROM contracts')
            row = cursor.fetchone()
            total = row[0] if row else 0
            
            # Κατανομή ανά τύπο
            cursor.execute('SELECT type, COUNT(*) as count FROM contracts GROUP BY type')
            by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Κατανομή ανά κατάσταση
            cursor.execute('SELECT expiry_date FROM contracts')
            expiry_dates = [row[0] for row in cursor.fetchall()]
            
            by_status = {"ACTIVE": 0, "EXPIRING_SOON": 0, "EXPIRED": 0, "NO_DATE": 0}
            for expiry_date in expiry_dates:
                status = get_contract_status(expiry_date)
                by_status[status] = by_status.get(status, 0) + 1
            
            return {
                'total': total,
                'by_type': by_type,
                'by_status': by_status
            }
    
    def fts_search(self, search_text: str) -> List[Dict[str, Any]]:
        """FTS5 αναζήτηση - Πολύ γρηγορότερη, με υποστήριξη πολλαπλών όρων"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Sanitize search text
            search_text = search_text.replace('"', '""')
            
            # Split terms and add wildcard to each for prefix matching
            terms = search_text.split()
            if not terms:
                return []
                
            # Create FTS query: "term1"* "term2"* ... (Implicit AND)
            fts_query = ' '.join([f'"{term}"*' for term in terms])
            
            query = '''
                SELECT DISTINCT c.* FROM contracts c
                INNER JOIN contracts_fts fts ON c.id = fts.id
                WHERE contracts_fts MATCH ?
                ORDER BY rank, c.created_at DESC
            '''
            
            cursor.execute(query, (fts_query,))
            return [self._parse_contract_row(row) for row in cursor.fetchall()]
    
    def fuzzy_search(self, search_text: str, category_filter: str = "Όλα") -> List[Dict[str, Any]]:
        """Αναζήτηση με split όρων - Κάθε όρος πρέπει να υπάρχει σε κάποιο από τα πεδία"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            terms = search_text.split()
            if not terms:
                return self.get_all_contracts()
            
            query = 'SELECT * FROM contracts WHERE 1=1'
            params: List[Any] = []
            
            if category_filter != "Όλα":
                # Χρήση TRIM/LOWER για ανεκτικότητα σε κενά/πεζά-κεφαλαία
                query += ' AND TRIM(LOWER(type)) = TRIM(LOWER(?))'
                params.append(category_filter)
            
            for term in terms:
                term_like = f'%{term}%'
                query += ''' AND (
                    provider LIKE ? OR 
                    number LIKE ? OR 
                    type LIKE ? OR 
                    comments LIKE ? OR
                    date LIKE ? OR
                    expiry_date LIKE ? OR
                    months LIKE ?
                )'''
                params.extend([term_like] * 7)
            
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            return [self._parse_contract_row(row) for row in cursor.fetchall()]
    
    def bulk_delete_contracts(self, contract_ids: List[str]) -> int:
        """Πολλαπλή διαγραφή συμβάσεων"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for contract_id in contract_ids:
                cursor.execute('DELETE FROM contracts WHERE id = ?', (contract_id,))
            
            return len(contract_ids)
    
    def bulk_update_type(self, contract_ids: List[str], new_type: str) -> int:
        """Αλλαγή τύπου για πολλαπλές συμβάσεις"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for contract_id in contract_ids:
                cursor.execute('''
                    UPDATE contracts 
                    SET type = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_type, contract_id))
            
            return len(contract_ids)

    def rename_category_in_contracts(self, old_type: str, new_type: str) -> Tuple[int, List[str]]:
        """
        Μετονομασία τύπου (κατηγορίας) σε όλες τις συμβάσεις που το χρησιμοποιούν.
        Εκτελείται μέσα σε transaction για ακεραιότητα δεδομένων.
        Δημιουργεί και αντίστοιχες εκδόσεις συμβάσεων (contract versions).

        Επιστρέφει: (αριθμός_ενημερωμένων_συμβάσεων, λίστα_ids_ενημερωμένων_συμβάσεων)
        """
        updated_ids: List[str] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM contracts
                WHERE TRIM(LOWER(type)) = TRIM(LOWER(?))
            ''', (old_type,))
            rows = cursor.fetchall()

            if not rows:
                return 0, []

            for row in rows:
                contract_id = row['id']

                cursor.execute('''
                    UPDATE contracts
                    SET type = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (new_type, contract_id))

                try:
                    contract_dict = self._parse_contract_row(row)
                    contract_dict['type'] = new_type
                    contract_json = json.dumps(contract_dict, ensure_ascii=False, indent=2)

                    cursor.execute(
                        'SELECT MAX(version_number) FROM contract_versions WHERE contract_id = ?',
                        (contract_id,)
                    )
                    ver_row = cursor.fetchone()
                    next_version = (ver_row[0] if ver_row and ver_row[0] else 0) + 1

                    version_id = str(uuid.uuid4())
                    change_desc = f"Αυτόματη αλλαγή είδους σύμβασης: '{old_type}' → '{new_type}'"

                    cursor.execute('''
                        INSERT INTO contract_versions
                        (id, contract_id, version_number, created_at, created_by, change_description, contract_data)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
                    ''', (version_id, contract_id, next_version, "System", change_desc, contract_json))
                except Exception as ver_err:
                    logger.warning(
                        f"Αδυναμία δημιουργίας έκδοσης για σύμβαση {contract_id}: {ver_err}"
                    )

                updated_ids.append(contract_id)

            self._rebuild_fts_sync(cursor)

        return len(updated_ids), updated_ids

    def _rebuild_fts_sync(self, cursor) -> None:
        """
        Επανασυγχρονισμός του FTS5 virtual table μετά από μαζικές αλλαγές.
        Χρησιμοποιεί το διάγνωσμα 'rebuild' της SQLite FTS5 για πλήρη ακεραιότητα.
        """
        try:
            cursor.execute("INSERT INTO contracts_fts(contracts_fts) VALUES('rebuild')")
        except Exception as fts_err:
            logger.warning(f"FTS5 rebuild warning: {fts_err}")
    
    def bulk_export_contracts(self, contract_ids: List[str]) -> List[Dict[str, Any]]:
        """Εξαγωγή επιλεγμένων συμβάσεων"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            placeholders = ','.join('?' * len(contract_ids))
            query = f'SELECT * FROM contracts WHERE id IN ({placeholders}) ORDER BY created_at DESC'
            
            cursor.execute(query, contract_ids)
            return [self._parse_contract_row(row) for row in cursor.fetchall()]

    def migrate_from_json(self, json_file: str) -> bool:
        """Μεταφορά δεδομένων από JSON σε SQLite"""
        if not os.path.exists(json_file):
            return False
            
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                contracts_data = json.load(f)
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for contract in contracts_data:
                    special_data_json = json.dumps(contract.get('special_data', {}), ensure_ascii=False)
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO contracts 
                        (id, provider, number, date, months, type, comments, expiry_date, pdf_path, special_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        contract['id'],
                        contract['provider'],
                        contract['number'],
                        contract['date'],
                        contract['months'],
                        contract['type'],
                        contract.get('comments', ''),
                        contract.get('expiry_date'),
                        contract.get('pdf_path', ''),
                        special_data_json
                    ))
            
            backup_json = json_file + '.backup'
            shutil.copy2(json_file, backup_json)
            
            return True
            
        except Exception as e:
            print(f"Migration error: {e}")
            return False
    
    # =========================================================================
    # === ΔΙΑΧΕΙΡΙΣΗ ΕΚΔΟΣΕΩΝ ΣΥΜΒΑΣΕΩΝ ===
    # =========================================================================
    
    def create_contract_version(self, contract_data: Dict[str, Any], 
                               change_description: str = "", 
                               created_by: str = "System") -> str:
        """Δημιουργία νέας έκδοσης μιας σύμβασης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            contract_id = contract_data['id']
            
            # Λήψη του επόμενου αριθμού έκδοσης
            cursor.execute(
                'SELECT MAX(version_number) FROM contract_versions WHERE contract_id = ?',
                (contract_id,)
            )
            row = cursor.fetchone()
            next_version = (row[0] if row and row[0] else 0) + 1
            
            # Αποθήκευση των δεδομένων της σύμβασης ως JSON
            contract_json = json.dumps(contract_data, ensure_ascii=False, indent=2)
            
            version_id = str(uuid.uuid4())
            
            cursor.execute('''
                INSERT INTO contract_versions 
                (id, contract_id, version_number, created_by, change_description, contract_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (version_id, contract_id, next_version, created_by, change_description, contract_json))
            
            return version_id
    
    def get_contract_versions(self, contract_id: str) -> List[Dict[str, Any]]:
        """Λήψη όλων των εκδόσεων μιας σύμβασης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, contract_id, version_number, created_at, created_by, change_description
                FROM contract_versions
                WHERE contract_id = ?
                ORDER BY version_number DESC
            ''', (contract_id,))
            
            versions = []
            for row in cursor.fetchall():
                versions.append({
                    'id': row[0],
                    'contract_id': row[1],
                    'version_number': row[2],
                    'created_at': row[3],
                    'created_by': row[4],
                    'change_description': row[5]
                })
            
            return versions
    
    def get_version_data(self, version_id: str) -> Optional[Dict[str, Any]]:
        """Λήψη των δεδομένων μιας συγκεκριμένης έκδοσης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT contract_data FROM contract_versions WHERE id = ?',
                (version_id,)
            )
            row = cursor.fetchone()
            
            if row:
                try:
                    data = json.loads(row[0])
                    if 'date' in data:
                        data['date'] = _to_greek(data['date'])
                    if 'expiry_date' in data:
                        data['expiry_date'] = _to_greek(data['expiry_date'])
                    return data
                except json.JSONDecodeError:
                    return None
            
            return None
    
    def restore_contract_version(self, version_id: str, 
                                restore_description: str = "Επαναφορά σύμβασης") -> bool:
        """Επαναφορά μιας σύμβασης σε προηγούμενη έκδοση"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Λήψη των δεδομένων της έκδοσης
            cursor.execute(
                'SELECT contract_id, contract_data FROM contract_versions WHERE id = ?',
                (version_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return False
            
            contract_id, contract_json = row
            
            try:
                contract_data = json.loads(contract_json)
                
                # Ενημέρωση της τρέχουσας σύμβασης με τα δεδομένα της έκδοσης
                self.update_contract(contract_data)
                
                # Δημιουργία νέας έκδοσης για την επαναφορά
                self.create_contract_version(
                    contract_data,
                    f"{restore_description} (Επαναφορά από έκδοση {version_id[:8]}...)",
                    "System"
                )
                
                return True
            except Exception as e:
                print(f"Error restoring version: {e}")
                return False
    
    def get_version_changes(self, version_id: str, prev_version_id: Optional[str] = None) -> Dict[str, Any]:
        """Σύγκριση δύο εκδόσεων και εξαγωγή των αλλαγών"""
        current_data = self.get_version_data(version_id)
        
        if not current_data:
            return {}
        
        if prev_version_id:
            prev_data = self.get_version_data(prev_version_id)
            if not prev_data:
                return {'current': current_data}
        else:
            prev_data = None
        
        changes = {
            'current': current_data,
            'previous': prev_data,
            'differences': {}
        }
        
        if prev_data:
            # Βρίσκουμε τις διαφορές
            for key in set(list(current_data.keys()) + list(prev_data.keys())):
                current_val = current_data.get(key)
                prev_val = prev_data.get(key)
                
                if current_val != prev_val:
                    changes['differences'][key] = {
                        'from': prev_val,
                        'to': current_val
                    }
        
        return changes
    
    def delete_contract_version(self, version_id: str) -> bool:
        """Διαγραφή μιας έκδοσης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM contract_versions WHERE id = ?', (version_id,))
            return cursor.rowcount > 0
    
    def count_versions(self, contract_id: str) -> int:
        """Μέτρηση εκδόσεων μιας σύμβασης"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) FROM contract_versions WHERE contract_id = ?',
                (contract_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else 0
