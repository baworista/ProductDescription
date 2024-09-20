import mysql.connector

# Database connection details
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'superwnetrze',
    'database': 'superwnetrze_db'
}

# Function to build CA_TRESC field and update it in cms_art_produkty
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
    cursor.execute(query, (product_id,))
    description_parts = cursor.fetchall()

    # Initialize CA_TRESC as an empty string
    ca_tresc = ""

    # Loop over each description part and generate HTML
    for part in description_parts:
        order, text, text2, kind = part

        # Handle image dimensions (mimic logic from PHP)
        for field in ['text', 'text2']:
            field_content = text if field == 'text' else text2
            if '<img' in field_content:
                # Find all image URLs in text/text2
                images = []
                image_query = f"SELECT CZ_WIDTH, CZ_HEIGHT FROM cms_zalaczniki WHERE CZ_SRC = %s"
                img_srcs = extract_image_sources(field_content)

                for img_src in img_srcs:
                    cursor.execute(image_query, (img_src,))
                    img = cursor.fetchone()
                    if img and img[0] > 0:
                        # Insert width and height attributes in <img> tag
                        width, height = img
                        field_content = field_content.replace(f'<img src="{img_src}"', f'<img src="{img_src}" width="{width}" height="{height}"')
                
                if field == 'text':
                    text = field_content
                else:
                    text2 = field_content

        # Generate HTML based on 'kind'
        if kind in ['img-txt', 'txt-img', 'img-img']:
            section_html = f"""
            <div class="ck-content wysiwyg-ck desc-row s-{kind}">
                <div class="side">{text}</div>
                <div class="side">{text2}</div>
            </div>
            """
        else:
            # For regular sections (e.g., 'short')
            section_html = f"""
            <div class="ck-content wysiwyg-ck s-{kind}" style="overflow:hidden">
                {text}
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

# Example usage
def main():
    product_id = 160881  # Example product ID

    # Update CA_TRESC field with the combined HTML
    update_ca_tresc(product_id)

if __name__ == "__main__":
    main()
