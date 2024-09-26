import mysql.connector
import json
import os
import requests
from dotenv import load_dotenv
import random
import re

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

# Dictionary to store image URLs by img_id for later reference
image_url_dict = {}


# Function to extract product IDs from the existing fine-tuning dataset
def extract_product_ids_from_file(file_path):
    existing_product_ids = set()
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                try:
                    data = json.loads(line.strip())
                    for message in data.get("messages", []):
                        if message["role"] == "user":
                            user_data = json.loads(message["content"])
                            product_id = user_data.get("product_id")
                            if product_id:
                                existing_product_ids.add(int(product_id))
                except json.JSONDecodeError:
                    print("Error decoding JSON line")
    return existing_product_ids


# Function to get product information, including materials and additional info
def get_product_info_with_materials_and_producer(limit=1):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    # Query to fetch product information, materials, sizes, and producer
    query = """
    SELECT CA_CW_ID, CA_TYTUL, ca_filters_material1, ca_filters_material2, ca_filters_material3,
           ca_filters_wysokosc, ca_filters_dlugosc, ca_filters_szerokosc, ca_filters_glebokosc,
           ca_filters_srednica, ca_filters_pojemnosc, CA_PRODUCENT_ID
    FROM cms_art_produkty
    WHERE ca_is_multitext = 1 AND CA_AKTYWNY = 'T'
    """
    cursor.execute(query)
    products = cursor.fetchall()

    # Shuffle the products to introduce randomness
    random.shuffle(products)

    # Extract existing product IDs from the fine-tuning file
    existing_product_ids = extract_product_ids_from_file("fine_tune_chat_dataset.jsonl")

    product_info_list = []
    for product in products:
        # Skip the product if it's already in the fine-tuning dataset
        if product[0] in existing_product_ids:
            continue

        # Query to fetch the producer name based on CA_PRODUCENT_ID
        cursor.execute(f"SELECT CP_NAZWA FROM cms_producenci WHERE CP_ID = '{product[11]}'")
        producer = cursor.fetchone()
        
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
            "producent": producer[0] if producer else "brak informacji"
        }
        
        product_info_list.append(product_info)

        # Stop adding products once we've reached the specified limit
        if len(product_info_list) >= limit:
            break

    cursor.close()
    connection.close()

    return product_info_list



# Function to get all image URLs and generate unique img_id for each
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

    cursor.close()
    connection.close()

    return images


# Function to send an image URL to GPT-4 Vision API and get a description
def send_image_url_to_gpt_vision(image_url):
    return "Generated_description"
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
        return "Description not available"


# Function to process images and add their descriptions to the existing images dictionary
def process_images_with_descriptions(images):
    for image in images:
        image_id, image_url = image['img_id'], image['url']
        print("Image id is: " + str(image_id) + "\nImage url is: " + str(image_url))
        try:
            description = send_image_url_to_gpt_vision(image_url)  # Get description from GPT-4 Vision
            image['description'] = description  # Add description to the existing image dictionary
        except Exception as e:
            print(f"Error processing {image_url}: {e}")
            image['description'] = "Description not available"  # Default if there's an error

    return images  # Return the updated images list with descriptions

# Function to get product descriptions (left and right sides)
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
            "capd_desc_order": order,
            "capd_desc_text": desc_text,
            "capd_desc_text2": desc_text2
        })

    cursor.close()
    connection.close()

    return description_parts


# Function to replace all URLs in description parts with their corresponding img_id or a random img_id
def replace_urls_with_img_ids(descriptions, image_descriptions):
    # Create a mapping from URLs to img_ids
    url_to_img_id = {image['url']: image['img_id'] for image in image_descriptions}

    # Define a regex to match URLs
    url_regex = r'https?://[^\s\'"<>]+'

    # List of all img_ids to use if we need random replacements
    img_ids = [image['img_id'] for image in image_descriptions]
    used_img_ids = set()  # To keep track of used img_ids

    for part in descriptions:
        # Replace known URLs in 'capd_desc_text'
        capd_desc_text = part.get("capd_desc_text", "")
        urls_in_text = re.findall(url_regex, capd_desc_text)

        for url in urls_in_text:
            img_id = url_to_img_id.get(url)  # Get img_id for the found URL
            if img_id:
                img_id_placeholder = f"img_id:{img_id}"
                # Replace the known URL with img_id placeholder
                capd_desc_text = capd_desc_text.replace(url, img_id_placeholder)
            else:
                # Find an unused img_id or loop back if all are used
                available_img_ids = [img_id for img_id in img_ids if img_id not in used_img_ids]
                if available_img_ids:
                    random_img_id = random.choice(available_img_ids)
                    used_img_ids.add(random_img_id)  # Mark this img_id as used
                else:
                    # If all img_ids are used, reset the set and allow reuse
                    used_img_ids.clear()
                    random_img_id = random.choice(img_ids)
                    used_img_ids.add(random_img_id)  # Mark this img_id as used

                random_img_id_placeholder = f"img_id:{random_img_id}"
                print(f"Replacing unknown {url} with {random_img_id_placeholder}")
                capd_desc_text = capd_desc_text.replace(url, random_img_id_placeholder)
        part["capd_desc_text"] = capd_desc_text

        # Replace known URLs in 'capd_desc_text2'
        capd_desc_text2 = part.get("capd_desc_text2", "")
        urls_in_text2 = re.findall(url_regex, capd_desc_text2)

        for url in urls_in_text2:
            img_id = url_to_img_id.get(url)  # Get img_id for the found URL
            if img_id:
                img_id_placeholder = f"img_id:{img_id}"
                # Replace the known URL with img_id placeholder
                capd_desc_text2 = capd_desc_text2.replace(url, img_id_placeholder)
            else:
                # Find an unused img_id or loop back if all are used
                available_img_ids = [img_id for img_id in img_ids if img_id not in used_img_ids]
                if available_img_ids:
                    random_img_id = random.choice(available_img_ids)
                    used_img_ids.add(random_img_id)  # Mark this img_id as used
                else:
                    # If all img_ids are used, reset the set and allow reuse
                    used_img_ids.clear()
                    random_img_id = random.choice(img_ids)
                    used_img_ids.add(random_img_id)  # Mark this img_id as used

                random_img_id_placeholder = f"img_id:{random_img_id}"
                print(f"Replacing unknown {url} with {random_img_id_placeholder}")
                capd_desc_text2 = capd_desc_text2.replace(url, random_img_id_placeholder)
        part["capd_desc_text2"] = capd_desc_text2

    return descriptions


# Function to create the JSONL dataset with materials and producer information
def create_fine_tune_dataset(output_file="fine_tune_chat_dataset.jsonl"):
    products = get_product_info_with_materials_and_producer()

    with open(output_file, "a", encoding="utf-8") as file:
        for product in products:
            product_id = product["product_id"]
            product_name = product["product_name"]
            materials = product["materials"]
            sizes = product["sizes"]
            producer = product["producent"]

            # Get product images (with URLs)
            images = get_product_images(product_id)

            # Process images and add descriptions directly to the images dictionary
            images_with_descriptions = process_images_with_descriptions(images)

            # Get product descriptions (left and right sides) from the database
            descriptions = get_product_descriptions(product_id)

            # Check if there are description parts, if not, skip this product
            if not descriptions:
                print(f"No descriptions found for product ID {product_id}")
                continue

            # Replace URLs with img_id in description parts
            descriptions_with_img_ids = replace_urls_with_img_ids(descriptions, images_with_descriptions)

            # Create the system prompt with the updated structure
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

            # Prepare the user message with product information
            user_message = {
                "product_id": product_id,
                "product_name": product_name,
                "producent_name": producer,
                "materials": materials,
                "sizes": sizes,
                "images": [
                    {
                        "img_id": image["img_id"],
                        "description": image["description"]
                    } for image in images_with_descriptions
                ]
            }

            # Construct the chat data including the system prompt, user input, and assistant response
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
                        "content": json.dumps({"description_parts": descriptions_with_img_ids}, ensure_ascii=False)
                    }
                ]
            }

            file.write(json.dumps(chat_data, ensure_ascii=False) + "\n")



# Main function to process all products and create the dataset
def main():
    create_fine_tune_dataset()


if __name__ == "__main__":
    main()
