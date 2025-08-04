import openai
import json

client = openai.OpenAI()

def ask_openai(messages):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages
    )
    return response.choices[0].message.content.strip()

def find_best_summary(user_input, summary_string):
    print ("in find_best_summary")
    print (user_input)
    #print (summary_string)
    system_text = "Choose just one of the following list of comma seperated list of summaries of apis the summary among the following Summaries: " + "\n" +summary_string + "\n" + " that best matches the user's intent. Respond with the exact summary, no quotes or double quotes"
    #print (system_text)
    try:
        messages = [
            {"role": "system", "content": system_text},
            {"role": "user", "content":user_input}
        ]
        #print(json.dumps(messages, indent=2))
        response = client.chat.completions.create(model="gpt-4", messages=messages)
        content = response.choices[0].message.content.strip()

        print('[Raw LLM Response]', content)
        try:
            parsed = json.loads(content)
            return parsed.get('best_summary', parsed)
        except Exception as e:
            print('[OpenAI JSON Error]', e)
            return content.strip().strip('"')
        except Exception as e:
            print('[OpenAI JSON Error]', e)
            return {'prompts': []}
    except Exception as e:
        print("[OpenAI Error]", e)
        return ""