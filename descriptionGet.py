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

# Function to execute SQL query and get the product IDs where ca_is_multitext = 1
def get_product_ids():
    # Database connection details (you may need to adjust these)
    connection = mysql.connector.connect(**DB_CONFIG)

    cursor = connection.cursor()

    # SQL query to get product IDs where ca_is_multitext = 1
    query = "SELECT ca_cw_id FROM cms_art_produkty WHERE ca_is_multitext = 1 LIMIT 1"

    # Execute the query
    cursor.execute(query)

    # Fetch all results
    product_ids = [row[0] for row in cursor.fetchall()]

    # Close the database connection
    cursor.close()
    connection.close()

    return product_ids

# Function to retrieve and structure product description parts
def get_product_descriptions(product_id):
    # Database connection details (you may need to adjust these)
    connection = mysql.connector.connect(
        host='localhost',
        user='root',
        password='superwnetrze',
        database='superwnetrze_db'
    )

    cursor = connection.cursor()

    # SQL query to get all description parts for the given product, ordered by 'capd_desc_order'
    query = f"""
    SELECT capd_desc_order, capd_desc_text, capd_desc_text2, capd_kind
    FROM cms_art_produkty_desc
    WHERE capd_cw_id = {product_id}
    ORDER BY capd_desc_order ASC
    """
    
    # Execute the query
    cursor.execute(query)
    
    # Fetch all results
    rows = cursor.fetchall()
    
    # Initialize structured JSON
    product_description = {
        "product_id": product_id,
        "description_parts": []
    }

    # Parse the data into the desired structure
    for row in rows:
        order, desc_text, desc_text2, kind = row
        
        part = {
            "order": order,
            "left": desc_text,
            "right": desc_text2
        }
        
        # Add the part to the list of description parts
        product_description["description_parts"].append(part)
    
    # Close the database connection
    cursor.close()
    connection.close()

    # Return the structured data
    return product_description

# Function to process all products and store their descriptions in JSON format
def process_all_products():
    # Get the product IDs from the database
    product_ids = get_product_ids()

    all_product_descriptions = []

    # Iterate over each product ID and retrieve its descriptions
    for product_id in product_ids:
        product_description = get_product_descriptions(product_id)
        all_product_descriptions.append(product_description)

    # Convert to JSON and return (ensure_ascii=False to handle non-ASCII characters)
    return json.dumps(all_product_descriptions, indent=4, ensure_ascii=False)

# Example usage
def main():
    # Process all products and get descriptions in JSON
    product_descriptions_json = process_all_products()

    # Print the JSON structure
    print(f"All Product Descriptions JSON:\n{product_descriptions_json}")

if __name__ == "__main__":
    main()
