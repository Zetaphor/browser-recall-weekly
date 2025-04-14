import sqlite3
import os
from datetime import datetime, timedelta
import json
from llm_client import LLMClient
import copy
# import math # No longer needed
from logger import log # Import the configured logger

db_path = '/home/zetaphor/Code/browser-recall/history.db'
prompt_path = 'prompts/page_analysis.json'
# --- Configuration ---
MAX_CONTENT_LENGTH = 4000 # Define max characters per chunk
CHUNK_OVERLAP = 200       # Define overlap between chunks (optional, helps context)
# ---------------------

# --- Summarization Prompt Configuration ---
# Define the prompt and schema for the final summarization step
SUMMARIZATION_SYSTEM_PROMPT = "You are an AI assistant skilled at summarizing text. Combine the following descriptions into a single, concise description of one or two sentences. Respond ONLY with a valid JSON object containing the 'description' field."
SUMMARIZATION_USER_PROMPT_TEMPLATE = "Combine the following descriptions, which represent different parts of the same webpage, into a single, coherent description of one or two sentences:\n\n{combined_descriptions}\n\nFormat your response as a JSON object with a single 'description' field."
SUMMARIZATION_RESPONSE_SCHEMA = {
    "properties": {
      "description": {
        "type": "string",
        "description": "A final combined one or two sentence summary."
      }
    },
    "required": [
      "description"
    ]
  }
# ---------------------------------------

# --- Generate Markdown Output Filename ---
output_dir = "analysis_results"
os.makedirs(output_dir, exist_ok=True) # Ensure the output directory exists
today_date_str = datetime.now().strftime('%Y-%m-%d')
markdown_filename = os.path.join(output_dir, f"{today_date_str}_analysis.md")
log.info(f"Markdown output will be saved to: {markdown_filename}")
# --- End Markdown Filename ---


if not os.path.exists(db_path):
    log.error(f"Database file not found at {db_path}")
    exit()

if not os.path.exists(prompt_path):
    log.error(f"Prompt file not found at {prompt_path}")
    exit()

try:
    with open(prompt_path, 'r') as f:
        prompt_config = json.load(f)
        # Extract messages and schema
        prompt_messages_template = prompt_config.get("messages")
        prompt_response_schema = prompt_config.get("response_schema")
        if not prompt_messages_template or not prompt_response_schema:
            log.error(f"'messages' or 'response_schema' missing in {prompt_path}")
            exit()
except json.JSONDecodeError as e:
    log.error(f"Error decoding JSON from {prompt_path}: {e}")
    exit()
except Exception as e:
    log.error(f"Error reading prompt file {prompt_path}: {e}")
    exit()

API_BASE_URL = "http://192.168.50.246:1234"
API_KEY = "lmstudio"
MODEL_NAME = "lmstudio-community/gemma-3-12b-it"

llm_client = LLMClient(base_url=API_BASE_URL, api_key=API_KEY, model=MODEL_NAME)

conn = None
try:
    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()

    days_to_filter = 7
    date_threshold = datetime.now() - timedelta(days=days_to_filter)
    date_threshold_str = date_threshold.strftime('%Y-%m-%d %H:%M:%S')

    log.info(f"Selecting records created since {date_threshold_str}...")

    query = "SELECT id, url, title, content FROM history WHERE created >= ?"
    params = (date_threshold_str,)
    cursor.execute(query, params)

    history_records = cursor.fetchall()

    column_names = [description[0] for description in cursor.description]
    log.info(f"Found {len(history_records)} records in the 'history' table.")

    for i, record in enumerate(history_records):
        record_dict = dict(zip(column_names, record))
        record_id = record_dict.get('id', f'N/A_{i}') # Use index if ID is missing
        record_title = record_dict.get('title', 'N/A')
        record_url = record_dict.get('url', 'N/A') # Get the URL
        full_content = record_dict.get('content', '')

        log.info(f"Processing Record ID: {record_id} - Title: {record_title[:50]}...")

        if not full_content:
            log.warning(f"  Record ID: {record_id} - Skipping: No content available.")
            # print("-" * 10) # Removed decorative print
            continue

        # --- Chunking Logic ---
        content_chunks = []
        if len(full_content) > MAX_CONTENT_LENGTH:
            log.info(f"  Record ID: {record_id} - Content length ({len(full_content)}) exceeds limit ({MAX_CONTENT_LENGTH}). Chunking...")
            start = 0
            while start < len(full_content):
                end = start + MAX_CONTENT_LENGTH
                content_chunks.append(full_content[start:end])
                # Move start for the next chunk, considering overlap
                next_start = end - CHUNK_OVERLAP
                # Ensure next_start doesn't go backward if overlap is large or chunk is small
                if next_start <= start:
                     next_start = start + MAX_CONTENT_LENGTH # Move forward without overlap if needed
                start = next_start
                # Break if we've essentially processed the end
                if start >= len(full_content):
                    break
            log.info(f"  Record ID: {record_id} - Split content into {len(content_chunks)} chunks.")
        else:
            content_chunks.append(full_content) # Process as a single chunk if short enough
        # --- End Chunking Logic ---

        # --- Process Each Chunk ---
        chunk_descriptions = [] # Store descriptions from each chunk
        for chunk_index, content_chunk in enumerate(content_chunks):
            log.info(f"  Record ID: {record_id} - Analyzing chunk {chunk_index + 1}/{len(content_chunks)}...")

            # Deep copy the message template for this specific chunk
            current_messages = copy.deepcopy(prompt_messages_template)

            # Find the user message and substitute placeholders
            user_message_found = False
            for msg in current_messages:
                if msg.get("role") == "user":
                    content_template = msg.get("content", "")
                    # Replace placeholders
                    content_template = content_template.replace("[Title]", record_title)
                    # Use the current chunk's content
                    content_template = content_template.replace("[Text content]", content_chunk)
                    msg["content"] = content_template
                    user_message_found = True
                    break # Assume only one user message needs substitution

            if not user_message_found:
                log.warning(f"    Record ID: {record_id}, Chunk {chunk_index + 1} - No user message found in prompt template. Skipping analysis.")
                continue

            # Pass the modified messages and the schema to the client
            # Pass record_id and chunk_index for better error reporting in analyze_record if needed
            analysis_result = llm_client.analyze_record(
                {"id": record_id, "chunk": chunk_index + 1}, # Pass context info
                current_messages,
                prompt_response_schema # Use the schema loaded from page_analysis.json
            )

            if analysis_result and "description" in analysis_result:
                # Store the description from the chunk
                chunk_descriptions.append(analysis_result["description"])
                log.info(f"    Record ID: {record_id}, Chunk {chunk_index + 1} - Description received.")
                # Optional: Log individual chunk description for debugging
                # log.debug(f"      Desc: {analysis_result['description'][:100]}...")
            else:
                log.error(f"    Record ID: {record_id}, Chunk {chunk_index + 1} - Failed to get description from LLM.")
        # --- End Chunk Processing ---

        # --- Combine and Summarize Descriptions ---
        final_description = None
        if not chunk_descriptions:
            log.warning(f"  Record ID: {record_id} - No descriptions generated from chunks. Cannot summarize.")
        elif len(chunk_descriptions) == 1:
            log.info(f"  Record ID: {record_id} - Single chunk processed. Using its description.")
            final_description = chunk_descriptions[0]
        else:
            log.info(f"  Record ID: {record_id} - Combining {len(chunk_descriptions)} chunk descriptions for final summary...")
            combined_text = "\n\n".join(f"- {desc}" for desc in chunk_descriptions) # Join with newlines for clarity

            # Prepare messages for the summarization call
            summarization_messages = [
                {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
                {"role": "user", "content": SUMMARIZATION_USER_PROMPT_TEMPLATE.format(combined_descriptions=combined_text)}
            ]

            # Prepare the response format for the summarization call
            summarization_response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "summarization_schema",
                    "schema": SUMMARIZATION_RESPONSE_SCHEMA
                }
            }

            # Call the LLM directly for summarization
            summary_result = llm_client.llm_call(
                messages=summarization_messages,
                response_format=summarization_response_format
            )

            if summary_result and isinstance(summary_result, dict) and "description" in summary_result:
                final_description = summary_result["description"]
                log.info(f"  Record ID: {record_id} - Successfully generated final summary.")
            else:
                log.error(f"  Record ID: {record_id} - Failed to generate final summary from combined descriptions.")
                # Fallback: just concatenate descriptions if summarization fails
                # final_description = " ".join(chunk_descriptions)
                # log.warning("  Using concatenated descriptions as fallback.")


        # --- Write to Markdown File and Log Final Result ---
        if final_description:
             log.info(f"Final Description (Record ID: {record_id}): {final_description}")
             # Append to markdown file
             try:
                 with open(markdown_filename, 'a', encoding='utf-8') as md_file:
                     md_file.write(f"Title: {record_title}\n")
                     md_file.write(f"URL: {record_url}\n")
                     md_file.write(f"Description: {final_description}\n\n")
                     md_file.write("---\n\n") # Add a separator
                 log.info(f"  Appended result for Record ID: {record_id} to {markdown_filename}")
             except Exception as e:
                 log.error(f"  Failed to write to markdown file {markdown_filename} for Record ID: {record_id}: {e}")
        else:
             log.warning(f"No final description generated for Record ID: {record_id}.")


        # print("-" * 10) # Removed decorative print


except sqlite3.Error as e:
    log.exception(f"SQLite error: {e}") # Use log.exception to include traceback
except Exception as e:
    log.exception(f"An unexpected error occurred: {e}") # Use log.exception here too
finally:
    if conn:
        conn.close()
        log.info("Database connection closed.")