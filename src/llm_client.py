import os
import requests
import json
from logger import log # Import the configured logger

class LLMClient:
    """
    A client class to interact with an OpenAI compatible LLM API using HTTP requests.
    """
    def __init__(self, api_key=None, base_url=None, model="default-model"):
        """
        Initializes the LLM client.

        Args:
            api_key (str, optional): The API key for authentication. Defaults to None (uses env var OPENAI_API_KEY).
            base_url (str, optional): The base URL of the API endpoint. Defaults to None (uses env var OPENAI_BASE_URL).
            model (str): The name of the model to use for completions.
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.model = model

        if not self.base_url:
            # Log error instead of raising immediately, allow potential fallback if needed elsewhere
            log.error("API base_url is missing. Provide it as an argument or via OPENAI_BASE_URL env var.")
            # raise ValueError("API base_url must be provided either as an argument or via OPENAI_BASE_URL environment variable.")
        else:
            # Ensure base_url ends with /v1 if it's likely an OpenAI-compatible URL
            if "api.openai.com" not in self.base_url and not self.base_url.endswith("/v1"): # Adjusted logic slightly
                 self.base_url = self.base_url.rstrip('/') + "/v1" # Append /v1 if needed
                 log.debug(f"Appended /v1 to base_url. New base_url: {self.base_url}")

            self.chat_endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
            log.info(f"LLMClient initialized. Chat endpoint: {self.chat_endpoint}")


    def analyze_record(self, record_data, messages, response_schema):
        """
        Analyzes a single history record using the LLM with a defined response schema.

        Args:
            record_data (dict): A dictionary containing the data for one history record (e.g., id, url, title, content).
            messages (list): The list of message objects with placeholders already substituted.
            response_schema (dict): The JSON schema defining the expected response structure
                                    (containing keys like 'properties', 'required').

        Returns:
            dict or None: The parsed JSON analysis result from the LLM, or None if an error occurred.
        """
        record_id = record_data.get('id', 'N/A')
        chunk_id = record_data.get('chunk', 'N/A')
        log.debug(f"Analyzing record ID: {record_id}, Chunk: {chunk_id}")
        try:
            # The messages list with substituted placeholders is passed directly

            # Define the desired response format using the provided schema
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    # Add a descriptive name (optional but good practice)
                    "name": "page_analysis_schema",
                    # Nest the actual schema definition under the 'schema' key
                    "schema": response_schema
                }
            }

            # Call the llm_call method with the prepared messages and format
            analysis_result = self.llm_call(messages, response_format=response_format)

            return analysis_result

        except Exception as e:
            # Use log.exception to include traceback details
            log.exception(f"An error occurred during analyze_record setup for record {record_id}, chunk {chunk_id}: {e}")
            return None


    def llm_call(self, messages, response_format=None):
        """
        Calls the LLM API with the given messages and response format.

        Args:
            messages (list): A list of message objects (dicts with 'role' and 'content').
            response_format (dict, optional): A dictionary specifying the desired response format
                                            (e.g., {"type": "json_schema", "json_schema": {...}}). Defaults to None.

        Returns:
            str or dict: The content of the LLM's response (string or parsed JSON), or None if an error occurred.
        """
        if not self.api_key:
            log.error("API key is missing. Cannot make API call.")
            return None
        if not self.base_url or not hasattr(self, 'chat_endpoint'):
             log.error("API base_url or chat_endpoint is not configured. Cannot make API call.")
             return None

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0,
            }

            # Add response_format to the payload if provided
            if response_format:
                # Ensure the entire response_format structure is included
                payload["response_format"] = response_format
                log.debug(f"Requesting response format: {response_format.get('type')}")

            log.debug(f"Sending request to {self.chat_endpoint} with model {self.model}")
            # log.debug(f"Payload (excluding messages): { {k:v for k,v in payload.items() if k != 'messages'} }") # Avoid logging potentially large messages content at debug level unless needed

            response = requests.post(
                self.chat_endpoint,
                headers=headers,
                data=json.dumps(payload), # Send data as JSON string
                timeout=120 # Increased timeout slightly for potentially longer analysis
            )

            log.debug(f"Received response with status code: {response.status_code}")

            # Check if the request was successful
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

            # Parse the JSON response
            response_data = response.json()

            # Extract the content from the response structure (adjust if your API differs)
            if response_data.get("choices") and len(response_data["choices"]) > 0:
                message = response_data["choices"][0].get("message")
                if message and message.get("content"):
                    content_str = message["content"]
                    log.debug("Successfully extracted content from LLM response.")
                    # Try to parse the content as JSON if a structured format was requested
                    if response_format and response_format.get("type") in ["json_object", "json_schema"]:
                        try:
                            # The API should return valid JSON string in the content field
                            # when json_object or json_schema is requested
                            result = json.loads(content_str)
                            log.info("Successfully parsed JSON response from LLM.")
                        except json.JSONDecodeError as json_err:
                            log.error(f"LLM response content is not valid JSON despite requesting {response_format.get('type')}.")
                            log.error(f"JSONDecodeError: {json_err}")
                            log.error(f"Raw content snippet: {content_str[:500]}...") # Print more context
                            result = None # Indicate failure to parse JSON
                    else:
                         result = content_str.strip() # Default to string if no specific format requested
                         log.debug("Returning raw string content from LLM.")
                else:
                    log.error("Could not find message content in LLM response choice.")
                    result = None
            else:
                log.error("'choices' field missing, empty, or invalid in LLM response.")
                log.debug(f"Full response data: {response_data}")
                result = None
            # --- End API call ---

            return result

        except requests.exceptions.Timeout as timeout_err:
             # Access timeout value from the request object if needed
             timeout_value = timeout_err.request.timeout if hasattr(timeout_err.request, 'timeout') else 'N/A'
             log.error(f"LLM API call timed out after {timeout_value} seconds.")
             return None
        except requests.exceptions.RequestException as http_error:
            log.error(f"HTTP Error calling LLM API: {http_error}")
            # Optionally print response body for more details on API errors
            if hasattr(http_error, 'response') and http_error.response is not None:
                 log.error(f"Response status: {http_error.response.status_code}")
                 try:
                     log.error(f"Response body: {http_error.response.json()}")
                 except json.JSONDecodeError:
                     log.error(f"Response body (non-JSON): {http_error.response.text}")
            return None
        except json.JSONDecodeError as json_error:
            log.error(f"Error decoding JSON response from LLM API: {json_error}")
            # Ensure response is defined before accessing .text
            raw_text = 'N/A'
            if 'response' in locals() and hasattr(response, 'text'):
                raw_text = response.text
            log.error(f"Raw response text: {raw_text}")
            return None
        except Exception as e:
            # Catch any other unexpected errors during processing
            log.exception(f"An unexpected error occurred during LLM call: {e}") # Use log.exception
            return None