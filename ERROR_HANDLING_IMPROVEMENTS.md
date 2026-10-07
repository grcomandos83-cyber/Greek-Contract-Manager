# Βελτιώσεις Χειρισμού Σφαλμάτων - Contract Manager

## Περίληψη Αλλαγών

Έχουν εφαρμοστεί οι ακόλουθες βελτιώσεις στον χειρισμό σφαλμάτων του `contract_manager.py`:

---

## 1. Προσθήκη Logging System

### Τι Προστέθηκε:
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('contract_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
```

### Πλεονεκτήματα:
- ✅ Καταγραφή όλων των σημαντικών γεγονότων
- ✅ Αποθήκευση logs σε αρχείο `contract_manager.log`
- ✅ Εμφάνιση logs στην κονσόλα για debugging
- ✅ Timestamps για κάθε γεγονός
- ✅ Διαφορετικά επίπεδα logging (INFO, WARNING, ERROR)

---

## 2. Βελτιωμένος Χειρισμός Σφαλμάτων Βάσης Δεδομένων

### Μέθοδος: `process_contract_result()`

**Πριν:**
```python
except Exception as e:
    messagebox.showerror("Σφάλμα", f"Αποτυχία: {e}")
```

**Τώρα:**
```python
except sqlite3.Error as db_err:
    logger.error(f"Σφάλμα βάσης δεδομένων: {db_err}", exc_info=True)
    messagebox.showerror("Σφάλμα Βάσης Δεδομένων", 
                       f"Αποτυχία αποθήκευσης:\n\n{str(db_err)}")
except KeyError as key_err:
    logger.error(f"Λείπει πεδίο: {key_err}", exc_info=True)
    messagebox.showerror("Σφάλμα Δεδομένων", 
                       f"Λείπει απαιτούμενο πεδίο: {str(key_err)}")
except Exception as e:
    logger.error(f"Απροσδόκητο σφάλμα: {e}", exc_info=True)
    messagebox.showerror("Σφάλμα", f"Απροσδόκητο σφάλμα:\n\n{str(e)}")
```

### Πλεονεκτήματα:
- ✅ Διαχωρισμός σφαλμάτων βάσης από άλλα σφάλματα
- ✅ Συγκεκριμένα μηνύματα για κάθε τύπο σφάλματος
- ✅ Καταγραφή stack trace για debugging
- ✅ Καλύτερη εμπειρία χρήστη με σαφή μηνύματα

---

## 3. Βελτιωμένος Χειρισμός Αναζήτησης

### Μέθοδος: `apply_filters()`

**Νέα Χαρακτηριστικά:**
- Χειρισμός `sqlite3.OperationalError` για FTS errors
- Fallback σε fuzzy search αν το FTS αποτύχει
- Χειρισμός `tk.TclError` για widget destruction
- Logging για cache hits/misses

```python
try:
    filtered_contracts = self.db_manager.fts_search(search_text)
except sqlite3.OperationalError as fts_err:
    logger.warning(f"FTS search απέτυχε, χρήση fuzzy search: {fts_err}")
    filtered_contracts = self.db_manager.fuzzy_search(search_text, category_filter)
```

### Πλεονεκτήματα:
- ✅ Αυτόματη εναλλακτική λύση αν το FTS αποτύχει
- ✅ Καταγραφή cache performance
- ✅ Αποφυγή crashes κατά το κλείσιμο της εφαρμογής

---

## 4. Βελτιωμένος Χειρισμός Αρχείων PDF

### Μέθοδος: `open_pdf()`

**Νέοι Χειρισμοί:**
```python
except AttributeError:
    # os.startfile is Windows-only
    # Fallback to platform-specific opener
except FileNotFoundError as fnf_err:
    logger.error(f"Δεν βρέθηκε PDF viewer: {fnf_err}")
    messagebox.showerror("Σφάλμα Συστήματος", 
                       "Δεν βρέθηκε πρόγραμμα για άνοιγμα PDF.")
except OSError as os_err:
    logger.error(f"Σφάλμα λειτουργικού: {os_err}")
    messagebox.showerror("Σφάλμα Συστήματος", 
                       f"Σφάλμα κατά το άνοιγμα:\n\n{str(os_err)}")
```

### Πλεονεκτήματα:
- ✅ Cross-platform compatibility
- ✅ Σαφή μηνύματα για διαφορετικά σφάλματα
- ✅ Καταγραφή προβλημάτων συστήματος

---

## 5. Βελτιωμένη Εξαγωγή/Εισαγωγή Δεδομένων

### Μέθοδος: `export_data()`

**Νέοι Χειρισμοί:**
```python
except IOError as io_err:
    logger.error(f"Σφάλμα I/O: {io_err}", exc_info=True)
    messagebox.showerror("Σφάλμα Αρχείου", 
                       f"Αποτυχία εγγραφής:\n\n{str(io_err)}")
except json.JSONEncodeError as json_err:
    logger.error(f"Σφάλμα JSON: {json_err}", exc_info=True)
    messagebox.showerror("Σφάλμα JSON", 
                       f"Αποτυχία κωδικοποίησης:\n\n{str(json_err)}")
```

### Μέθοδος: `import_from_json()`

**Νέα Χαρακτηριστικά:**
- Μετρητής επιτυχιών/αποτυχιών
- Συνέχιση εισαγωγής ακόμα και αν κάποιες συμβάσεις αποτύχουν
- Λεπτομερή μηνύματα για κάθε τύπο σφάλματος

```python
success_count = 0
error_count = 0

for i, contract in enumerate(imported_data):
    try:
        # Import logic
        success_count += 1
    except sqlite3.Error as db_err:
        error_count += 1
        logger.error(f"Σφάλμα εισαγωγής σύμβασης {i+1}: {db_err}")

if error_count > 0:
    messagebox.showwarning("Εισαγωγή με Σφάλματα", 
                         f"Επιτυχείς: {success_count}\nΑποτυχίες: {error_count}")
```

### Πλεονεκτήματα:
- ✅ Μερική εισαγωγή αντί για πλήρη αποτυχία
- ✅ Λεπτομερής αναφορά αποτελεσμάτων
- ✅ Καταγραφή κάθε αποτυχίας για debugging

---

## 6. Βελτιωμένη Διαχείριση Ρυθμίσεων

### Μέθοδος: `load_settings()`

**Νέα Χαρακτηριστικά:**
- Fallback σε προεπιλογές αν το αρχείο λείπει
- Χειρισμός κατεστραμμένων αρχείων JSON
- Ενημέρωση χρήστη για προβλήματα

```python
except FileNotFoundError:
    logger.warning("Αρχείο ρυθμίσεων δεν βρέθηκε, χρήση προεπιλογών")
    self.settings = {"categories": [], "current_theme": "Minimalist"}
except json.JSONDecodeError as json_err:
    logger.error(f"Κατεστραμμένο αρχείο ρυθμίσεων: {json_err}")
    messagebox.showwarning("Σφάλμα Ρυθμίσεων", 
                         "Το αρχείο ρυθμίσεων είναι κατεστραμμένο.\n\nΘα χρησιμοποιηθούν προεπιλογές.")
```

### Πλεονεκτήματα:
- ✅ Η εφαρμογή δεν κρασάρει αν λείπουν ρυθμίσεις
- ✅ Αυτόματη επαναφορά σε προεπιλογές
- ✅ Ενημέρωση χρήστη για προβλήματα

---

## 7. Logging Levels

### Χρήση Διαφορετικών Επιπέδων:

**INFO** - Κανονικές λειτουργίες:
```python
logger.info(f"Ενημερώθηκε σύμβαση με ID: {contract_id}")
logger.info(f"Εξήχθησαν {count} συμβάσεις επιτυχώς")
```

**WARNING** - Προβλήματα που δεν σταματούν τη λειτουργία:
```python
logger.warning(f"FTS search απέτυχε, χρήση fuzzy search")
logger.warning(f"Αρχείο ρυθμίσεων δεν βρέθηκε")
```

**ERROR** - Σοβαρά σφάλματα:
```python
logger.error(f"Σφάλμα βάσης δεδομένων: {err}", exc_info=True)
logger.error(f"Αποτυχία εισαγωγής σύμβασης: {err}", exc_info=True)
```

**DEBUG** - Λεπτομερείς πληροφορίες:
```python
logger.debug(f"Cache hit για αναζήτηση: {search_text}")
logger.debug("Παράλειψη query λόγω minimum interval")
```

---

## 8. Ανάλυση Log File

### Παράδειγμα Log Entries:

```
2026-02-02 20:55:00 - __main__ - INFO - Ενημερώθηκε σύμβαση με ID: abc123
2026-02-02 20:55:05 - __main__ - DEBUG - Cache hit για αναζήτηση: ενέργεια
2026-02-02 20:55:10 - __main__ - WARNING - FTS search απέτυχε, χρήση fuzzy search: no such table: contracts_fts
2026-02-02 20:55:15 - __main__ - ERROR - Σφάλμα βάσης δεδομένων: UNIQUE constraint failed: contracts.id
Traceback (most recent call last):
  ...
```

### Πώς να Χρησιμοποιήσετε τα Logs:

1. **Εύρεση Προβλημάτων:**
   ```bash
   # Εμφάνιση μόνο σφαλμάτων
   grep "ERROR" contract_manager.log
   
   # Εμφάνιση warnings και errors
   grep -E "WARNING|ERROR" contract_manager.log
   ```

2. **Παρακολούθηση σε Πραγματικό Χρόνο:**
   ```bash
   tail -f contract_manager.log
   ```

3. **Στατιστικά:**
   ```bash
   # Μέτρηση σφαλμάτων
   grep -c "ERROR" contract_manager.log
   
   # Μέτρηση cache hits
   grep -c "Cache hit" contract_manager.log
   ```

---

## 9. Σύγκριση Πριν/Μετά

### Πριν:
```python
try:
    # operation
except Exception as e:
    messagebox.showerror("Σφάλμα", f"Αποτυχία: {e}")
```

**Προβλήματα:**
- ❌ Δεν ξέρουμε τι πήγε στραβά
- ❌ Δεν υπάρχει καταγραφή
- ❌ Γενικό μήνυμα σφάλματος
- ❌ Δύσκολο debugging

### Μετά:
```python
try:
    # operation
    logger.info("Επιτυχής λειτουργία")
except sqlite3.Error as db_err:
    logger.error(f"Σφάλμα βάσης: {db_err}", exc_info=True)
    messagebox.showerror("Σφάλμα Βάσης", f"Λεπτομέρειες: {db_err}")
except IOError as io_err:
    logger.error(f"Σφάλμα I/O: {io_err}", exc_info=True)
    messagebox.showerror("Σφάλμα Αρχείου", f"Λεπτομέρειες: {io_err}")
except Exception as e:
    logger.error(f"Απροσδόκητο: {e}", exc_info=True)
    messagebox.showerror("Σφάλμα", f"Λεπτομέρειες: {e}")
```

**Πλεονεκτήματα:**
- ✅ Συγκεκριμένος χειρισμός για κάθε τύπο σφάλματος
- ✅ Πλήρης καταγραφή με stack traces
- ✅ Σαφή μηνύματα στον χρήστη
- ✅ Εύκολο debugging

---

## 10. Best Practices που Εφαρμόστηκαν

1. **Συγκεκριμένες Εξαιρέσεις Πρώτα:**
   ```python
   except sqlite3.Error:  # Πιο συγκεκριμένο
   except IOError:        # Μέτρια συγκεκριμένο
   except Exception:      # Γενικό (τελευταίο)
   ```

2. **Logging με exc_info=True:**
   ```python
   logger.error("Σφάλμα", exc_info=True)  # Περιλαμβάνει stack trace
   ```

3. **Σαφή Μηνύματα Χρήστη:**
   ```python
   messagebox.showerror("Τίτλος Σφάλματος", 
                       f"Περιγραφή:\n\n{λεπτομέρειες}")
   ```

4. **Graceful Degradation:**
   ```python
   try:
       # Προτιμώμενη μέθοδος
   except:
       # Εναλλακτική μέθοδος
   ```

---

## Συμπέρασμα

Οι βελτιώσεις στον χειρισμό σφαλμάτων παρέχουν:
- ✅ Καλύτερη διαγνωστικότητα προβλημάτων
- ✅ Πιο σταθερή εφαρμογή
- ✅ Καλύτερη εμπειρία χρήστη
- ✅ Ευκολότερο debugging και maintenance
- ✅ Πλήρη καταγραφή γεγονότων

Το αρχείο `contract_manager.log` θα περιέχει όλες τις πληροφορίες που χρειάζεστε για debugging!

---

## Ημερομηνία Ενημέρωσης
2 Φεβρουαρίου 2026
