import sqlite3
import os
from datetime import datetime, timedelta
import json
from llm_client import LLMClient
import copy
import time # Import the time module
# import math # No longer needed
from logger import log # Import the configured logger
from collections import Counter # Import Counter for category consolidation

db_path = '/home/zetaphor/Code/browser-recall/history.db'
prompt_path = 'prompts/page_analysis.json'
# --- Configuration ---
MAX_CONTENT_LENGTH = 4000 # Define max characters per chunk
CHUNK_OVERLAP = 200       # Define overlap between chunks (optional, helps context)
# ---------------------

# --- Summarization Prompt Configuration ---
# Define the prompt and schema for the final summarization step
SUMMARIZATION_SYSTEM_PROMPT = "You are an AI assistant skilled at summarizing and categorizing text. Combine the following descriptions, categories, and topics from different parts of the same webpage into a single, concise description (1-2 sentences), the most likely overall category (1-2 words), and a consolidated list of 1-3 unique key topics. Respond ONLY with a valid JSON object containing 'description', 'category', and 'topics' fields."
SUMMARIZATION_USER_PROMPT_TEMPLATE = """Combine the following information, which represents different parts of the same webpage:

Chunk Descriptions:
{combined_descriptions}

Chunk Categories:
{combined_categories}

Chunk Topics:
{combined_topics}

Generate a single, coherent output with:
1. A final description (1-2 sentences).
2. The most representative overall category (1-2 words).
3. A consolidated list of 1-3 unique key topics from all chunks.

Format your response as a JSON object with 'description', 'category', and 'topics' fields."""
SUMMARIZATION_RESPONSE_SCHEMA = {
    "properties": {
      "description": {
        "type": "string",
        "description": "A final combined one or two sentence summary."
      },
      "category": {
          "type": "string",
          "description": "The most representative overall category (1-2 words)."
      },
      "topics": {
          "type": "array",
          "items": { "type": "string" },
          "description": "A consolidated list of 1-3 unique key topics."
      }
    },
    "required": [
      "description",
      "category",
      "topics"
    ]
  }
# ---------------------------------------

# --- Generate Markdown Output Filename ---
output_dir = "analysis_results"
os.makedirs(output_dir, exist_ok=True) # Ensure the output directory exists
today_date_str = datetime.now().strftime('%Y-%m-%d')
markdown_filename = os.path.join(output_dir, f"{today_date_str}_raw_analysis.md")
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
    total_records = len(history_records) # Get total number of records
    log.info(f"Found {total_records} records in the 'history' table to process.")

    processed_records_count = 0
    total_processing_time = 0.0

    for i, record in enumerate(history_records):
        record_start_time = time.time() # Record start time for this record
        current_record_number = i + 1 # Human-readable record number (1-based)

        record_dict = dict(zip(column_names, record))
        record_id = record_dict.get('id', f'N/A_{i}') # Use index if ID is missing
        record_title = record_dict.get('title', 'N/A')
        record_url = record_dict.get('url', 'N/A') # Get the URL
        full_content = record_dict.get('content', '')

        # Update log message to include progress
        log.info(f"Processing Record {current_record_number} of {total_records} (ID: {record_id}) - Title: {record_title[:50]}...")

        if not full_content:
            log.warning(f"  Record ID: {record_id} - Skipping: No content available.")
            # Calculate duration even for skipped records to avoid division by zero later if all are skipped
            record_end_time = time.time()
            record_duration = record_end_time - record_start_time
            # Don't increment processed_records_count, but add to total time
            total_processing_time += record_duration
            log.info(f"  Record {current_record_number} of {total_records} (ID: {record_id}) skipped in {record_duration:.2f} seconds.")
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
        chunk_categories = []   # Store categories from each chunk
        chunk_topics = []       # Store lists of topics from each chunk
        analysis_successful = True # Flag to track if analysis worked for this record
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
            analysis_result = llm_client.analyze_record(
                {"id": record_id, "chunk": chunk_index + 1}, # Pass context info
                current_messages,
                prompt_response_schema # Use the schema loaded from page_analysis.json
            )

            # Check for all required fields
            if analysis_result and \
               "description" in analysis_result and \
               "category" in analysis_result and \
               "topics" in analysis_result:
                # Store the results from the chunk
                chunk_descriptions.append(analysis_result["description"])
                chunk_categories.append(analysis_result["category"])
                # Ensure topics is a list, even if LLM returns a single string sometimes
                topics = analysis_result["topics"]
                if isinstance(topics, list):
                    chunk_topics.extend(topics) # Use extend to flatten the list of lists later
                elif isinstance(topics, str):
                     chunk_topics.append(topics) # Append if it's just a string
            else:
                log.error(f"    Record ID: {record_id}, Chunk {chunk_index + 1} - Failed to get complete analysis (description, category, topics) from LLM.")
                log.debug(f"      LLM Result: {analysis_result}") # Log the actual result for debugging
                # If any chunk fails, mark the record's analysis as unsuccessful for summarization logic
                analysis_successful = False # Decided against this, will try to summarize what we have
        # --- End Chunk Processing ---

        # --- Combine and Summarize Results ---
        final_description = None
        final_category = None
        final_topics = None

        # Check if we got any results at all
        if not chunk_descriptions: # If descriptions list is empty, others will be too
            log.warning(f"  Record ID: {record_id} - No analysis results generated from chunks. Cannot summarize.")
        elif len(content_chunks) == 1 and chunk_descriptions: # Single chunk success
             final_description = chunk_descriptions[0]
             # Use the first category and topics list directly
             if chunk_categories:
                 final_category = chunk_categories[0]
             # chunk_topics is already a flat list from the processing loop
             if chunk_topics:
                 # Ensure uniqueness and limit to 3
                 final_topics = list(dict.fromkeys(chunk_topics))[:3]

        else: # Multiple chunks require summarization/consolidation
            log.info(f"  Record ID: {record_id} - Combining {len(chunk_descriptions)} chunk analyses for final summary...")
            combined_desc_text = "\n".join(f"- {desc}" for desc in chunk_descriptions)
            combined_cat_text = "\n".join(f"- {cat}" for cat in chunk_categories)
            # Get unique topics from the flattened list collected earlier
            unique_topics = list(dict.fromkeys(chunk_topics))
            combined_topic_text = "\n".join(f"- {topic}" for topic in unique_topics)

            # Prepare messages for the summarization call
            summarization_messages = [
                {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
                {"role": "user", "content": SUMMARIZATION_USER_PROMPT_TEMPLATE.format(
                    combined_descriptions=combined_desc_text,
                    combined_categories=combined_cat_text,
                    combined_topics=combined_topic_text
                    )}
            ]

            # Prepare the response format for the summarization call
            summarization_response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "final_page_analysis_schema", # Give schema a unique name
                    "schema": SUMMARIZATION_RESPONSE_SCHEMA
                }
            }

            # Call the LLM directly for summarization
            summary_result = llm_client.llm_call(
                messages=summarization_messages,
                response_format=summarization_response_format
            )

            if summary_result and isinstance(summary_result, dict) and \
               "description" in summary_result and \
               "category" in summary_result and \
               "topics" in summary_result:
                final_description = summary_result["description"]
                final_category = summary_result["category"]
                final_topics = summary_result["topics"] # Assume LLM returns the final list
                log.info(f"  Record ID: {record_id} - Successfully generated final summary (Desc, Cat, Topics).")
            else:
                log.error(f"  Record ID: {record_id} - Failed to generate final summary from combined analysis.")
                log.debug(f"      Summarization LLM Result: {summary_result}")
                # Fallback: Use first description, most common category, and unique topics
                if chunk_descriptions:
                    final_description = chunk_descriptions[0] + " (Summarization failed)"
                if chunk_categories:
                    # Find the most common category as a simple fallback
                    category_counts = Counter(chunk_categories)
                    if category_counts:
                        final_category = category_counts.most_common(1)[0][0]
                if chunk_topics:
                    # Use unique topics collected earlier, limit to 3
                    final_topics = list(dict.fromkeys(chunk_topics))[:3]
                log.warning(f"  Record ID: {record_id} - Using fallback summarization (First Desc, Most Common Cat, Unique Topics).")


        # --- Write to Markdown File and Log Final Result ---
        # Check if we have at least a description to write
        if final_description:
             # Append to markdown file
             try:
                 with open(markdown_filename, 'a', encoding='utf-8') as md_file:
                     md_file.write(f"Title: {record_title}\n")
                     md_file.write(f"URL: {record_url}\n")
                     md_file.write(f"Description: {final_description}\n")
                     if final_category:
                         md_file.write(f"Category: {final_category}\n")
                     if final_topics:
                         # Format topics nicely
                         topics_str = ", ".join(final_topics)
                         md_file.write(f"Topics: {topics_str}\n")
                     md_file.write("\n") # Add a blank line before separator
                     md_file.write("---\n\n") # Add a separator
                 log.info(f"  Appended result for Record ID: {record_id} to {markdown_filename}")
             except Exception as e:
                 log.error(f"  Failed to write to markdown file {markdown_filename} for Record ID: {record_id}: {e}")
        else:
             log.warning(f"No final analysis generated for Record ID: {record_id}. Nothing written to markdown.")

        # --- Timing Calculation for the Record ---
        record_end_time = time.time()
        record_duration = record_end_time - record_start_time
        total_processing_time += record_duration
        processed_records_count += 1 # Increment count only for records that were attempted (not skipped early)

        log.info(f"Finished processing Record {current_record_number} of {total_records} (ID: {record_id}) in {record_duration:.2f} seconds.")
        # Optional: Log running average
        # if processed_records_count > 0:
        #     running_avg = total_processing_time / processed_records_count
        #     log.info(f"  Running average time per record: {running_avg:.2f} seconds.")
        # --- End Timing Calculation ---


except sqlite3.Error as e:
    log.exception(f"SQLite error: {e}") # Use log.exception to include traceback
except Exception as e:
    log.exception(f"An unexpected error occurred: {e}") # Use log.exception here too
finally:
    if conn:
        conn.close()
        log.info("Database connection closed.")

    # --- Final Average Calculation ---
    if processed_records_count > 0:
        average_time = total_processing_time / processed_records_count
        log.info(f"Finished processing {processed_records_count} records.")
        log.info(f"Total processing time: {total_processing_time:.2f} seconds.")
        log.info(f"Average time per record: {average_time:.2f} seconds.")
    elif total_records > 0:
         log.warning("No records were successfully processed.")
         # Log total time spent even if no records fully processed (includes skipped time)
         log.info(f"Total time spent (including skipped records): {total_processing_time:.2f} seconds.")
    else:
        log.info("No records found to process.")
    # --- End Final Average Calculation ---