**All work will eventually connect to an Model Context Protocol (MCP) server. Keep that in mind.

Build all test scripts in the "test_scripts" directory
Build all auth scripts in the "auth" directory
Build all project scripts in the "project" directory
Build all utility/helper scripts in the "utils" directory

AUTH EXAMPLE FOR VANTAGEPOINT (payload will need to be encoded in the request):
```python
# Example of how to authenticate with VantagePoint API
import httpx
import json

url = "https://az-webui-01.global.gsp/api/v1/auths/api_key"

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer TOKEN_HERE",
}

payload = {}  # Empty dict → same as sending `{}` JSON

with httpx.Client() as client:
    response = client.post(url, headers=headers, json=payload)

print(response.text)


