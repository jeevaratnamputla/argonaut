import os

SYSTEM_TEXT_PATH = os.getenv("SYSTEM_TEXT_PATH", "/app/system_text.txt")

def create_system_text():
    try:
        with open(SYSTEM_TEXT_PATH, "r", encoding="utf-8") as f:
            system_text = f.read()
        #print(system_text)
        return system_text
    except Exception as e:
        print(f"Failed to read system text from {SYSTEM_TEXT_PATH}: {e}")
        return ""

def main():
    create_system_text()

if __name__ == "__main__":
    main()