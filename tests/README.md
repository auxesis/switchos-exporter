# Test suite

The tests run the full parse pipeline against **captured device responses** —
no network or real switch required. Each device's raw `.b` endpoint bodies live
under `tests/fixtures/<device>/`, and `conftest.py` patches
`SwitchOSClient._make_request` to serve them, so `collect_metrics()` runs exactly
as it would against the live device.

```
tests/
├── fixtures/
│   ├── swos_css106/        # MikroTik CSS106-1G-4P-1S  (SwOS)
│   ├── swos_crs309/        # MikroTik CRS309-1G-8S+IN  (SwOS)
│   └── swoslite_css610/    # MikroTik CSS610-8P-2S+IN  (SwOS Lite)
├── conftest.py             # fixture-backed client + device registry
├── redact.py               # strips identifiers from captured fixtures
├── test_collection.py      # every metric family, per device
├── test_parity.py          # SwOS vs SwOS Lite parity (+ known gaps)
├── test_regressions.py     # one test per bug fixed
├── test_config.py          # YAML config loading + settings
└── test_exporter.py        # metric labels + /metrics & /health endpoints
```

Run them with `pytest -q` (or `mise run test`). Dev dependencies are in
`requirements-dev.txt` (`pip install -r requirements-dev.txt`).

## Adding test data from a new device

1. **Capture** every endpoint from the switch (replace `IP` and credentials):

   ```bash
   DIR=tests/fixtures/<vendor_model>          # e.g. swoslite_css318
   mkdir -p "$DIR"
   for ep in link.b sfp.b stats.b '!stats.b' fwd.b vlan.b '!dhost.b' sys.b poe.b; do
     fname=$(echo "$ep" | sed 's/^!/bang_/')   # '!stats.b' -> 'bang_stats.b'
     curl -s --digest -u admin:PASSWORD "http://IP/$ep" > "$DIR/$fname"
   done
   ```

   Capture all of them even if some come back empty — an empty `stats.b` with a
   populated `!stats.b`, for example, is exactly what exercises the fallback.

2. **Redact** device identifiers before committing (this repo is public):

   ```bash
   python3 tests/redact.py "$DIR"
   ```

   `redact.py` replaces MAC addresses (`mac`/`rmac`/`i03`/`i11` and every MAC in
   the host table), serial numbers (`sid`/`i04`), and IP addresses with fixed
   placeholders. Counters, port names, models and versions are left intact.
   Afterwards, grep the directory to confirm nothing identifying remains.

3. **Register** the device in `tests/conftest.py` by adding an entry to
   `DEVICES` (its `name`, a placeholder `ip`, model, and `os`: `swos` or
   `swos-lite`).

4. **Pin expectations** in `tests/test_collection.py` by adding the device to
   `EXPECTED` (port count, port names, MAC-table size, SFP/PoE counts, version,
   board, temperature). Run `pytest -q` — the parametrized tests now cover it.

If the new device is SwOS Lite and a metric comes out empty or wrong, it is
likely a new obfuscated-field layout; capture the firmware's web-UI JS (the
`.b` field mappings live there) and extend the relevant `_translate_swoslite_*`
table in `switchos_client.py`.
