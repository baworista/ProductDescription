This program created to generate good descriptions with images related on info from database and oriented on its structure.

Main things are wrote in prompt itself, but there are several things to mention:

1.Used tables in order as it used in code:
-**cms_art_produkty* - table with product information, such as CA_CW_ID(which is not primary key in database logic, but used everywhere), CA_TYTUL, ca_filters_material1, ca_filters_material2, ca_filters_material3, ca_filters_wysokosc, ca_filters_dlugosc, ca_filters_szerokosc, ca_filters_glebokosc, ca_filters_srednica, ca_filters_pojemnosc, CA_PRODUCENT_ID respectively
-*cms_producenci* - table where we need only producent name
-*cms_zalaczniki* - table with al images related to its product's id
    There are many images with different sizes and links, the sql query returns first 3 images links
-*cms_art_produkty_desc* - structured order, left / right part(detailed in prompt) 
-*cms_art_produkty* there are field ca_is_multitet which sould be changed on true, but for now it is not implemented
-*cms_art_produkty* - used INSERT for new description

2.The program **v1.4** takes EAN code and works in following order:
 - *get_product_info_with_ean()* Takes product info from database
 - *get_product_images()* Takes all product images links
 - *send_image_url_to_gpt()* Takes image link and uses gpt4o vision to describe it
 - *process_images_with_descriptions()* Makes dictionary of id, link and descriptions
 - *send_chat_data_to_gpt()* Sends whole data to make new description
 - *replace_img_id_with_urls()* After chat response returns links instead of id(if try to do it with links directly, chat often generates new one which dont exist)
 - *description_parts_to_insert()* Parse all chat output and insert new description in *cms_art_produkty_desc*
 - *update_ca_tresc()* Runned in previous func, using info from *cms_art_produkty_desc*
 - *extract_image_sources()* Insert links instead of ids
 - *display_fine_tune_input_for_single_product()* Main function which uses all previously described

 3. The program **fineTuningDatasetGPT4o1img_id.py** is used to make dataset(System msg, user input and desired output) for chat gpt fine-tuning. Has almost the same structure as
 v1.4, but additionaly wrotes good structured data into jsonl file. 

 4. The program **fineTuning.py** is a file to make fine-tuned particular model using gpt api.
