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

# Function to get a single product by its EAN
def get_product_by_ean(product_ean):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = f"""
    SELECT CA_CW_ID, CA_TYTUL
    FROM cms_art_produkty
    WHERE CA_EAN = '{product_ean}'
    """

    cursor.execute(query)
    product = cursor.fetchone()

    cursor.close()
    connection.close()

    # Return the product details as a tuple (product_id, product_name), or None if not found
    return product if product else None


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


# Function to send an image URL to GPT-4 Vision API and get a description
def send_image_url_to_gpt_vision(image_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "gpt-4o-2024-08-06",  # Use GPT-4 or your fine-tuned model
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "To jest zdjęcie produktu z internet-sklepu. Opisz to co jest na zdjęciu."
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
            print("Sending image: " + image_url)
            description = send_image_url_to_gpt_vision(image_url)
            descriptions.append((image_url, description))
        except Exception as e:
            print(f"Error processing {image_url}: {e}")
            descriptions.append((image_url, "Description not available"))
    
    return descriptions


# Function to send chat_data to GPT-4 API and get the assistant's completion
def send_chat_data_to_gpt(chat_data):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "ft:gpt-4o-2024-08-06:personal::A6ylSDm3",  # Use GPT-4 or your fine-tuned model
        "messages": chat_data["messages"],
        "max_tokens": 2000,  # Adjust as needed
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response_json = response.json()

    if 'choices' in response_json:
        # Extract the assistant's message content
        return response_json['choices'][0]['message']['content']
    else:
        return "Error in API call"


# Function to insert description parts into the database
def description_parts_to_insert(product_id, description_parts):
    insert_queries = []
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    for part in description_parts:
        order = part.get('order', 0)
        left = part.get('left', '')
        right = part.get('right', '')

        # Prepare the SQL query for inserting into cms_art_produkty_desc
        query = """
        INSERT INTO cms_art_produkty_desc (capd_cw_id, capd_desc_order, capd_desc_text, capd_desc_text2)
        VALUES (%s, %s, %s, %s)
        """
        values = (product_id, order, left, right)
        insert_queries.append((query, values))

        # Execute each insert query
        cursor.execute(query, values)

    # Commit the changes to the database
    connection.commit()

    # Close the cursor and connection
    cursor.close()
    connection.close()

    return insert_queries


# Function to create and send system message and user input for a specific product
def display_fine_tune_input_for_single_product(product_ean):
    product = get_product_by_ean(product_ean)
    
    if product:
        product_id, product_name = product

        # Get product images
        images = get_product_images(product_id)

        # Get image descriptions
        image_descriptions = process_images_with_descriptions(images)

        # Create the chat format structure (without the assistant message)
        chat_data = {
            "messages": [
                {
                    "role": "system",
                    "content": "Jesteś asystentem sklepu e-commerce. W bazie danych przechowywane są produkty, z których niektóre mają opisy, a inne ich nie posiadają. Twoim celem jest wygenerowanie odpowiednich opisów dla tych produktów. Opisy są przychowywane w bazie danych w takiej strukturze: capd_cw_id (id produktu), capd_desc_order (kolejność części opisu) oraz capd_desct_text i capd_desct_text2, które reprezentują odpowiednio lewą i prawą stronę opisu. Opis w tych polach jest z odpowiednimi tegami html, o to też trzeba uważać. Masz podane nazwę produktu, linki do zdjęć(lub zdjęcia), które ma ten produkt oraz ich opis. Mając nazwe i opis zdjęć napisz ładny opis, i wykorzystaj zdjęcia, wstawiając linki. ''' Use only the exact image URLs provided in prompt, without modification or generating new links ''' "
                },
                {
                    "role": "user",
                    "content": f"Product ID: {product_id}, Product: {product_name}. " + " ".join([f"Image_{idx + 1}_URL: {image_url}. Image_{idx + 1}_Description: {description}." for idx, (image_url, description) in enumerate(image_descriptions)])
                }
            ]
        }

        # Send the chat_data to GPT-4 API and get the assistant's completion
        assistant_response = send_chat_data_to_gpt(chat_data)
        print(f"Assistant Response:\n{assistant_response}")

        # Convert the response into SQL INSERT statements
        description_parts = json.loads(assistant_response).get('description_parts', [])
        if description_parts:
            sql_inserts = description_parts_to_insert(product_id, description_parts)
            print(f"SQL Inserts executed: {len(sql_inserts)}")
        else:
            print("No description parts found in the assistant response.")

    else:
        print(f"No product found for Product EAN: {product_ean}")



# Main function to process and send one product to the GPT-4 API using EAN
def main():
    product_ean = 8719883573045  # Example product EAN
    display_fine_tune_input_for_single_product(product_ean)

if __name__ == "__main__":
    main()
