import os
from llm_client import LLMClient
from logger import log
from history_analyzer import analyze_history
from data_extractor import extract_data_from_analysis
from summary_generator import generate_browsing_summary
from report_generator import generate_html_report

DB_PATH = '/home/zetaphor/Code/browser-recall/history.db'
PROMPT_PATH = 'prompts/page_analysis.json'
SUMMARY_PROMPT_PATH = 'prompts/browsing_summary.json'
API_BASE_URL = "http://192.168.50.246:1234"
API_KEY = "lmstudio"
MODEL_NAME = "lmstudio-community/gemma-3-12b-it"
OUTPUT_DIR = "analysis_results"
DAYS_TO_FILTER = 5 # How many days of history to process
MAX_CONTENT_LENGTH = 4000 # Max characters per chunk for LLM
CHUNK_OVERLAP = 200       # Overlap between chunks

def main():
    """
    Main function to orchestrate the browser history analysis process.
    """
    log.info("Starting main application.")
    analysis_output_file = None # Initialize variable
    extracted_data_file = None # Initialize variable
    summary_file = None # Initialize variable for the new summary file

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
        return # Stop if config files are missing
    except ValueError as e:
        log.error(f"Prompt configuration error: {e}")
        return # Stop on prompt errors
    except Exception as e:
        log.exception("An error occurred during the history analysis step.")
        return # Stop if analysis fails

    # --- Step 2: Extract Data from Analysis ---
    if analysis_output_file and os.path.exists(analysis_output_file): # Check if file exists
        try:
            log.info("Initiating data extraction step...")
            extracted_data_file = extract_data_from_analysis(
                markdown_file_path=analysis_output_file,
                output_dir=OUTPUT_DIR
            )
            log.info(f"Data extraction completed. Results written to: {extracted_data_file}")
        except FileNotFoundError as e:
             log.error(f"Data extraction error: {e}")
             # Decide if you want to stop or continue if extraction fails
        except Exception as e:
            log.exception("An error occurred during the data extraction step.")
            # Decide if you want to stop or continue if extraction fails
    else:
        log.warning(f"Skipping data extraction step because history analysis file '{analysis_output_file}' was not found or not generated.")


    # --- Step 3: Generate Browsing Summary ---
    # This step requires both the raw analysis and the extracted data
    if analysis_output_file and os.path.exists(analysis_output_file) and \
       extracted_data_file and os.path.exists(extracted_data_file):
        try:
            log.info("Initiating browsing summary generation step...")
            summary_file = generate_browsing_summary(
                markdown_file_path=analysis_output_file,
                json_data_path=extracted_data_file,
                prompt_path=SUMMARY_PROMPT_PATH, # Use the new prompt path
                llm_client=llm_client,
                output_dir=OUTPUT_DIR
            )
            if summary_file:
                log.info(f"Browsing summary generation completed. Summary saved to: {summary_file}")
            else:
                log.warning("Browsing summary generation failed or returned no content.")
                # Decide if you want to stop or continue
        except FileNotFoundError as e:
            log.error(f"Browsing summary generation error: {e}")
            # Decide if you want to stop or continue
        except Exception as e:
            log.exception("An error occurred during the browsing summary generation step.")
            # Decide if you want to stop or continue
    else:
        missing_files = []
        if not (analysis_output_file and os.path.exists(analysis_output_file)):
            missing_files.append(f"raw analysis file ('{analysis_output_file}')")
        if not (extracted_data_file and os.path.exists(extracted_data_file)):
            missing_files.append(f"extracted data file ('{extracted_data_file}')")
        log.warning(f"Skipping browsing summary generation because required input file(s) were not found or not generated: {', '.join(missing_files)}.")


    # --- Step 4: Generate HTML Report --- (Renumbered from Step 3)
    if extracted_data_file and os.path.exists(extracted_data_file): # Check if data file exists
        try:
            log.info("Initiating HTML report generation step...")
            html_report_file = generate_html_report(
                json_data_path=extracted_data_file,
                output_dir=OUTPUT_DIR,
                summary_file_path=summary_file # Pass the summary file path (can be None)
            )
            log.info(f"HTML report generation completed. Report saved to: {html_report_file}")
        except FileNotFoundError as e:
            log.error(f"HTML report generation error: {e}")
            # Decide if you want to stop or continue
        except Exception as e:
            log.exception("An error occurred during the HTML report generation step.")
            # Decide if you want to stop or continue
    else:
        log.warning("Skipping HTML report generation because extracted data file was not found or not generated.")


    log.info("Main application finished.")

if __name__ == "__main__":
    main()