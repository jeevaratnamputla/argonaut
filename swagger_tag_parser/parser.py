import json

def load_swagger(path):
    with open(path) as f:
        swagger = json.load(f)
    return swagger

def extract_tags(swagger):
    tags = set()
    for path_item in swagger.get("paths", {}).values():
        for method in path_item.values():
            for tag in method.get("tags", []):
                tags.add(tag)
    return sorted(tags)

if __name__ == "__main__":
    swagger_path = "swagger.json"
    swagger = load_swagger(swagger_path)
    tags = extract_tags(swagger)
    print("Tags found in Swagger:")
    for tag in tags:
        print("-", tag)
