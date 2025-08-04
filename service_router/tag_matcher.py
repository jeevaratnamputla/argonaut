import openai
import json

client = openai.OpenAI()

def ask_openai(messages):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages
    )
    return response.choices[0].message.content.strip()

def find_best_tag(user_input, tags):
    try:
        messages = [
            {"role": "system", "content": "Choose the most relevant tag from the list based on the users input.Output should be just the tag, with no quotes single or double:  . No extra output from you."},
            {"role": "user", "content": f"Input: {user_input}\nOptions: {tags}"}
        ]
        response = client.chat.completions.create(model="gpt-4", messages=messages)
        content = response.choices[0].message.content.strip()
        print('[Raw LLM Response]', content)
        try:
            parsed = json.loads(content)
            return parsed.get('best_tag', parsed)
        except Exception as e:
            print('[OpenAI JSON Error]', e)
            return content.strip().strip('"')
        except Exception as e:
            print('[OpenAI JSON Error]', e)
            return {'prompts': []}
    except Exception as e:
        print("[OpenAI Error]", e)
        return "Unknown"