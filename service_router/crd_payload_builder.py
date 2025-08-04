import json

def build_payload_from_crd(crd_path):
    with open(crd_path) as f:
        crd = json.load(f)

    spec_schema = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
    payload = {}

    required = spec_schema.get("required", [])
    for key in required:
        if key in spec_schema["properties"]:
            if key in ["source", "sources"]:
                sub_required = spec_schema["properties"][key].get("required", [])
                payload[key] = {field: f"<{field}>" for field in sub_required}
            elif key == "destination":
                sub_required = spec_schema["properties"][key].get("required", [])
                payload[key] = {field: f"<{field}>" for field in sub_required}
            else:
                payload[key] = f"<{key}>"
        else:
            payload[key] = f"<{key}>"
    return payload