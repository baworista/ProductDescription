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

    random.shuffle(products)

    existing_product_ids = extract_product_ids_from_file("fine_tune_chat_dataset.jsonl")
    new_products = [(product_id, product_name) for product_id, product_name in products if product_id not in existing_product_ids]

    return new_products[:1]


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
        WHERE CZ_CW_ID = {product_id}
    ) AS OrderedImages
    WHERE rn = 1
    ORDER BY CZ_KOLEJNOSC ASC;
    """

    cursor.execute(query)
    images = []
    for idx, row in enumerate(cursor.fetchall()):
        img_id = idx + 1
        url = row[1]
        images.append({"img_id": img_id, "url": url})

    cursor.close()
    connection.close()

    return images

# Function to send an image URL to GPT-4 Vision API and get a description
def send_image_url_to_gpt_vision(image_url):
    return "Generated_description"
    # headers = {
    #     "Content-Type": "application/json",
    #     "Authorization": f"Bearer {api_key}"
    # }

    # payload = {
    #     "model": "gpt-4o-2024-08-06",
    #     "messages": [
    #         {
    #             "role": "user",
    #             "content": f"To jest zdjęcie produktu z internet-sklepu. Opisz to co jest na zdjęciu. Uważaj, bo masz 150 tokenów na odpowiedź.\nZdjęcie: {image_url}"
    #         }
    #     ],
    #     "max_tokens": 150
    # }

    # response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    # response_json = response.json()

    # if 'choices' in response_json:
    #     return response_json['choices'][0]['message']['content']
    # else:
    #     return "Description not available"


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

import random


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


# Function to create the JSONL dataset
def create_fine_tune_dataset(output_file="fine_tune_chat_dataset.jsonl"):
    products = get_product_ids_and_names()

    with open(output_file, "a", encoding="utf-8") as file:
        for product_id, product_name in products:
            # Get product images (with URLs)
            images = get_product_images(product_id)

            # Process images and add descriptions directly to the images dictionary
            images_with_descriptions = process_images_with_descriptions(images)

            # Get product descriptions (left and right sides)
            descriptions = get_product_descriptions(product_id)

            # Replace URLs with img_id in description parts
            descriptions_with_img_ids = replace_urls_with_img_ids(descriptions, images_with_descriptions)

            # Create the system prompt with the updated structure
            system_prompt = """
Jesteś asystentem sklepu e-commerce. Twoim zadaniem jest wygenerowanie atrakcyjnych opisów produktów, które zostaną zapisane w bazie danych w następującej strukturze:

- capd_cw_id: ID produktu
- capd_desc_order: kolejność części opisu
- capd_desct_text: lewa strona opisu (z odpowiednimi tagami HTML)
- capd_desct_text2: prawa strona opisu (z odpowiednimi tagami HTML)

***

Instrukcje:
- Masz podane id produktu, nazwę produktu, id zdjęć oraz ich opis. Na podstawie nazwy produktu oraz opisów zdjęć, wygeneruj opis produktu krok po kroku:
  
  1. ***Najpierw*** pomyśl nad najlepszym sposobem opisania produktu. Rozważ kluczowe cechy, które mogą zainteresować klientów, np. funkcjonalność, jakość, estetyka.
  2. ***Zastanów się***, jakie zdjęcia najlepiej pasują do opisu każdego fragmentu tekstu i jak mogą wizualnie wspierać opis. Wybierz odpowiednie id zdjęć na podstawie ich opisu i funkcji.
  3. ***Zaplanuj***, gdzie umieścić zdjęcia, aby harmonijnie wspierały tekst i wprowadzały wizualny kontekst.
  4. ***Dla każdej części opisu***, zapisz swoje myśli i logiczny ciąg myślenia, gdzie dane zdjęcie powinno się znaleźć i dlaczego.
  5. Dopiero po tym przemyśleniu, przystąp do ostatecznego sformułowania treści i umiejscowienia zdjęć w odpowiednich miejscach.

***

- Używaj id zdjęć w miejscach, gdzie musi być wstawione odpowiednie zdjęcie. ***Nie modyfikuj ani nie twórz nowych linków, tylko wstawiaj id zdjęcia.***
- Zachowaj odpowiednią strukturę HTML w polach `capd_desct_text` i `capd_desct_text2`. ***Nie zostawiaj pustych pól.***
- Unikaj umieszczania pierwszego zdjęcia z id 1 tam, gdzie capd_desc_order to 1. Na inne zdjęcia nie ma ograniczeń.
- Opis nie musi być dłuższy niż 5 części i, w przypadku więcej niż jednego zdjęcia, nie mniej niż 2 części.
- Pamiętaj o estetyce, logicznym ciągu opisu i czytelności tekstu. Zapewnij, że opis jest uporządkowany i przyjemny dla oka.
- Upewnij się, że zdjęcia są umieszczone w odpowiednich miejscach, w sposób przemyślany i z sensem.

***

WAŻNE: Używaj ***tylko*** podanych identyfikatorów obrazów. ***Nie dodawaj oraz nie generuj nowych identyfikatorów. Zastępuj linki zdjęć identyfikatorem img_id:id, gdzie id to odpowiedni identyfikator obrazu.***

"""

            # Prepare the user message with img_id and descriptions
            user_message = {
                "product_id": product_id,
                "product_name": product_name,
                "images": [
                    {
                        "img_id": image["img_id"],
                        "description": image["description"]
                    } for image in images_with_descriptions  # Keep only img_id and description fields
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
