# EPA DATA COLLECTIOn

It's defined in `endpoint_categories.py` and `collector.py` (relative to app root).

## Collectors

Add it to the category in `endpoint_categories.py`:

```python
ENDPOINT_CATEGORIES = {
    EndpointCategory.EVENTS: {
        'system_events',
        'lockdown_status',
        'new_failure_alerts',  # ← ADD NEW ENDPOINT HERE
        'drive_rebuild_status', # ← OR HERE
        # ...
    }
}
```

Add the API path to `collector.py`:

```python
API_ENDPOINTS = {
    # ...
    'new_failure_alerts': 'devmgr/v2/storage-systems/{system_id}/failures',
    'drive_rebuild_status': 'devmgr/v2/storage-systems/{system_id}/drives/rebuild-status',
}
```

Recategorize if needed:

```python
# Move from EVENTS to CONFIGURATION (if it's more static than you thought)
ENDPOINT_CATEGORIES = {
    EndpointCategory.CONFIGURATION: {
        'snapshot_schedules',  # ← MOVED FROM EVENTS
        # ...
    },
    EndpointCategory.EVENTS: {
        'lockdown_status',
        # 'snapshot_schedules',  ← REMOVE FROM HERE
        # ...
    }
}
```

Helper functions:

```python
# Check if all your endpoints are categorized
validation = validate_endpoint_coverage(all_known_endpoints)
print("Uncategorized:", validation['uncategorized'])

# Get all event endpoints
event_endpoints = get_endpoints_by_category(EndpointCategory.EVENTS)

# Check what category an endpoint belongs to
category = get_endpoint_category('lockdown_status')  # Returns EndpointCategory.EVENTS
```

Each collector automatically uses the categorization:

- ConfigCollector: Only collects `EndpointCategory.CONFIGURATION` endpoints
- PerformanceCollector: Only collects `EndpointCategory.PERFORMANCE` endpoints
- EventCollector: Only collects `EndpointCategory.EVENTS` endpoints

Example:

```python
# EventCollector automatically gets all event endpoints
self.event_endpoints = get_endpoints_by_category(EndpointCategory.EVENTS)
```

## API Endpoints

They're defined in `collector.py` (`API_ENDPOINTS`).

## Hierachical collection (`ESeriesCollector` class)

These can be found the same file, `ID_DEPENDENCIES`.

- ID Dependencies Configuration (`collector.py`):
  - `ID_DEPENDENCIES` dict - defines which endpoints need parent IDs
  - The endpoint must be listed and have correct `id_source` and `id_field`
- Collection Logic (collector.py):
  - `collect_hierarchical_data()` method - orchestrates the hierarchical collection
  - `_collect_with_id_dependency()` method - handles individual ID-dependent endpoints
  - `_build_api_url_with_id()` method - constructs URLs with parent IDs
- Endpoint Categorization (endpoint_categories.py):
  - Ensure ID-dependent endpoints are in the right category (usually CONFIGURATION)
  - Actual collection behaviors should match expected behaviors
- Integration Points (`main.py`):
 - All three collectors (Config, Performance, Event) are instantiated
 - Event collection is integrated in the main loop

```python
# Test imports and basic functionality
python -c "from app.collectors.collector import ESeriesCollector; print('OK - import works')"

# Test ID dependencies are defined
python -c "from app.collectors.collector import ESeriesCollector; c = ESeriesCollector({'from_json': False}); print('Dependencies:', list(c.ID_DEPENDENCIES.keys()))"
```
