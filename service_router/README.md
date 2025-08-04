# Service Tag Router

This script:
- Loads `swagger.json`
- Extracts all service tags
- Sends user input and tags to OpenAI to find the best matching service

## Usage

1. Place `swagger.json` in the `service_router` folder.
2. Set your OpenAI API key:
   export OPENAI_API_KEY=sk-...
3. Run:
   python router.py
