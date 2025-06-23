**All work will eventually connect to an Model Context Protocol (MCP) server. Keep that in mind.

Build all test scripts in the "test_scripts" directory
Build all auth scripts in the "auth" directory
Build all project scripts in the "project" directory
Build all utility/helper scripts in the "utils" directory

AUTH EXAMPLE FOR VANTAGEPOINT (payload will need to be encoded in the request):
```python
# Example of how to authenticate with VantagePoint API
import requests
url = "https://vp.greshamsmith.com/vantagepoint/api/token"

payload = 'Username=USER_NAME&Password=PASSWORD&grant_type=password&Integrated=N&database=Vantagepoint&Client_Id=CLIENT_ID&client_secret=SECRET'
headers = {
  'Content-Type': 'application/x-www-form-urlencoded'
}
response = requests.request("POST", url, headers=headers, data=payload)

