import mysql.connector
import json
from dotenv import load_dotenv
import os


load_dotenv()  # Load environment variables from .env file
# Database connection details loaded from environment variables
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# Function to get all active products with description IDs
def get_product_ids_and_names():
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = """
    SELECT CA_CW_ID, CA_TYTUL
    FROM cms_art_produkty
    WHERE ca_is_multitext = 1 AND CA_AKTYWNY = 'T'
    LIMIT 1
    """

    cursor.execute(query)
    products = cursor.fetchall()

    cursor.close()
    connection.close()

    return products  # Returns list of tuples (product_id, product_name)

# Function to get all image URLs for a product
def get_product_images(product_id):
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()

    query = f"""
    SELECT CASE 
        WHEN CZ_SOURCE_SRC IS NOT NULL AND CZ_SOURCE_SRC != '' 
        THEN CONCAT('https://www.superwnetrze.pl/i/cms/originals/', CZ_SOURCE_SRC) 
        ELSE CZ_SRC 
    END AS CZ_SOURCE_SRC, CZ_KOLEJNOSC, CZ_TYP, CZ_CZS_ID
    FROM cms_zalaczniki
    WHERE CZ_CW_ID = {product_id}
    ORDER BY CZ_KOLEJNOSC ASC
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

# Function to create the JSONL dataset
def create_fine_tune_dataset(output_file="fine_tune_dataset.jsonl"):
    products = get_product_ids_and_names()

    with open(output_file, "w", encoding="utf-8") as file:
        for product_id, product_name in products:
            # Get product images
            images = get_product_images(product_id)

            # Get product descriptions
            descriptions = get_product_descriptions(product_id)

            # Combine images into a single string
            images_str = ", ".join(images)

            # Create the input (prompt)
            prompt = f"Product: {product_name}\nImages: {images_str}\nAdditional Info: "

            # Create the completion (desired output)
            completion = {
                "description_parts": descriptions
            }

            # Write the prompt and completion in JSONL format
            file.write(json.dumps({
                "prompt": prompt,
                "completion": json.dumps(completion)  # Convert completion to string format for JSONL
            }) + "\n")

# Main function to process all products and create the dataset
def main():
    create_fine_tune_dataset()

if __name__ == "__main__":
    main()
