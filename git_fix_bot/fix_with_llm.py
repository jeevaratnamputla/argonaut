from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
import os

llm = ChatOpenAI(model="gpt-4o", temperature=0)

def fix_files_with_llm(repo_dir: str, instruction: str, subdir=None) -> str:
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "You are an expert developer. Given a file and an instruction, update the file content."),
        ("human", "File: {filepath}\n\n{content}\n\nInstruction: {instruction}")
    ])
    chain = prompt_template | llm | StrOutputParser()

    search_dir = os.path.join(repo_dir, subdir) if subdir else repo_dir
    for root, _, files in os.walk(search_dir):
        for file in files:
            if file.endswith((".py", ".md")):
                full_path = os.path.join(root, file)
                with open(full_path) as f:
                    old_content = f.read()
                new_content = chain.invoke({
                    "filepath": file,
                    "content": old_content,
                    "instruction": instruction
                })
                if new_content.strip() != old_content.strip():
                    with open(full_path, "w") as f:
                        f.write(new_content)
                    return full_path
    raise Exception("No file changed.")