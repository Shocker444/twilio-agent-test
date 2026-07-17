
import requests

url = "https://geologic-wired-overplay.ngrok-free.dev/outbound"
payload = {"to_number": "+2348109491368"}
headers = {"Content-Type": "application/json"}

response = requests.request("POST", url, json=payload, headers=headers)

print(response.text)
