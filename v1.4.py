import mysql.connector
import json
import os
import requests
from dotenv import load_dotenv
import logging
import random
import re

# Load the API key from the .env file
load_dotenv()  # Load environment variables from .env file
api_key = os.getenv("OPENAI_API_KEY")

# Database connection details
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def log_sql(query, params=None):
    if params:
        logger.info(f"Executing SQL: {query} | Params: {params}")
    else:
        logger.info(f"Executing SQL: {query}")


# Function to get product information, including materials
def get_product_info_with_ean(product_ean):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = f"""
    SELECT CA_CW_ID, CA_TYTUL, ca_filters_material1, ca_filters_material2, ca_filters_material3, ca_filters_wysokosc, ca_filters_dlugosc, ca_filters_szerokosc, ca_filters_glebokosc, ca_filters_srednica, ca_filters_pojemnosc, CA_PRODUCENT_ID
    FROM cms_art_produkty
    WHERE CA_EAN = '{product_ean}'
    """
    cursor.execute(query)
    product = cursor.fetchone()

    query = f"""
    SELECT CP_NAZWA
    FROM cms_producenci
    WHERE CP_ID = '{product[11]}'
    """
    cursor.execute(query)
    producent = cursor.fetchone()

    cursor.close()
    connection.close()

    if product:
        product_info = {
            "product_id": product[0],
            "product_name": product[1],
            "materials": {
                "material1": product[2] if product[2] else "brak informacji",
                "material2": product[3] if product[3] else "brak informacji",
                "material3": product[4] if product[4] else "brak informacji"
            },
            "sizes": {
                "wysokość": product[5] if product[5] else "brak informacji",
                "długość": product[6] if product[6] else "brak informacji",
                "szerokość": product[7] if product[7] else "brak informacji",
                "głębokość": product[8] if product[8] else "brak informacji",
                "średnica": product[9] if product[9] else "brak informacji",
                "pojemność": product[10] if product[10] else "brak informacji",
            },
            "producent": producent[0]
        }
        logger.info(f"Product Info: {product_info}")
        return product_info
    else:
        logger.warning(f"No product found for EAN: {product_ean}")
        return None


# Function to get all image URLs for a product
def get_product_images(product_id):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = f"""
    SELECT CZ_CZS_ID, CZ_SOURCE_SRC, CZ_KOLEJNOSC, CZ_TYP
    FROM (
        SELECT
            CZ_CZS_ID,
            CASE 
                WHEN CZ_SOURCE_SRC IS NOT NULL AND CZ_SOURCE_SRC != '' 
                THEN CONCAT('https://www.superwnetrze.pl/i/cms/originals/', CZ_SOURCE_SRC) 
                ELSE CZ_SRC 
            END AS CZ_SOURCE_SRC, 
            CZ_KOLEJNOSC, 
            CZ_TYP,
            ROW_NUMBER() OVER (
                PARTITION BY CZ_KOLEJNOSC
                ORDER BY 
                    CASE 
                        WHEN CZ_TYP = 'D' THEN 1  
                        WHEN CZ_TYP = 'S' THEN 2  
                        WHEN CZ_TYP = 'M' THEN 3  
                        ELSE 4
                    END
            ) AS rn
        FROM cms_zalaczniki
        WHERE CZ_CW_ID = {product_id} AND CZ_CZS_ID = 0 OR CZ_CZS_ID IS NULL
    ) AS OrderedImages
    WHERE rn = 1
    ORDER BY CZ_KOLEJNOSC ASC
    LIMIT 3
    """ 
    cursor.execute(query)

    images = []
    for idx, row in enumerate(cursor.fetchall()):
        url = row[1] if row[1] != 0 else None  # Handle 0 as None or invalid URL
        images.append({"img_id": idx + 1, "url": url})

    logger.info(f"Fetched images: {images}")
    cursor.close()
    connection.close()

    return images



# Function to send an image URL to GPT-4 API and get a description
def send_image_url_to_gpt(image_url):
    #return "Here is description"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    prompt = f"Opis zdjęcia produktu dla sklepu internetowego. Krótko opisz to co jest na zdjęciu.\nZdjęcie: {image_url}"

    payload = {
        "model": "gpt-4o-2024-08-06",  # Use GPT-4 or your fine-tuned model
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "max_tokens": 150  # Limit to 150 tokens for the description
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response_json = response.json()

    if 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        print(f"Error in API call: {response_json}")
        return "Description not available"


# Function to process images and add their descriptions
def process_images_with_descriptions(image_urls):
    descriptions = []
    for image in image_urls:
        try:
            description = send_image_url_to_gpt(image['url'])
            image['description'] = description  # Add description to the existing dictionary
        except Exception as e:
            print(f"Error processing {image['url']}: {e}")
            image['description'] = "Description not available"

    return image_urls  # Return the updated list with descriptions

# Function to send chat_data to GPT-4 API and get the assistant's completion
def send_chat_data_to_gpt(chat_data):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": "ft:gpt-4o-2024-08-06:personal::A8nS4dK3",  # Use GPT-4 or your fine-tuned model
        "messages": chat_data["messages"],
        "max_tokens": 1200,  # Adjust as needed
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    response_json = response.json()

    if 'choices' in response_json:
        return response_json['choices'][0]['message']['content']
    else:
        print(f"Error in API call: {response_json}")
        return "Error in API call"


# Function to replace img_id with URLs in the assistant's output
def replace_img_id_with_urls(text, image_id_to_url):
    for image in image_id_to_url:
        img_id = f"img_id:{image['img_id']}"
        if image['url']:
            url = str(image['url'])
        else:
            url = "Invalid URL"
            logger.warning(f"Invalid URL for img_id: {image['img_id']}")
        text = text.replace(img_id, url)
    return text



# Function to insert description parts into the database
def description_parts_to_insert(product_id, description_parts, image_id_to_url):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Delete existing descriptions for the product
    delete_query = "DELETE FROM cms_art_produkty_desc WHERE capd_cw_id = %s"
    log_sql(delete_query, product_id)
    cursor.execute(delete_query, (product_id,))
    connection.commit()

    for part in description_parts:
        order = part.get('capd_desc_order', 0)
        left = replace_img_id_with_urls(part.get('capd_desc_text', ''), image_id_to_url)
        right = replace_img_id_with_urls(part.get('capd_desc_text2', ''), image_id_to_url)

        # Prepare the SQL query for inserting into cms_art_produkty_desc
        query = """
        INSERT INTO cms_art_produkty_desc (capd_cw_id, capd_desc_order, capd_desc_text, capd_desc_text2)
        VALUES (%s, %s, %s, %s)
        """
        values = (product_id, order, left, right)

        log_sql(query, values)
        cursor.execute(query, values)

    # Commit the changes to the database
    connection.commit()

    logger.info(f"Inserted description parts for product {product_id}")
    cursor.close()
    connection.close()
    

def update_ca_tresc(product_id):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Fetch all description parts for the product
    query = """
    SELECT capd_desc_order, capd_desc_text, capd_desc_text2, capd_kind
    FROM cms_art_produkty_desc
    WHERE capd_cw_id = %s
    ORDER BY capd_desc_order ASC
    """
    log_sql(query, product_id)
    cursor.execute(query, (product_id,))
    description_parts = cursor.fetchall()

    # Initialize CA_TRESC as an empty string
    ca_tresc = ""

    # Iterate over each description part
    for part in description_parts:
        order, text, text2, kind = part

        # Skip invalid or empty sections
        if order == -1:
            continue

        # Process images and inject width and height attributes
        for field in ['text', 'text2']:
            field_content = text if field == 'text' else text2
            if '<img' in field_content:
                img_srcs = extract_image_sources(field_content)
                for img_src in img_srcs:
                    image_query = f"SELECT CZ_WIDTH, CZ_HEIGHT FROM cms_zalaczniki WHERE CZ_SRC = %s"
                    cursor.execute(image_query, (img_src,))
                    img = cursor.fetchone()
                    if img and img[0] > 0:
                        width, height = img
                        field_content = field_content.replace(
                            f'<img src="{img_src}"',
                            f'<img src="{img_src}" width="{width}" height="{height}"'
                        )
                
                if field == 'text':
                    text = field_content
                else:
                    text2 = field_content

        # Determine the class based on whether the fields contain an image
        if '<img' in text and '<img' in text2:
            layout_class = 's-img-img'
        elif '<img' in text:
            layout_class = 's-img-txt'
        elif '<img' in text2:
            layout_class = 's-txt-img'
        else:
            layout_class = 's-short'

        # Create the HTML with dynamic class assignment
        section_html = f"""
        <div class="ck-content wysiwyg-ck desc-row {layout_class}">
            <div class="side">{text}</div>
            <div class="side">{text2}</div>
        </div>
        """

        # Append the generated HTML to CA_TRESC
        ca_tresc += section_html

    # Update the CA_TRESC field in cms_art_produkty
    # !!!
    # If doing a test REMOVE ca_is_multitext = 1 to not fill database with not trusted description
    # !!!
    update_query = """
    UPDATE cms_art_produkty
    SET CA_TRESC = %s, ca_is_multitext = 1
    WHERE CA_CW_ID = %s
    """
    log_sql(update_query, (ca_tresc, product_id))
    cursor.execute(update_query, (ca_tresc, product_id))
    connection.commit()

    logger.info(f"CA_TRESC field updated for product {product_id}")
    cursor.close()
    connection.close()



def extract_image_sources(text):
    import re
    # Regular expression to find all <img src="...">
    return re.findall(r'<img\s+src="([^"]+)"', text)



# Function to create and send system message and user input for a specific product
def display_fine_tune_input_for_single_product(product_ean):
    product_info = get_product_info_with_ean(product_ean)

    if product_info:
        product_id = product_info["product_id"]
        producent = product_info["producent"]
        product_name = product_info["product_name"]
        materials = product_info["materials"]
        sizes = product_info["sizes"]

        # Get product images
        images = get_product_images(product_id)

        if not images:
            logger.warning(f"No images found for product ID {product_id}.")
            return

        # Process images and add descriptions
        images_with_descriptions = process_images_with_descriptions(images)

        # Log the images with descriptions
        logger.info(f"Images with descriptions: {images_with_descriptions}")

        # Create the system prompt
        system_prompt = """
Jesteś asystentem sklepu e-commerce. Twoim zadaniem jest tworzenie atrakcyjnych opisów produktów w strukturze:

- **capd_cw_id**: ID produktu
- **capd_desc_order**: kolejność części opisu
- **capd_desct_text**: lewa strona opisu (z HTML)
- **capd_desct_text2**: prawa strona opisu (z HTML)

**Instrukcje:**

1. Opracuj krótki opis produktu na podstawie podanych informacji. **Nie dodawaj niepewnych danych.**
2. Wybierz najlepsze zdjęcia dla fragmentów opisu, aby wspierały tekst. **Rozmiar max: 600x600.**
3. Zaplanuj, gdzie umieścić zdjęcia (lewo/prawo) dla najlepszej prezentacji.
4. Stwórz opis używając struktury:

{
  "description_parts": [
    {
      "capd_desc_order": 1,
      "capd_desc_text": "Treść dla lewej strony z HTML",
      "capd_desc_text2": "Treść dla prawej strony z HTML"
    }
    // Dodatkowe części według potrzeb
  ]
}

**WAŻNE:**

- **Pisz specyfikację tylko z dostępnych danych.**
- Używaj **wyłącznie** podanych identyfikatorów obrazów. **Nie dodawaj ani nie generuj nowych linków; wstawiaj tylko id zdjęcia w postaci img src=\"img_id:id\
, gdzie id to odpowiedni numer obrazu.**
- Zachowaj odpowiednią strukturę HTML. **Nie pozostawiaj pustych pól.**
- Zadbaj o estetykę, spójność i czytelność. Używaj symboli ✅, ⭐, ale bez przesady.
- Jeśli jest jedno zdjęcie, utwórz **maksymalnie 1 sekcję**. Przy więcej niż 1 zdjęciu - **maksymalnie 3 sekcje.**
- **Nie używaj tego samego zdjęcia więcej niż raz.**
"""



        # Prepare the user message with product information, materials, and images
        user_message = {
            "product_id": product_id,
            "product_name": product_name,
            "producent_name": producent,
            "materials": materials,
            "sizes": sizes,
            "images": [
                {
                    "img_id": image["img_id"],
                    "description": image["description"]
                } for image in images_with_descriptions
            ]
        }

        # Send data to GPT
        chat_data = {
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt.strip()
                },
                {
                    "role": "user",
                    "content": json.dumps(user_message, ensure_ascii=False)
                }
            ]
        }

        assistant_response = send_chat_data_to_gpt(chat_data)
        if assistant_response:
            logger.info(f"Assistant Response:\n{assistant_response}")

            try:
                # Ensure the assistant's response is valid JSON
                response_json = json.loads(assistant_response)
                description_parts = response_json.get('description_parts', [])

                if description_parts:
                    description_parts_to_insert(product_id, description_parts, images_with_descriptions)
                    update_ca_tresc(product_id)
                    logger.info(f"Product ID {product_id} updated in the database.")
                else:
                    logger.warning("No description parts found in the assistant's response.")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing assistant's response: {e}")
        else:
            logger.error("Assistant's response is empty or None.")
    else:
        logger.warning(f"No product found for Product EAN: {product_ean}")


# Main function to process and send one product to the GPT-4 API using EAN
def main():
    product_ean = '5903351255462'  # Example product EAN
    display_fine_tune_input_for_single_product(product_ean)

if __name__ == "__main__":
    main()
