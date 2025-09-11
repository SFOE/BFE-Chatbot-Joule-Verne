import logging
import json

logging.basicConfig(level=logging.INFO)

with open('./data/all_pdf_data.json', 'r') as input_file, open('./data/metadata.jsonl', 'w') as output_file:
      data =  json.load(input_file)
      for record in data:
            output_file.write(json.dumps(record) + '\n')
            

bucket_name = 'bfe-public-data-pdf'
object_key = 'metadata/metadata.jsonl'

# if upload_file('./data/metadata.jsonl', bucket_name, object_key):
#     print("File uploaded successfully!")
# else:
#     print("Failed to upload file.")

