
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
    timeout=15.0,
    max_retries=0,
)

models = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "meta-models/muse-spark-open",
    "minimaxai/minimax-m2.7",
    "openai/gpt-oss-safeguard-20b",
]

for model in models:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Reply only: OK"}
            ],
            max_tokens=300,
            temperature=0,
        )

        answer = response.choices[0].message.content
        if answer and answer.strip():
            print(f"PASS: {model}")
        else:
            print(f"EMPTY RESPONSE: {model}")

    except Exception as exc:
        print(f"FAILED: {model} - {type(exc).__name__}: {exc}")
