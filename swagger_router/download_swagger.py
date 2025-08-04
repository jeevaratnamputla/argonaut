import requests
import json
import os

url = "https://cd.apps.argoproj.io/swagger.json"
output_dir = "swagger_router"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "swagger.json")

response = requests.get(url)
if response.status_code == 200:
    with open(output_path, "w") as f:
        json.dump(response.json(), f, indent=2)
    print(f"Swagger JSON downloaded and saved to: {output_path}")
else:
    print(f"Failed to download Swagger JSON. Status: {response.status_code}")
