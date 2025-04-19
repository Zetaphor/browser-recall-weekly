import sqlite3
import os
from datetime import datetime, timedelta
import json
import copy
import time
from collections import Counter
from logger import log # Import the configured logger
from llm_client import LLMClient # Import LLMClient

# --- Configuration Constants (can be overridden by arguments) ---
DEFAULT_MAX_CONTENT_LENGTH = 4000
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_DAYS_TO_FILTER = 7
DEFAULT_OUTPUT_DIR = "analysis_results"
SUMMARIZATION_PROMPT_PATH = 'prompts/summarization_analysis.json' # Added path for summarization prompt

def analyze_history(
    db_path: str,
    prompt_path: str,
    llm_client: LLMClient,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    days_to_filter: int = DEFAULT_DAYS_TO_FILTER,
    max_content_length: int = DEFAULT_MAX_CONTENT_LENGTH,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
) -> str:
    """
    Connects to the history database, analyzes recent records using an LLM,
    and writes the analysis results to a markdown file.

    Args:
        db_path: Path to the SQLite history database.
        prompt_path: Path to the JSON file containing the analysis prompt template and schema.
        llm_client: An initialized LLMClient instance.
        output_dir: Directory to save the markdown analysis results.
        days_to_filter: How many past days of history to analyze.
        max_content_length: Maximum characters per content chunk for LLM analysis.
        chunk_overlap: Overlap between content chunks.

    Returns:
        The path to the generated markdown file.

    Raises:
        FileNotFoundError: If the database or prompt file doesn't exist.
        ValueError: If the prompt file is missing required keys.
        json.JSONDecodeError: If the prompt file is not valid JSON.
        sqlite3.Error: If there's an issue with the database connection or query.
        Exception: For other unexpected errors during processing.
    """
    log.info("Starting history analysis process...")

    if not os.path.exists(db_path):
        log.error(f"Database file not found at {db_path}")
        raise FileNotFoundError(f"Database file not found at {db_path}")

    if not os.path.exists(prompt_path):
        log.error(f"Prompt file not found at {prompt_path}")
        raise FileNotFoundError(f"Prompt file not found at {prompt_path}")

    # Added check for the new summarization prompt file
    if not os.path.exists(SUMMARIZATION_PROMPT_PATH):
        log.error(f"Summarization prompt file not found at {SUMMARIZATION_PROMPT_PATH}")
        raise FileNotFoundError(f"Summarization prompt file not found at {SUMMARIZATION_PROMPT_PATH}")

    try:
        with open(prompt_path, 'r') as f:
            prompt_config = json.load(f)
            prompt_messages_template = prompt_config.get("messages")
            prompt_response_schema = prompt_config.get("response_schema")
            if not prompt_messages_template or not prompt_response_schema:
                log.error(f"'messages' or 'response_schema' missing in {prompt_path}")
                raise ValueError(f"'messages' or 'response_schema' missing in {prompt_path}")
    except json.JSONDecodeError as e:
        log.error(f"Error decoding JSON from {prompt_path}: {e}")
        raise
    except Exception as e:
        log.error(f"Error reading prompt file {prompt_path}: {e}")
        raise

    # Load summarization prompt configuration
    try:
        with open(SUMMARIZATION_PROMPT_PATH, 'r') as f:
            summarization_config = json.load(f)
            summarization_messages_template = summarization_config.get("messages")
            summarization_response_schema = summarization_config.get("response_schema")
            if not summarization_messages_template or not summarization_response_schema:
                log.error(f"'messages' or 'response_schema' missing in {SUMMARIZATION_PROMPT_PATH}")
                raise ValueError(f"'messages' or 'response_schema' missing in {SUMMARIZATION_PROMPT_PATH}")
    except json.JSONDecodeError as e:
        log.error(f"Error decoding JSON from {SUMMARIZATION_PROMPT_PATH}: {e}")
        raise
    except Exception as e:
        log.error(f"Error reading summarization prompt file {SUMMARIZATION_PROMPT_PATH}: {e}")
        raise

    # --- Generate Markdown Output Filename ---
    today_date_str = datetime.now().strftime('%Y-%m-%d')
    run_output_dir = os.path.join(output_dir, today_date_str)  # Create date-specific subfolder
    os.makedirs(run_output_dir, exist_ok=True)  # Ensure the date-specific output directory exists

    markdown_filename = os.path.join(run_output_dir, f"{today_date_str}_raw_analysis.md")
    log.info(f"Markdown output will be saved to: {markdown_filename}")
    # Clear the file if it exists to start fresh for the day
    if os.path.exists(markdown_filename):
        log.warning(f"Markdown file {markdown_filename} already exists. Overwriting.")
        open(markdown_filename, 'w').close()
    # --- End Markdown Filename ---

    conn = None
    processed_records_count = 0
    total_processing_time = 0.0
    total_records = 0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        date_threshold = datetime.now() - timedelta(days=days_to_filter)
        date_threshold_str = date_threshold.strftime('%Y-%m-%d %H:%M:%S')

        log.info(f"Selecting records updated since {date_threshold_str}...")

        query = "SELECT id, url, title, content FROM history WHERE updated >= ?"
        params = (date_threshold_str,)
        cursor.execute(query, params)

        history_records = cursor.fetchall()

        column_names = [description[0] for description in cursor.description]
        total_records = len(history_records) # Get total number of records
        log.info(f"Found {total_records} records in the 'history' table to process.")

        for i, record in enumerate(history_records):
            record_start_time = time.time() # Record start time for this record
            current_record_number = i + 1 # Human-readable record number (1-based)

            record_dict = dict(zip(column_names, record))
            record_id = record_dict.get('id', f'N/A_{i}') # Use index if ID is missing
            record_title = record_dict.get('title', 'N/A')
            record_url = record_dict.get('url', 'N/A') # Get the URL
            full_content = record_dict.get('content', '')

            log.info(f"Processing Record {current_record_number} of {total_records} (ID: {record_id}) - Title: {record_title[:50]}...")

            if not full_content:
                log.warning(f"  Record ID: {record_id} - Skipping: No content available.")
                record_end_time = time.time()
                record_duration = record_end_time - record_start_time
                total_processing_time += record_duration
                log.info(f"  Record {current_record_number} of {total_records} (ID: {record_id}) skipped in {record_duration:.2f} seconds.")
                continue

            # --- Chunking Logic ---
            content_chunks = []
            if len(full_content) > max_content_length:
                log.info(f"  Record ID: {record_id} - Content length ({len(full_content)}) exceeds limit ({max_content_length}). Chunking...")
                start = 0
                while start < len(full_content):
                    end = start + max_content_length
                    content_chunks.append(full_content[start:end])
                    next_start = end - chunk_overlap
                    if next_start <= start:
                         next_start = start + max_content_length
                    start = next_start
                    if start >= len(full_content):
                        break
                log.info(f"  Record ID: {record_id} - Split content into {len(content_chunks)} chunks.")
            else:
                content_chunks.append(full_content)
            # --- End Chunking Logic ---

            # --- Process Each Chunk ---
            chunk_descriptions = []
            chunk_categories = []
            chunk_topics = []
            for chunk_index, content_chunk in enumerate(content_chunks):
                log.info(f"  Record ID: {record_id} - Analyzing chunk {chunk_index + 1}/{len(content_chunks)}...")

                current_messages = copy.deepcopy(prompt_messages_template)
                user_message_found = False
                for msg in current_messages:
                    if msg.get("role") == "user":
                        content_template = msg.get("content", "")
                        content_template = content_template.replace("[Title]", record_title)
                        content_template = content_template.replace("[Text content]", content_chunk)
                        msg["content"] = content_template
                        user_message_found = True
                        break

                if not user_message_found:
                    log.warning(f"    Record ID: {record_id}, Chunk {chunk_index + 1} - No user message found in prompt template. Skipping analysis.")
                    continue

                analysis_result = llm_client.analyze_record(
                    {"id": record_id, "chunk": chunk_index + 1},
                    current_messages,
                    prompt_response_schema
                )

                if analysis_result and \
                   "description" in analysis_result and \
                   "category" in analysis_result and \
                   "topics" in analysis_result:
                    chunk_descriptions.append(analysis_result["description"])
                    chunk_categories.append(analysis_result["category"])
                    topics = analysis_result["topics"]
                    if isinstance(topics, list):
                        chunk_topics.extend(topics)
                    elif isinstance(topics, str):
                         chunk_topics.append(topics)
                else:
                    log.error(f"    Record ID: {record_id}, Chunk {chunk_index + 1} - Failed to get complete analysis (description, category, topics) from LLM.")
                    log.debug(f"      LLM Result: {analysis_result}")
            # --- End Chunk Processing ---

            # --- Combine and Summarize Results ---
            final_description = None
            final_category = None
            final_topics = None

            if not chunk_descriptions:
                log.warning(f"  Record ID: {record_id} - No analysis results generated from chunks. Cannot summarize.")
            elif len(content_chunks) == 1 and chunk_descriptions:
                 final_description = chunk_descriptions[0]
                 if chunk_categories:
                     final_category = chunk_categories[0]
                 if chunk_topics:
                     final_topics = list(dict.fromkeys(chunk_topics))[:3]
            else: # Multiple chunks require summarization/consolidation
                log.info(f"  Record ID: {record_id} - Combining {len(chunk_descriptions)} chunk analyses for final summary...")
                combined_desc_text = "\n".join(f"- {desc}" for desc in chunk_descriptions)
                combined_cat_text = "\n".join(f"- {cat}" for cat in chunk_categories)
                unique_topics = list(dict.fromkeys(chunk_topics))
                combined_topic_text = "\n".join(f"- {topic}" for topic in unique_topics)

                # Use loaded summarization prompt template
                current_summarization_messages = copy.deepcopy(summarization_messages_template)
                user_message_found = False
                for msg in current_summarization_messages:
                    if msg.get("role") == "user":
                        content_template = msg.get("content", "")
                        content_template = content_template.replace("{combined_descriptions}", combined_desc_text)
                        content_template = content_template.replace("{combined_categories}", combined_cat_text)
                        content_template = content_template.replace("{combined_topics}", combined_topic_text)
                        msg["content"] = content_template
                        user_message_found = True
                        break

                if not user_message_found:
                     log.error(f"  Record ID: {record_id} - No user message found in summarization prompt template. Cannot summarize.")
                     # Fallback logic remains the same...
                     if chunk_descriptions:
                         final_description = chunk_descriptions[0] + " (Summarization failed - template error)"
                     if chunk_categories:
                         category_counts = Counter(chunk_categories)
                         if category_counts:
                             final_category = category_counts.most_common(1)[0][0]
                     if chunk_topics:
                         final_topics = list(dict.fromkeys(chunk_topics))[:3]
                     log.warning(f"  Record ID: {record_id} - Using fallback summarization (First Desc, Most Common Cat, Unique Topics).")
                else:
                    # Use loaded summarization response schema
                    summarization_response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "final_page_analysis_schema",
                            "schema": summarization_response_schema # Use loaded schema
                        }
                    }

                    summary_result = llm_client.llm_call(
                        messages=current_summarization_messages, # Use updated messages
                        response_format=summarization_response_format
                    )

                    if summary_result and isinstance(summary_result, dict) and \
                       "description" in summary_result and \
                       "category" in summary_result and \
                       "topics" in summary_result:
                        final_description = summary_result["description"]
                        final_category = summary_result["category"]
                        final_topics = summary_result["topics"]
                        log.info(f"  Record ID: {record_id} - Successfully generated final summary (Desc, Cat, Topics).")
                    else:
                        log.error(f"  Record ID: {record_id} - Failed to generate final summary from combined analysis.")
                        log.debug(f"      Summarization LLM Result: {summary_result}")
                        # Fallback logic remains the same...
                        if chunk_descriptions:
                            final_description = chunk_descriptions[0] + " (Summarization failed)"
                        if chunk_categories:
                            category_counts = Counter(chunk_categories)
                            if category_counts:
                                final_category = category_counts.most_common(1)[0][0]
                        if chunk_topics:
                            final_topics = list(dict.fromkeys(chunk_topics))[:3]
                        log.warning(f"  Record ID: {record_id} - Using fallback summarization (First Desc, Most Common Cat, Unique Topics).")

            # --- Write to Markdown File ---
            if final_description:
                 try:
                     with open(markdown_filename, 'a', encoding='utf-8') as md_file:
                         md_file.write(f"Title: {record_title}\n")
                         md_file.write(f"URL: {record_url}\n")
                         md_file.write(f"Description: {final_description}\n")
                         if final_category:
                             md_file.write(f"Category: {final_category}\n")
                         if final_topics:
                             topics_str = ", ".join(final_topics)
                             md_file.write(f"Topics: {topics_str}\n")
                         md_file.write("\n---\n\n")
                     log.info(f"  Appended result for Record ID: {record_id} to {markdown_filename}")
                 except Exception as e:
                     log.error(f"  Failed to write to markdown file {markdown_filename} for Record ID: {record_id}: {e}")
            else:
                 log.warning(f"No final analysis generated for Record ID: {record_id}. Nothing written to markdown.")

            # --- Timing Calculation for the Record ---
            record_end_time = time.time()
            record_duration = record_end_time - record_start_time
            total_processing_time += record_duration
            processed_records_count += 1

            log.info(f"Finished processing Record {current_record_number} of {total_records} (ID: {record_id}) in {record_duration:.2f} seconds.")

    except sqlite3.Error as e:
        log.exception(f"SQLite error during history analysis: {e}")
        raise # Re-raise the exception after logging
    except Exception as e:
        log.exception(f"An unexpected error occurred during history analysis: {e}")
        raise # Re-raise the exception after logging
    finally:
        if conn:
            conn.close()
            log.info("Database connection closed.")

        # --- Final Average Calculation ---
        log.info("-" * 20 + " Analysis Summary " + "-" * 20)
        if processed_records_count > 0:
            average_time = total_processing_time / processed_records_count
            log.info(f"Finished processing {processed_records_count} records.")
            log.info(f"Total processing time: {total_processing_time:.2f} seconds.")
            log.info(f"Average time per record: {average_time:.2f} seconds.")
        elif total_records > 0:
             log.warning("No records were successfully processed.")
             log.info(f"Total time spent (including skipped records): {total_processing_time:.2f} seconds.")
        else:
            log.info("No records found to process in the specified timeframe.")
        log.info(f"Analysis results saved to: {markdown_filename}")
        log.info("-" * 58)


    return markdown_filename