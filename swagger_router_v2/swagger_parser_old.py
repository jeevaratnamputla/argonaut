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

    def get_all_tags(self):
        tags = set()
        for item in self.index:
            for tag in item.get("tags", []):
                tags.add(tag)
        return list(tags)

    def match_tag_from_query(self, query):
        query = query.lower()
        tags = self.get_all_tags()
        scored = [(tag, self._tag_score(tag.lower(), query)) for tag in tags]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0] if scored and scored[0][1] > 0 else None

    def _tag_score(self, tag, query):
        return sum(1 for word in tag.replace("Service", "").lower().split() if word in query)

    def search_by_tag(self, query):
        tag = self.match_tag_from_query(query)
        if not tag:
            return []

        keyword = query.lower()
        results = []
        for item in self.index:
            if tag not in item.get("tags", []):
                continue

            fields_to_search = [
                item.get("summary", "").lower(),
                item.get("operationId", "").lower()
            ]
            if any(keyword in field for field in fields_to_search):
                results.append(item)
        return results
