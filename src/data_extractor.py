import os
import re
import json
from collections import Counter
from datetime import datetime
from logger import log

def extract_data_from_analysis(markdown_file_path: str, output_dir: str) -> str:
    """
    Parses a markdown analysis file to extract and count unique categories and topics.

    Args:
        markdown_file_path: Path to the input markdown analysis file.
        output_dir: Directory to save the extracted data JSON file.

    Returns:
        The path to the generated JSON file.

    Raises:
        FileNotFoundError: If the markdown file doesn't exist.
        Exception: For other unexpected errors during processing.
    """
    log.info(f"Starting data extraction from: {markdown_file_path}")

    if not os.path.exists(markdown_file_path):
        log.error(f"Markdown analysis file not found at {markdown_file_path}")
        raise FileNotFoundError(f"Markdown analysis file not found at {markdown_file_path}")

    category_counter = Counter()
    topic_counter = Counter()

    # Regex to find Category and Topics lines
    category_regex = re.compile(r"^Category:\s*(.*)", re.IGNORECASE)
    topics_regex = re.compile(r"^Topics:\s*(.*)", re.IGNORECASE)

    try:
        with open(markdown_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                category_match = category_regex.match(line)
                if category_match:
                    category = category_match.group(1).strip()
                    if category:
                        category_counter[category] += 1
                    continue # Move to next line once category is found

                topics_match = topics_regex.match(line)
                if topics_match:
                    topics_str = topics_match.group(1).strip()
                    if topics_str:
                        # Split topics by comma, strip whitespace from each
                        topics = [topic.strip() for topic in topics_str.split(',') if topic.strip()]
                        topic_counter.update(topics)

        log.info(f"Found {len(category_counter)} unique categories and {len(topic_counter)} unique topics.")

        # --- Generate JSON Output Filename ---
        # Extract date from the markdown filename (e.g., 2024-05-15_raw_analysis.md)
        base_filename = os.path.basename(markdown_file_path)
        date_str_match = re.match(r"(\d{4}-\d{2}-\d{2})", base_filename)
        if date_str_match:
            date_str = date_str_match.group(1)
        else:
            # Fallback to current date if pattern doesn't match
            log.warning("Could not extract date from filename, using current date.")
            date_str = datetime.now().strftime('%Y-%m-%d')

        json_filename = os.path.join(output_dir, f"{date_str}_extracted_data.json")
        log.info(f"Extracted data will be saved to: {json_filename}")

        # --- Prepare JSON Data ---
        output_data = {
            "categories": dict(category_counter),
            "topics": dict(topic_counter)
        }

        # --- Write to JSON File ---
        os.makedirs(output_dir, exist_ok=True) # Ensure output directory exists
        with open(json_filename, 'w', encoding='utf-8') as json_file:
            json.dump(output_data, json_file, indent=4, ensure_ascii=False)

        log.info(f"Successfully wrote extracted data to {json_filename}")
        return json_filename

    except Exception as e:
        log.exception(f"An error occurred during data extraction from {markdown_file_path}: {e}")
        raise # Re-raise the exception after logging