import json

def load_swagger(path):
    with open(path) as f:
        return json.load(f)

def find_api_by_summary(swagger, summary_text):
    matches = []
    for path, methods in swagger.get("paths", {}).items():
        for method, details in methods.items():
            if details.get("summary", "").strip().lower() == summary_text.strip().lower():
                matches.append({
                    "path": path,
                    "method": method.upper(),
                    "operation": details
                })
    return matches

if __name__ == "__main__":
    swagger_path = "swagger.json"
    swagger = load_swagger(swagger_path)

    summary_input = input("Enter exact summary to look up: ").strip()
    results = find_api_by_summary(swagger, summary_input)

    if not results:
        print("No matching API found.")
    else:
        for result in results:
            print(f"\nPath: {result['path']}")
            print(f"Method: {result['method']}")
            print("Full API definition:")
            print(json.dumps(result["operation"], indent=2))
