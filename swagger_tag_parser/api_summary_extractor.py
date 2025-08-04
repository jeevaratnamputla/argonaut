import json

def load_swagger(path):
    with open(path) as f:
        return json.load(f)

def extract_summaries_by_service(swagger, service_tag):
    summaries = []
    for path, methods in swagger.get("paths", {}).items():
        for method, details in methods.items():
            if service_tag in details.get("tags", []):
                summary = details.get("summary")
                if summary:
                    summaries.append(summary)
    return {
        "service": service_tag,
        "summaries": summaries
    }

if __name__ == "__main__":
    swagger_path = "swagger.json"
    swagger = load_swagger(swagger_path)

    service_tag = input("Enter service tag (e.g., ApplicationService): ").strip()
    result = extract_summaries_by_service(swagger, service_tag)

    print("\nSummaries for service:", result["service"])
    for i, summary in enumerate(result["summaries"], 1):
        print(f"{i}. {summary}")
