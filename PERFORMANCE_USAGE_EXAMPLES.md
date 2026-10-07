# Παραδείγματα Χρήσης - Βελτιώσεις Απόδοσης

## 1. Παρακολούθηση Cache Statistics

Μπορείτε να προσθέσετε ένα κουμπί στο dashboard για να δείτε τα statistics του cache:

```python
# Στο dashboard_view.py ή στο contract_manager.py
def show_cache_stats(self):
    stats = self.get_cache_stats()
    message = f"""
    📊 Στατιστικά Cache:
    
    • Μέγεθος Cache: {stats['cache_size']} / {stats['max_cache_size']}
    • Χρήση: {stats['cache_usage_percent']:.1f}%
    
    Το cache αποθηκεύει τα αποτελέσματα αναζήτησης
    για ταχύτερη πρόσβαση.
    """
    messagebox.showinfo("Cache Statistics", message)
```

---

## 2. Χειροκίνητη Εκκαθάριση Cache

Αν θέλετε να προσθέσετε ένα κουμπί για χειροκίνητη εκκαθάριση:

```python
def manual_clear_cache(self):
    cache_size = len(self._search_cache)
    self._clear_search_cache()
    messagebox.showinfo(
        "Cache Cleared", 
        f"Εκκαθαρίστηκαν {cache_size} cached αποτελέσματα."
    )
```

---

## 3. Προσαρμογή Παραμέτρων Απόδοσης

Μπορείτε να προσαρμόσετε τις παραμέτρους ανάλογα με τις ανάγκες σας:

```python
# Για πολύ γρήγορα συστήματα (μειώστε τα delays):
self._min_query_interval = 0.1  # 100ms
self._debounce_delay = 300      # 300ms

# Για αργά συστήματα (αυξήστε τα delays):
self._min_query_interval = 0.2  # 200ms
self._debounce_delay = 500      # 500ms

# Για μεγάλες βάσεις δεδομένων (αυξήστε το cache):
self._max_cache_size = 200      # 200 entries
```

---

## 4. Debugging Performance Issues

Προσθέστε logging για να παρακολουθείτε την απόδοση:

```python
import time
import logging

def apply_filters(self):
    start_time = time.time()
    
    # ... existing code ...
    
    elapsed = time.time() - start_time
    logging.info(f"apply_filters took {elapsed*1000:.2f}ms")
    
    if cache_key in self._search_cache:
        logging.info("Cache HIT")
    else:
        logging.info("Cache MISS - executing query")
```

---

## 5. Προφίλ Απόδοσης για Διαφορετικά Σενάρια

### Σενάριο A: Μικρή Βάση (<100 συμβάσεις)
```python
self._min_query_interval = 0.05  # 50ms
self._debounce_delay = 200       # 200ms
self._max_cache_size = 50        # 50 entries
```

### Σενάριο B: Μεσαία Βάση (100-1000 συμβάσεις)
```python
self._min_query_interval = 0.15  # 150ms (default)
self._debounce_delay = 400       # 400ms (default)
self._max_cache_size = 100       # 100 entries (default)
```

### Σενάριο C: Μεγάλη Βάση (>1000 συμβάσεις)
```python
self._min_query_interval = 0.25  # 250ms
self._debounce_delay = 600       # 600ms
self._max_cache_size = 200       # 200 entries
```

---

## 6. Monitoring Cache Effectiveness

Προσθέστε ένα counter για cache hits/misses:

```python
def __init__(self):
    # ... existing code ...
    self._cache_hits = 0
    self._cache_misses = 0

def apply_filters(self):
    # ... existing code ...
    
    if cache_key in self._search_cache:
        self._cache_hits += 1
    else:
        self._cache_misses += 1

def get_cache_effectiveness(self):
    total = self._cache_hits + self._cache_misses
    if total == 0:
        return 0
    return (self._cache_hits / total) * 100
```

---

## 7. Αυτόματη Προσαρμογή Παραμέτρων

Δυναμική προσαρμογή βάσει του μεγέθους της βάσης:

```python
def auto_tune_performance(self):
    """Automatically adjust performance parameters based on database size."""
    contract_count = len(self.contracts_data)
    
    if contract_count < 100:
        self._debounce_delay = 200
        self._max_cache_size = 50
    elif contract_count < 1000:
        self._debounce_delay = 400
        self._max_cache_size = 100
    else:
        self._debounce_delay = 600
        self._max_cache_size = 200
    
    logging.info(f"Auto-tuned for {contract_count} contracts")
```

Καλέστε αυτή τη μέθοδο στο `load_data_from_db()`:

```python
def load_data_from_db(self):
    self.contracts_data = self.db_manager.get_all_contracts()
    self.auto_tune_performance()  # Auto-tune based on data size
```

---

## 8. Testing Performance Improvements

Δοκιμαστικό script για να μετρήσετε τη βελτίωση:

```python
import time

def benchmark_search():
    """Benchmark search performance."""
    test_queries = ["test", "energy", "2024", "provider"]
    
    # Clear cache first
    app._clear_search_cache()
    
    # First run (cold cache)
    cold_times = []
    for query in test_queries:
        app.entry_search.delete(0, 'end')
        app.entry_search.insert(0, query)
        
        start = time.time()
        app.apply_filters()
        cold_times.append(time.time() - start)
    
    # Second run (warm cache)
    warm_times = []
    for query in test_queries:
        app.entry_search.delete(0, 'end')
        app.entry_search.insert(0, query)
        
        start = time.time()
        app.apply_filters()
        warm_times.append(time.time() - start)
    
    print(f"Cold cache avg: {sum(cold_times)/len(cold_times)*1000:.2f}ms")
    print(f"Warm cache avg: {sum(warm_times)/len(warm_times)*1000:.2f}ms")
    print(f"Improvement: {(1 - sum(warm_times)/sum(cold_times))*100:.1f}%")
```

---

## Συμπέρασμα

Οι βελτιώσεις απόδοσης που εφαρμόστηκαν παρέχουν:
- ✅ Ταχύτερη αναζήτηση
- ✅ Λιγότερο φορτίο στη βάση δεδομένων
- ✅ Καλύτερη εμπειρία χρήστη
- ✅ Μειωμένη κατανάλωση πόρων

Μπορείτε να προσαρμόσετε τις παραμέτρους ανάλογα με τις ανάγκες σας!
