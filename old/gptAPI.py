from openai import OpenAI
import os
from dotenv import load_dotenv

# ===== Final step - generating new description

# Load environment variables from .env file
load_dotenv()

# Initialize OpenAI client (it will default to picking the API key from env)
client = OpenAI()

# Create a chat completion using the new method
chat_completion = client.chat.completions.create(
    model="gpt-4o-2024-08-06",  # Example of the model you're using
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "https://www.superwnetrze.pl/i/cms/106938030600.jpg powiedź mi proszę co to jest na tym zdjęciu"}
    ]
)

# Print the completion's result
message = chat_completion.choices[0].message.content
print(message)
