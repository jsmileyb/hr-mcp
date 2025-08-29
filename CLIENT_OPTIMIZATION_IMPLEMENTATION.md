# HTTP Client Optimization Implementation

## Overview

This implementation optimizes HTTP client usage throughout the application by introducing a client registry pattern that shares AsyncClient instances across modules, eliminating redundant client creation/destruction and TLS handshakes.

## Problem Addressed

Previously, the application created new `httpx.AsyncClient` instances in multiple places:

- `main.py` - One shared client for GIA/OWUI operations
- `auth/power_automate_auth.py` - Created new client for each PA call
- `auth/graph_auth.py` - Created new client for each Graph token request
- `auth/vp_auth.py` - Created new client for each VP token request
- `utils/vantagepoint.py` - Created new client for each VP API call

This caused unnecessary latency due to repeated TLS handshakes and connection setup/teardown.

## Solution Implemented

### 1. Client Registry (`utils/client_registry.py`)

Created a centralized client registry that:

- Maintains one shared `AsyncClient` per host
- Automatically creates clients with sensible defaults
- Provides cleanup functionality
- Thread-safe and async-friendly

### 2. Updated Authentication Modules

Modified all auth modules to accept an optional `client` parameter:

**`auth/graph_auth.py`:**

```python
async def get_graph_token_async(client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
```

**`auth/power_automate_auth.py`:**

```python
async def call_pa_workflow_async(
    payload: Dict[str, Any],
    token: Optional[str],
    client: Optional[httpx.AsyncClient] = None
) -> Optional[Dict[str, Any]]:
```

**`auth/vp_auth.py`:**

```python
async def get_vantagepoint_token(client: Optional[httpx.AsyncClient] = None):
```

**`utils/vantagepoint.py`:**

```python
async def get_vacation_days(
    payload: Dict[str, Any],
    token: Optional[str],
    client: Optional[httpx.AsyncClient] = None
) -> Optional[Dict[str, Any]]:
```

### 3. Main Application Integration

Updated `main.py` to:

- Import and use the client registry
- Register the main GIA client with the registry
- Close all shared clients on shutdown

## Client Usage Pattern

### Before (Multiple Clients)

```
Module A: create client -> TLS handshake -> API call -> close client
Module B: create client -> TLS handshake -> API call -> close client
Module C: create client -> TLS handshake -> API call -> close client
```

### After (Shared Clients)

```
Startup: create clients per host -> TLS handshakes
Module A: use shared client -> API call
Module B: use shared client -> API call
Module C: use shared client -> API call
Shutdown: close all shared clients
```

## Benefits

1. **Performance**: Eliminates redundant TLS handshakes (typically 100-500ms each)
2. **Resource Efficiency**: Fewer open connections and socket handles
3. **Connection Reuse**: HTTP/2 multiplexing and keep-alive work optimally
4. **Backward Compatibility**: All existing function calls work unchanged
5. **Flexibility**: Functions can still accept custom clients when needed

## Default Client Configuration

Shared clients are created with optimized settings:

- **Timeout**: 10s connect, 60s read, 30s write, 30s pool
- **Limits**: 16 keep-alive connections, 64 max connections per host
- **HTTP/2**: Enabled for performance
- **Base URL**: Set to host for relative path support

## Testing

Created comprehensive test suite (`test_scripts/test_client_registry.py`) that verifies:

- Client sharing works correctly
- Different hosts get different clients
- Function signatures accept client parameters
- Cleanup functionality works properly

## Migration Notes

**No Breaking Changes:**

- All existing function calls work unchanged due to default parameters
- Environment variables unchanged
- API contracts maintained

**Performance Impact:**

- First request per host: Same performance (client creation + TLS handshake)
- Subsequent requests: 100-500ms faster per request
- Under load: Significantly reduced connection overhead

This optimization provides a significant performance improvement while maintaining full backward compatibility and code clarity.
