import os
import json
from google import genai
from google.genai import types

def test_tool(x: int) -> int:
    """Multiplies x by 2."""
    return x * 2

def main():
    from dotenv import load_dotenv
    load_dotenv()
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"), vertexai=False)
    
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents="Call test_tool with 5",
        config=types.GenerateContentConfig(
            tools=[test_tool],
            temperature=0.1
        )
    )
    
    if response.function_calls:
        print("Function calls:", response.function_calls)
        for fc in response.function_calls:
            print("Name:", fc.name)
            print("Args:", fc.args)
    else:
        print("Text:", response.text)

if __name__ == "__main__":
    main()
