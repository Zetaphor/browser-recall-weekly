import os
from llm_client import LLMClient
from logger import log
from history_analyzer import analyze_history

# --- Configuration ---
DB_PATH = '/home/zetaphor/Code/browser-recall/history.db'
PROMPT_PATH = 'prompts/page_analysis.json'
API_BASE_URL = "http://192.168.50.246:1234"
API_KEY = "lmstudio"
MODEL_NAME = "lmstudio-community/gemma-3-12b-it"
OUTPUT_DIR = "analysis_results"
DAYS_TO_FILTER = 7 # How many days of history to process
MAX_CONTENT_LENGTH = 4000 # Max characters per chunk for LLM
CHUNK_OVERLAP = 200       # Overlap between chunks
# ---------------------

def main():
    """
    Main function to orchestrate the browser history analysis process.
    """
    log.info("Starting main application.")

    # --- Initialize LLM Client ---
    try:
        llm_client = LLMClient(base_url=API_BASE_URL, api_key=API_KEY, model=MODEL_NAME)
        log.info(f"LLM Client initialized for model: {MODEL_NAME}")
    except Exception as e:
        log.exception("Failed to initialize LLM Client.")
        return # Exit if LLM client fails

    # --- Step 1: Analyze History ---
    try:
        log.info("Initiating history analysis step...")
        analysis_output_file = analyze_history(
            db_path=DB_PATH,
            prompt_path=PROMPT_PATH,
            llm_client=llm_client,
            output_dir=OUTPUT_DIR,
            days_to_filter=DAYS_TO_FILTER,
            max_content_length=MAX_CONTENT_LENGTH,
            chunk_overlap=CHUNK_OVERLAP
        )
        log.info(f"History analysis completed. Results written to: {analysis_output_file}")

    except FileNotFoundError as e:
        log.error(f"Configuration error: {e}")
    except ValueError as e:
        log.error(f"Prompt configuration error: {e}")
    except Exception as e:
        log.exception("An error occurred during the history analysis step.")
        # Decide if you want to stop or continue with other steps if analysis fails
        # For now, we'll stop.

    # --- Step 2: Add other processing steps here ---
    # log.info("Proceeding to the next step...")
    # e.g., call_another_process(analysis_output_file)

    log.info("Main application finished.")

if __name__ == "__main__":
    main()