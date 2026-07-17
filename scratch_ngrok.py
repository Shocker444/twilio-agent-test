import urllib.request
import json

try:
    resp = urllib.request.urlopen('http://127.0.0.1:4040/api/requests/http')
    data = json.loads(resp.read().decode('utf-8'))
    for req in data.get('requests', [])[:20]:
        method = req['request']['method']
        uri = req['request']['uri']
        resp_status = req.get('response', {}).get('status_code', 'N/A')
        print(f"[{method}] {uri} -> Status: {resp_status}")
except Exception as e:
    print(f"Error checking ngrok: {e}")
