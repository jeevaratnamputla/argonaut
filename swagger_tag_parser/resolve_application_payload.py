import json

def load_json_file(path):
    with open(path) as f:
        return json.load(f)

def resolve_application_schema(swagger, crd):
    # Find the schema reference for the application body
    for path, methods in swagger.get("paths", {}).items():
        for method, details in methods.items():
            if details.get("summary", "").startswith("Create creates an application"):
                for param in details.get("parameters", []):
                    if param.get("in") == "body" and "$ref" in param.get("schema", {}):
                        ref_path = param["schema"]["$ref"]
                        break

    definition_key = ref_path.split("/")[-1]
    app_schema = swagger["definitions"].get(definition_key)
    if not app_schema:
        raise ValueError(f"Definition {definition_key} not found in swagger.json")

    # Now map that to CRD spec
    crd_spec = crd.get("spec", {}).get("versions", [])[0].get("schema", {}).get("openAPIV3Schema", {}).get("properties", {}).get("spec", {})
    return crd_spec

def create_minimal_payload_from_spec(spec, depth=0):
    if "type" not in spec:
        return {}

    if spec["type"] == "object":
        properties = spec.get("properties", {})
        return {key: create_minimal_payload_from_spec(value, depth + 1) for key, value in properties.items() if depth < 2}
    elif spec["type"] == "array":
        items = spec.get("items", {})
        return [create_minimal_payload_from_spec(items, depth + 1)]
    elif "default" in spec:
        return spec["default"]
    elif "example" in spec:
        return spec["example"]
    elif spec["type"] == "string":
        return "<string>"
    elif spec["type"] == "boolean":
        return False
    elif spec["type"] == "integer":
        return 0
    elif spec["type"] == "number":
        return 0.0
    else:
        return None

if __name__ == "__main__":
    swagger_path = "swagger.json"
    crd_path = "argocd-application-crd-compressed.json"

    swagger = load_json_file(swagger_path)
    crd = load_json_file(crd_path)

    spec_schema = resolve_application_schema(swagger, crd)
    example_payload = create_minimal_payload_from_spec(spec_schema)

    request_body = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": "example-app"},
        "spec": example_payload
    }

    print(json.dumps(request_body, indent=2))
