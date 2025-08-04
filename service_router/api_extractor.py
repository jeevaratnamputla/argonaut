import json

def get_api_by_summary(swagger_path, summary):
    with open(swagger_path) as f:
        swagger = json.load(f)
    for path, path_item in swagger.get("paths", {}).items():
        for method, operation in path_item.items():
            if operation.get("summary", "") == summary:
                return {
                    "path": path,
                    "method": method.upper(),
                    "operationId": operation.get("operationId", ""),
                    "details": operation
                }
    return {}