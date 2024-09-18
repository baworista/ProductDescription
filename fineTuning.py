from openai import OpenAI
import os
from dotenv import load_dotenv

# Load the API key from the environment variables
load_dotenv()

# Initialize OpenAI client (it will default to picking the API key from env)
client = OpenAI()

# # Upload the fine-tuning dataset, opening the file in binary mode ('rb')
# with open("fine_tune_chat_dataset.jsonl", "rb") as f:
#     response = client.files.create(
#         file=f,
#         purpose='fine-tune'
#     )

# # Print file ID
# print(response.id)


# # CREATE FINE-TUNING JOB
# response = client.fine_tuning.jobs.create(
#   training_file="file-xpwFa5rPgofDhRJjTSJGW96f",
#   model="gpt-4o-2024-08-06",
# )

# # Print the fine-tuning job details
# print(response)


# MONITOR FINE-TUNING JOB
# ftjob-k6gOW9YbNsAigLvZZAXY9bbD - v1.2(test fine-tuning)
# ftjob-R21W8ii0zLej2vLNaBATsRkF - v1.3(id, name and img urls)
# ftjob-dzMBKxXWVjcUdZSSAI6tQsdW - v1.4(id, name, materials, img ids)
response = client.fine_tuning.jobs.retrieve("ftjob-dzMBKxXWVjcUdZSSAI6tQsdW")

# Check the fine-tuned model ID
print(response)


# TEST USAGE
# completion = client.chat.completions.create(
#   model="ft:gpt-4o-2024-08-06:my-org:custom_suffix:ftjob-pHyvfekGVLqpFu5HQsCrVW6E",
#   messages=[
#     {"role": "system", "content": "You are a helpful assistant."},
#     {"role": "user", "content": "Hello!"}
#   ]
# )
# print(completion.choices[0].message)




# List 10 fine-tuning jobs
#client.fine_tuning.jobs.list()

# # Retrieve the state of a fine-tune
# client.fine_tuning.jobs.retrieve("ftjob-abc123")

# # Cancel a job
# client.fine_tuning.jobs.cancel("ftjob-abc123")

# # List up to 10 events from a fine-tuning job
# client.fine_tuning.jobs.list_events(fine_tuning_job_id="ftjob-abc123", limit=10)

# # Delete a fine-tuned model (must be an owner of the org the model was created in)
# client.models.delete("ft:gpt-3.5-turbo:acemeco:suffix:abc123")