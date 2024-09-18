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


# Function to send an image URL to GPT-4 API and get a description
def send_image_url_to_gpt(image_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    prompt = f"Opis zdjęcia produktu dla sklepu internetowego. Opisz to co jest na zdjęciu.\nZdjęcie: {image_url}"

    payload = {
        "model": "gpt-4o-2024-08-06",  # Use GPT-4 or your fine-tuned model
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 110  # Limit to 70 tokens for the description
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response_json = response.json()

    if 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        print(f"Error in API call: {response_json}")
        return "Description not available"
     

# Function to process images and add their descriptions to the prompt
def process_images_with_descriptions(image_urls):
    descriptions = []
    for image_url in image_urls:
        try:
            print("Processing image: " + image_url)
            description = send_image_url_to_gpt(image_url)
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
        "model": "ft:gpt-4o-2024-08-06:personal::A810XLWW",  # Use GPT-4 or your fine-tuned model
        "messages": chat_data["messages"],
        "max_tokens": 1500,  # Adjust as needed
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response_json = response.json()

    if 'choices' in response_json:
        # Extract the assistant's message content
        return response_json['choices'][0]['message']['content']
    else:
        print(f"Error in API call: {response_json}")
        return "Error in API call"


# Function to insert description parts into the database
def description_parts_to_insert(product_id, description_parts):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Delete existing descriptions for the product
    delete_query = "DELETE FROM cms_art_produkty_desc WHERE capd_cw_id = %s"
    cursor.execute(delete_query, (product_id,))
    connection.commit()

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

        # Execute each insert query
        cursor.execute(query, values)

    # Commit the changes to the database
    connection.commit()

    # Close the cursor and connection
    cursor.close()
    connection.close()


# Function to build CA_TRESC field and update it in cms_art_produkty
def update_ca_tresc(product_id):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Fetch all description parts for the product
    query = """
    SELECT capd_desc_order, capd_desc_text, capd_desc_text2
    FROM cms_art_produkty_desc
    WHERE capd_cw_id = %s
    ORDER BY capd_desc_order ASC
    """
    cursor.execute(query, (product_id,))
    description_parts = cursor.fetchall()

    # Initialize CA_TRESC as an empty string
    ca_tresc = ""

    # Loop over each description part and generate HTML
    for part in description_parts:
        order, text, text2 = part

        # Generate HTML based on the content
        section_html = f"""
        <div class="ck-content wysiwyg-ck">
            {text}
            {text2}
        </div>
        """

        # Append the generated HTML to CA_TRESC
        ca_tresc += section_html

    # Update the CA_TRESC field in cms_art_produkty
    update_query = """
    UPDATE cms_art_produkty
    SET CA_TRESC = %s
    WHERE CA_CW_ID = %s
    """
    cursor.execute(update_query, (ca_tresc, product_id))
    connection.commit()

    cursor.close()
    connection.close()



# Utility function to extract all image sources from the text
def extract_image_sources(text):
    import re
    # Regular expression to find all <img src="...">
    return re.findall(r'<img\s+src="([^"]+)"', text)


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
        system_prompt = """
Jesteś asystentem sklepu e-commerce. Twoim zadaniem jest wygenerowanie atrakcyjnych opisów produktów, które zostaną zapisane w bazie danych w następującej strukturze:

- **capd_cw_id**: ID produktu
- **capd_desc_order**: kolejność części opisu
- **capd_desct_text**: lewa strona opisu (z odpowiednimi tagami HTML)
- **capd_desct_text2**: prawa strona opisu (z odpowiednimi tagami HTML)

**Instrukcje**:

- Na podstawie nazwy produktu oraz opisów zdjęć, napisz ładny i zachęcający opis.
- **Nie modyfikuj ani nie twórz nowych linków!!!!!**; używaj **tylko** tych dostarczonych.
- Linki nie zawierają w swojej kolejności żadnych wzorców, nie mają kolejności, po prostu na sztywno ustawione.
- **Zdjęcia używaj tylko podane w prompcie, nie twórz nowych, nie dodawaj żadnego tesktu do linków, bo będzie błąd i nie będzie widoczne na stronie!!**
- **Użyj podanych zdjęć**, wstawiając ich linki w odpowiednich miejscach.
- Zachowaj odpowiednią strukturę HTML w polach `capd_desct_text` i `capd_desct_text2`. Nie zostawiaj pustymi pola 
- Pamiętaj o estetyce i czytelności opisu. Opis nie musi być dłużej niż 5 części.

**WAŻNE**: Używaj **tylko** podanych linków do zdjęć. **Nie dodawaj nowych linków**.
""".strip()

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

        # Print the formatted user message
        print("=================================USER MESSAGE=================================")
        print(json.dumps(user_message, indent=4, ensure_ascii=False))

        chat_data = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": json.dumps(user_message, ensure_ascii=False)
                }
            ]
        }

        # Send the chat_data to GPT-4 API and get the assistant's completion
        assistant_response = send_chat_data_to_gpt(chat_data)
        print(f"Assistant Response:\n{assistant_response}")

        # Convert the response into SQL INSERT statements
        try:
            description_parts = json.loads(assistant_response).get('description_parts', [])
            if description_parts:
                description_parts_to_insert(product_id, description_parts)
                print(f"Descriptions inserted into database for product ID {product_id}.")

                # Update CA_TRESC field after inserting descriptions
                update_ca_tresc(product_id)
                print(f"CA_TRESC field updated for product ID {product_id}.")

            else:
                print("No description parts found in the assistant response.")
        except json.JSONDecodeError:
            print("Assistant response is not valid JSON.")

    else:
        print(f"No product found for Product EAN: {product_ean}")


# Main function to process and send one product to the GPT-4 API using EAN
def main():
    product_ean = '8719883573045'  # Example product EAN
    display_fine_tune_input_for_single_product(product_ean)

if __name__ == "__main__":
    main()
