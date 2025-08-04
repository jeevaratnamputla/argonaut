import json

def get_tags(swagger_path):
    with open(swagger_path) as f:
        swagger = json.load(f)
    tags = set()
    for path_item in swagger.get("paths", {}).values():
        for method in path_item.values():
            for tag in method.get("tags", []):
                tags.add(tag)
    return sorted(tags)