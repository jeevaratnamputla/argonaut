from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

# Initialize the LLM
llm = ChatOpenAI(model="gpt-4", temperature=0)

# Updated prompt template that accepts instruction
prompt = PromptTemplate.from_template(
    "You are an assistant. Your task is:\n"
    "{instruction}\n\n"
    "Here is the input text:\n\n"
    "{text}\n\n"
    "Respond accordingly:"
)

# Chain together using pipe operator
chain = prompt | llm | StrOutputParser()

def summarize_text(input_text: str, instruction: str) -> str:
    """
    Summarize or analyze the given input text using the LLM chain and an instruction.

    Args:
        input_text (str): The text to process.
        instruction (str): The instruction guiding what the LLM should do.

    Returns:
        str: The result from the LLM.
    """
    return chain.invoke({"text": input_text, "instruction": instruction})

# Example usage
if __name__ == "__main__":
    text = """
    Argo CD is a declarative, GitOps continuous delivery tool for Kubernetes. 
    It continuously monitors running applications and compares their live state to the desired state defined in Git repositories. 
    Users can automatically or manually sync the application state to match the desired state and view diffs through a web UI or CLI.
    """
    instruction = "List the commands a user might run based on this information."

    result = summarize_text(text, instruction)
    print("Result:\n", result)