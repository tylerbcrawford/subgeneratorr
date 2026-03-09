# Tests

## Keyterms Consistency Test

The included test validates keyterm extraction and saving logic:

```bash
# From project root
python3 -m pytest tests/test_keyterms_consistency.py -v
```

### What it tests

- Keyterm CSV round-trip (save and reload)
- Deduplication and normalization
- Empty input handling
- Special character preservation

### Requirements

- Python 3.9+
- No API key or Docker required (unit tests only)
