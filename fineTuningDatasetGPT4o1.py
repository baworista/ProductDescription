import mysql.connector
import json
import os
import requests
from dotenv import load_dotenv
import random

# Load the API key from the .env file
load_dotenv()  # Load environment variables from .env file
api_key = os.getenv("OPENAI_API_KEY")

# Database connection details loaded from environment variables
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# Function to extract product IDs from the existing fine-tuning dataset
def extract_product_ids_from_file(file_path):
    existing_product_ids = set()
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                try:
                    data = json.loads(line.strip())
                    # Check if there's a message from the user and extract Product ID from its content
                    for message in data.get("messages", []):
                        if message["role"] == "user":
                            # Extract product ID from the user message content
                            content = message["content"]
                            try:
                                user_data = json.loads(content)
                                product_id = user_data.get("product_id")
                                if product_id:
                                    existing_product_ids.add(int(product_id))
                            except json.JSONDecodeError:
                                print("Error decoding user content JSON")
                except json.JSONDecodeError:
                    print("Error decoding JSON line")
    return existing_product_ids

# Function to get all active products with description IDs, shuffle them, and return the first 9
def get_product_ids_and_names():
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = """
    SELECT CA_CW_ID, CA_TYTUL
    FROM cms_art_produkty
    WHERE ca_is_multitext = 1 AND CA_AKTYWNY = 'T'
    """

    cursor.execute(query)
    products = cursor.fetchall()

    cursor.close()
    connection.close()

    # Randomize the order of products
    random.shuffle(products)

    # Check the existing product IDs in the fine-tuning file
    existing_product_ids = extract_product_ids_from_file("fine_tune_chat_dataset.jsonl")

    # Filter out products that are already in the file
    new_products = [(product_id, product_name) for product_id, product_name in products if product_id not in existing_product_ids]

    # Return the first 9 new products after filtering
    return new_products[:1]

# Function to get all image URLs for a product
def get_product_images(product_id):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = f"""
    SELECT CZ_SOURCE_SRC, CZ_KOLEJNOSC, CZ_TYP, CZ_CZS_ID
    FROM (
        SELECT
            CASE 
                WHEN CZ_SOURCE_SRC IS NOT NULL AND CZ_SOURCE_SRC != '' 
                THEN CONCAT('https://www.superwnetrze.pl/i/cms/originals/', CZ_SOURCE_SRC) 
                ELSE CZ_SRC 
            END AS CZ_SOURCE_SRC, 
            CZ_KOLEJNOSC, 
            CZ_TYP, 
            CZ_CZS_ID,
            ROW_NUMBER() OVER (
                PARTITION BY CZ_KOLEJNOSC
                ORDER BY 
                    CASE 
                        WHEN CZ_TYP = 'D' THEN 1  -- Prioritize large images first
                        WHEN CZ_TYP = 'S' THEN 2  -- Then medium-sized images
                        WHEN CZ_TYP = 'M' THEN 3  -- Small images come last
                        ELSE 4
                    END
            ) AS rn
        FROM cms_zalaczniki
        WHERE CZ_CW_ID = {product_id}
    ) AS OrderedImages
    WHERE rn = 1  -- Only keep the first row (largest image) per CZ_KOLEJNOSC group
    ORDER BY CZ_KOLEJNOSC ASC;
    """

    cursor.execute(query)
    images = [row[0] for row in cursor.fetchall()]  # Only return image URLs

    cursor.close()
    connection.close()

    return images

# Function to get the product descriptions (left and right sides)
def get_product_descriptions(product_id):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = f"""
    SELECT capd_desc_order, capd_desc_text, capd_desc_text2
    FROM cms_art_produkty_desc 
    WHERE capd_cw_id = {product_id}
    ORDER BY capd_desc_order ASC
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    description_parts = []
    for row in rows:
        order, desc_text, desc_text2 = row
        description_parts.append({
            "order": order,
            "left": desc_text,
            "right": desc_text2
        })

    cursor.close()
    connection.close()

    return description_parts

# Function to send an image URL to GPT-4 Vision API and get a description
def send_image_url_to_gpt_vision(image_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o-2024-08-06",  # Adjusted to 'gpt-4' as GPT-4 Vision may not be available
        "messages": [
            {
                "role": "user",
                "content": f"To jest zdjęcie produktu z internet-sklepu. Opisz to co jest na zdjęciu.\nZdjęcie: {image_url}"
            }
        ],
        "max_tokens": 70  # Limit to 70 tokens for the description
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response_json = response.json()

    if 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        return "Description not available"

# Function to process images and add their descriptions to the prompt
def process_images_with_descriptions(image_urls):
    descriptions = []
    for image_url in image_urls:
        try:
            description = send_image_url_to_gpt_vision(image_url)
            descriptions.append((image_url, description))
        except Exception as e:
            print(f"Error processing {image_url}: {e}")
            descriptions.append((image_url, "Description not available"))
        
    return descriptions

# Function to create the JSONL dataset
def create_fine_tune_dataset(output_file="fine_tune_chat_dataset.jsonl"):
    products = get_product_ids_and_names()

    with open(output_file, "a", encoding="utf-8") as file:
        for product_id, product_name in products:
            # Get product images
            images = get_product_images(product_id)

            # Get image descriptions
            image_descriptions = process_images_with_descriptions(images)

            # Get product descriptions
            descriptions = get_product_descriptions(product_id)

            # Create the chat format structure
            # Update the system prompt as per the new prompt
            system_prompt = """
Jesteś asystentem sklepu e-commerce. Twoim zadaniem jest wygenerowanie atrakcyjnych opisów produktów, które zostaną zapisane w bazie danych w następującej strukturze:

- **capd_cw_id**: ID produktu
- **capd_desc_order**: kolejność części opisu
- **capd_desct_text**: lewa strona opisu (z odpowiednimi tagami HTML)
- **capd_desct_text2**: prawa strona opisu (z odpowiednimi tagami HTML)

**Instrukcje**:

- Na podstawie nazwy produktu oraz opisów zdjęć, napisz ładny i zachęcający opis.
- **Użyj podanych zdjęć**, wstawiając ich linki w odpowiednich miejscach.
- **Nie modyfikuj ani nie twórz nowych linków**; używaj tylko tych dostarczonych.
- Zachowaj odpowiednią strukturę HTML w polach `capd_desct_text` i `capd_desct_text2`.
- Pamiętaj o estetyce i czytelności opisu.
- Jeżeli nie jesteś pewny czegoś(np. materiału lub rozmiarów), lepiej o tym nie pisać.

**WAŻNE**: Używaj **tylko** podanych linków do zdjęć. **Nie dodawaj nowych linków**.
"""

            # Create the user message in JSON format
            user_message = {
                "product_id": product_id,
                "product_name": product_name,
                "images": [
                    {
                        "url": image_url,
                        "description": description
                    } for image_url, description in image_descriptions
                ]
            }

            chat_data = {
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt.strip()
                    },
                    {
                        "role": "user",
                        "content": json.dumps(user_message, ensure_ascii=False)
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps({"description_parts": descriptions}, ensure_ascii=False)
                    }
                ]
            }

            # Write the prompt and completion in JSONL format
            file.write(json.dumps(chat_data, ensure_ascii=False) + "\n")

# Main function to process all products and create the dataset
def main():
    create_fine_tune_dataset()

if __name__ == "__main__":
    main()
