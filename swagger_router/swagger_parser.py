import json

class SwaggerIndex:
    def __init__(self, swagger_path):
        with open(swagger_path) as f:
            self.swagger = json.load(f)
        self.index = self._build_index()

    def _build_index(self):
        index = []
        for path, methods in self.swagger["paths"].items():
            for method, details in methods.items():
                index.append({
                    "path": path,
                    "method": method.upper(),
                    "summary": details.get("summary", ""),
                    "tags": details.get("tags", []),
                    "operationId": details.get("operationId", ""),
                    "parameters": details.get("parameters", []),
                    "requestBody": details.get("requestBody", {})
                })
        return index

    def search(self, keyword):
        keyword = keyword.lower()
        results = []
        for item in self.index:
            fields_to_search = [
                item.get("summary", "").lower(),
                item.get("operationId", "").lower(),
                " ".join(item.get("tags", [])).lower()
            ]
            if any(keyword in field for field in fields_to_search):
                results.append(item)
        return results
