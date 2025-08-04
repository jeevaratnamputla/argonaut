import openai

client = openai.OpenAI()

def ask_openai(messages):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages
    )
    return response.choices[0].message.content.strip()
import json

def ask_llm_to_fill(user_input, request_obj):
    try:
        messages = [
            {"role": "system", "content": "The user is trying to interact with an API. Identify missing fields that need user input. Respond with a JSON object of prompts."},
            {"role": "user", "content": f"Request: {json.dumps(request_obj, indent=2)}\nInput: {user_input}"}
        ]
        response = client.chat.completions.create(model="gpt-4", messages=messages)
        content = response.choices[0].message.content.strip()
        print('[Raw LLM Response]', content)
        try:
            parsed = json.loads(content)
            return parsed.get('prompts', parsed)
        except Exception as e:
            print('[OpenAI JSON Error]', e)
            if isinstance(content, str): return {'prompts': [content]}
            return {'prompts': []}
        except Exception as e:
            print('[OpenAI JSON Error]', e)
            return {'prompts': []}
    except Exception as e:
        print("[OpenAI Error]", e)
        return {"prompts": []}