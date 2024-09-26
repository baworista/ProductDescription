import os
import requests
import json
from dotenv import load_dotenv

# ===== Middle step - from image to text

# Load the API key from the .env file
load_dotenv()  # Load environment variables from .env file
api_key = os.getenv("OPENAI_API_KEY")

# Function to send an image URL to GPT-4 Vision API
def send_image_url_to_gpt_vision(image_url):
    # Prepare headers and payload for the request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o-2024-08-06",  # Use the correct GPT-4 Vision model
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What’s in this image?"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            }
        ],
        "max_tokens": 70  # Limit to 70 tokens for the description
    }

    # Send the request to the OpenAI API
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    
    # Check for errors and extract response content
    response_json = response.json()
    
    # Print full response for debugging
    print(f"Response for {image_url}: {response_json}")
    
    if 'choices' in response_json:
        # Extract the message content and token usage
        message_content = response_json['choices'][0]['message']['content']
        prompt_tokens = response_json['usage']['prompt_tokens']
        completion_tokens = response_json['usage']['completion_tokens']
        total_tokens = response_json['usage']['total_tokens']
        
        print(f"Content: {message_content}")
        print(f"Prompt tokens: {prompt_tokens}, Completion tokens: {completion_tokens}, Total tokens: {total_tokens}")
        
        return message_content, prompt_tokens, completion_tokens, total_tokens
    else:
        raise ValueError(f"Unexpected response format: {response_json}")

# Function to process multiple URLs and store descriptions in a dictionary
def process_images_and_store_descriptions(image_urls):
    descriptions = {}

    for image_url in image_urls:
        try:
            # Send the image URL to GPT-4 Vision API and get the description and token usage
            description, prompt_tokens, completion_tokens, total_tokens = send_image_url_to_gpt_vision(image_url)
            descriptions[image_url] = {
                "description": description,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }
            print(f"Generated Description for {image_url}: {description}")
        except Exception as e:
            print(f"Error processing {image_url}: {e}")

    return descriptions

# Example usage with 3 URLs
def main():
    image_urls = [
        "https://www.superwnetrze.pl/i/cms/106938030600.jpg",  
        "https://www.superwnetrze.pl/i/cms/mepal_modula.jpg",
        "https://www.superwnetrze.pl/i/cms/pojemnik-na-wedliny-modula-550-3-106938030600-s-0.jpg"
    ]

    # Process the images and store the descriptions
    descriptions = process_images_and_store_descriptions(image_urls)

    # Print the descriptions in JSON format
    descriptions_json = json.dumps(descriptions, indent=4)
    print(f"\nFinal JSON:\n{descriptions_json}")

if __name__ == "__main__":
    main()
