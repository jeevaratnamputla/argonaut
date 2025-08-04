import json

def get_summaries_for_service(swagger_path, service_tag):
    with open(swagger_path) as f:
        swagger = json.load(f)
    summaries = []
    for path, path_item in swagger.get("paths", {}).items():
        for method, operation in path_item.items():
            if service_tag in operation.get("tags", []):
                summaries.append(operation.get("summary", ""))
    return summaries