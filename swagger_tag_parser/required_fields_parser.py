import json

def load_json_file(path):
    with open(path) as f:
        return json.load(f)

def extract_top_level_required_fields(crd):
    spec = crd.get("spec", {}).get("versions", [])[0].get("schema", {}).get("openAPIV3Schema", {})
    spec_properties = spec.get("properties", {}).get("spec", {})
    required_keys = spec.get("properties", {}).get("spec", {}).get("required", [])
    return required_keys

if __name__ == "__main__":
    crd = load_json_file("service_router/argocd-application-crd-compressed.json")
    required_fields = extract_top_level_required_fields(crd)
    print("Top-level required fields under .spec:")
    for field in required_fields:
        print("-", field)
