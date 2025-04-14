import os
import json
import re
from datetime import datetime
from logger import log
from llm_client import LLMClient

MAX_SAMPLE_DESCRIPTIONS = 10
TOP_N_CATEGORIES = 5
TOP_N_TOPICS = 10

def _extract_descriptions_from_markdown(markdown_file_path: str) -> list[str]:
    """Extracts all description lines from the raw analysis markdown file."""
    descriptions = []
    description_regex = re.compile(r"^Description:\s*(.*)", re.IGNORECASE)
    try:
        with open(markdown_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                match = description_regex.match(line)
                if match:
                    description = match.group(1).strip()
                    if description:
                        descriptions.append(description)
    except FileNotFoundError:
        log.error(f"Markdown file not found at {markdown_file_path} during description extraction.")
        raise
    except Exception as e:
        log.exception(f"Error reading or parsing markdown file {markdown_file_path}: {e}")
        raise
    log.info(f"Extracted {len(descriptions)} descriptions from {markdown_file_path}")
    return descriptions

def _format_statistics(stats_dict: dict, top_n: int) -> str:
    """Formats the top N items from a statistics dictionary."""
    if not stats_dict:
        return "N/A"
    sorted_items = sorted(stats_dict.items(), key=lambda item: item[1], reverse=True)
    top_items = sorted_items[:top_n]
    return "\n".join([f"- {item} ({count})" for item, count in top_items])


def generate_browsing_summary(
    markdown_file_path: str,
    json_data_path: str,
    prompt_path: str,
    llm_client: LLMClient,
    output_dir: str
) -> str | None:
    """
    Generates a textual summary of browsing activity using LLM.

    Args:
        markdown_file_path: Path to the raw analysis markdown file.
        json_data_path: Path to the extracted data JSON file.
        prompt_path: Path to the JSON prompt file for summary generation.
        llm_client: Initialized LLMClient instance.
        output_dir: Directory to save the generated summary file.

    Returns:
        The path to the generated summary file, or None if generation fails.

    Raises:
        FileNotFoundError: If required input files (markdown, json, prompt) don't exist.
        Exception: For LLM errors or other processing issues.
    """
    log.info(f"Starting browsing summary generation.")
    log.info(f"Reading descriptions from: {markdown_file_path}")
    log.info(f"Reading statistics from: {json_data_path}")
    log.info(f"Using prompt template from: {prompt_path}")

    # --- Input File Checks ---
    if not os.path.exists(markdown_file_path):
        log.error(f"Markdown analysis file not found: {markdown_file_path}")
        raise FileNotFoundError(f"Markdown analysis file not found: {markdown_file_path}")
    if not os.path.exists(json_data_path):
        log.error(f"Extracted data JSON file not found: {json_data_path}")
        raise FileNotFoundError(f"Extracted data JSON file not found: {json_data_path}")
    if not os.path.exists(prompt_path):
        log.error(f"Summary prompt file not found: {prompt_path}")
        raise FileNotFoundError(f"Summary prompt file not found: {prompt_path}")

    try:
        # --- Load Data ---
        descriptions = _extract_descriptions_from_markdown(markdown_file_path)
        with open(json_data_path, 'r', encoding='utf-8') as f:
            stats_data = json.load(f)

        categories = stats_data.get("categories", {})
        topics = stats_data.get("topics", {}) # Assuming topics might have been deduplicated already

        # --- Prepare Prompt Inputs ---
        top_categories_str = _format_statistics(categories, TOP_N_CATEGORIES)
        top_topics_str = _format_statistics(topics, TOP_N_TOPICS)
        sample_descriptions_str = "\n".join([f"- {d}" for d in descriptions[:MAX_SAMPLE_DESCRIPTIONS]])

        if not descriptions:
            log.warning("No descriptions found in the markdown file. Summary might be less specific.")
            sample_descriptions_str = "N/A"
        if not categories:
            log.warning("No category data found. Summary might be less specific.")
        if not topics:
            log.warning("No topic data found. Summary might be less specific.")

        # --- Load Prompt Template ---
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = json.load(f)

        # --- Format Final Prompt ---
        # Find the user message and replace placeholders
        user_message_content = ""
        for msg in prompt_template.get("messages", []):
            if msg.get("role") == "user":
                user_message_content = msg.get("content", "")
                break

        if not user_message_content:
             log.error("Could not find user message content in prompt template.")
             raise ValueError("Invalid prompt template structure: Missing user message.")

        formatted_user_content = user_message_content.format(
            top_categories=top_categories_str,
            top_topics=top_topics_str,
            sample_descriptions=sample_descriptions_str
        )

        # Update the user message content in the template
        for msg in prompt_template["messages"]:
            if msg["role"] == "user":
                msg["content"] = formatted_user_content
                break

        # --- Call LLM ---
        log.info("Sending request to LLM for browsing summary...")
        summary_text = llm_client.llm_call(
            messages=prompt_template["messages"],
            response_format=None # Expecting plain text summary
        )

        if not summary_text or not isinstance(summary_text, str):
            log.error("LLM did not return a valid text summary.")
            return None # Indicate failure

        log.info("Received summary from LLM.")
        # Basic cleanup - remove potential leading/trailing whitespace
        summary_text = summary_text.strip()

        # --- Save Summary ---
        base_filename = os.path.basename(json_data_path)
        date_str_match = re.match(r"(\d{4}-\d{2}-\d{2})", base_filename)
        if date_str_match:
            date_str = date_str_match.group(1)
        else:
            log.warning("Could not extract date from JSON filename for summary, using current date.")
            date_str = datetime.now().strftime('%Y-%m-%d')

        summary_filename = f"{date_str}_browsing_summary.md"
        summary_filepath = os.path.join(output_dir, summary_filename)

        os.makedirs(output_dir, exist_ok=True)
        with open(summary_filepath, 'w', encoding='utf-8') as f:
            f.write(summary_text)

        log.info(f"Successfully generated and saved browsing summary: {summary_filepath}")
        return summary_filepath

    except json.JSONDecodeError as e:
        log.error(f"Error decoding JSON from {json_data_path} or {prompt_path}: {e}")
        raise
    except FileNotFoundError as e:
         log.error(f"Input file not found during summary generation: {e}")
         raise # Re-raise specific error
    except ValueError as e: # Catch potential formatting errors
         log.error(f"Value error during summary generation: {e}")
         raise
    except Exception as e:
        log.exception(f"An unexpected error occurred during browsing summary generation: {e}")
        raise # Re-raise after logging