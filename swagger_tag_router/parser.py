import json
import openai
import os

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

def find_best_tag_openai(user_input, tags):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    tag_list = "\n".join(tags)
    prompt = f"""You are helping route a user query to the correct Argo CD API service.
Given the user input: "{user_input}"

Choose the most appropriate tag from this list:
{tag_list}

Just return the best matching tag. If none match, return "Unknown".
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an API routing assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[OpenAI fallback] Error calling API: {e}")
        return find_best_tag_local(user_input, tags)

def find_best_tag_local(user_input, tags):
    user_input = user_input.lower()
    best_match = None
    best_score = 0

    for tag in tags:
        tag_words = tag.replace("Service", "").lower().split()
        score = sum(1 for word in tag_words if word in user_input)
        if score > best_score:
            best_match = tag
            best_score = score

    return best_match if best_match else "Unknown"

if __name__ == "__main__":
    swagger_path = "swagger_tag_router/swagger.json"
    swagger = load_swagger(swagger_path)
    tags = extract_tags(swagger)

    print("Tags found:")
    for tag in tags:
        print("-", tag)

    user_input = input("\nEnter user intent (e.g., create application): ")
    best_tag = find_best_tag_openai(user_input, tags)
    print(f"\nMost appropriate tag: {best_tag}")
