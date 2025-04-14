import os
import json
import re
from datetime import datetime
from logger import log
from wordcloud import WordCloud

# Basic HTML template - Updated with dark mode CSS
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Analysis Report - {report_date}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{
            font-family: sans-serif;
            line-height: 1.6;
            margin: 20px;
            background-color: #1e1e1e; /* Dark background */
            color: #d4d4d4; /* Light text */
        }}
        h1, h2, h3 {{
            color: #a3ffb4; /* Lighter heading color (was #9cdcfe) */
            border-bottom: 1px solid #444;
            padding-bottom: 5px;
        }}
        pre {{
            background-color: #252526; /* Slightly lighter dark for code blocks */
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto; /* Add scrollbars if code is too wide */
            border: 1px solid #444;
            color: #d4d4d4; /* Ensure pre text is light */
        }}
        code {{
            font-family: monospace;
            background-color: #252526; /* Consistent code background */
            padding: 2px 4px;
            border-radius: 3px;
            color: #d4d4d4; /* Ensure inline code text is light */
        }}
        a {{
            color: #50c878; /* Medium green for links (was #4fc1ff) */
        }}
        a:hover {{
            color: #77dd77; /* Lighter green on hover (was #80d4ff) */
        }}
        .data-section {{ /* Added for potential future use, kept for consistency */
             margin-top: 30px;
             padding-top: 15px;
             border-top: 1px solid #444;
        }}
        .container {{
            display: flex;
            flex-direction: column; /* Stack charts vertically */
            align-items: center; /* Center charts */
            margin-top: 20px;
        }}
        .chart-container, .wordcloud-container {{ /* Apply common styles */
            border: 1px solid #444; /* Darker border */
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.2); /* Adjusted shadow for dark */
            background-color: #252526; /* Dark background for containers */
            width: 90%; /* Use percentage width for responsiveness */
            box-sizing: border-box;
            /* Added min-height for consistency */
            min-height: 500px;
            display: flex; /* Added flex to center content */
            flex-direction: column; /* Stack title and chart */
            justify-content: center; /* Center vertically */
            align-items: center; /* Center horizontally */
        }}
        .chart-container {{ /* Specific max-width for chart */
             max-width: 800px; /* Adjusted max-width for pie chart */
        }}
        .wordcloud-container img {{ /* Style for the word cloud image */
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto; /* Center the image */
            /* background-color: #fff; */ /* REMOVED - Let image background show */
            /* padding: 10px; */ /* REMOVED - No longer needed */
            border-radius: 5px; /* Slightly round corners */
        }}

        #categoryPieChart {{ /* Style for the pie chart div */
            width: 100%;
            height: 500px; /* Ensure div has height */
         }}

        /* Plotly dark theme adjustments */
        .plotly .plot-container {{
             background-color: #252526 !important;
        }}
         .plotly .xaxislayer-above .xtick text, .plotly .yaxislayer-above .ytick text {{
             fill: #d4d4d4 !important; /* Light tick labels */
         }}
         .plotly .legendtext {{
             fill: #d4d4d4 !important; /* Light legend text */
         }}
         .plotly .annotation-text {{
             fill: #d4d4d4 !important; /* Light annotation text */
         }}
         /* Ensure grid lines are visible but not too bright */
         .plotly .gridlayer .gridline {{
             stroke: #444 !important;
         }}
         /* Ensure axis lines are visible */
         .plotly .zerolinelayer .zeroline {{
             stroke: #666 !important;
         }}
         .plotly .xaxislayer-above .domain, .plotly .yaxislayer-above .domain {{
             stroke: #666 !important; /* Axis line color */
         }}

    </style>
</head>
<body>
    <h1>Analysis Report - {report_date}</h1>

    <div class="container">
        <div class="chart-container">
            <h2>Category Distribution</h2>
            <div id="categoryPieChart"></div>
        </div>

        <div class="wordcloud-container">
            <h2>Topic Word Cloud</h2>
            <!-- Replaced canvas with img tag -->
            <img src="{wordcloud_image_filename}" alt="Topic Word Cloud">
        </div>
    </div>

    <script>
        // --- Donut Chart (Plotly) ---
        try {{
            // Use the new placeholder for pie data
            const pieChartData = {category_pie_data_json};
            const pieTrace = [{{
                labels: pieChartData.labels,
                values: pieChartData.values,
                type: 'pie',
                hole: .4, // Use .4 for donut, 0 for pie
                textinfo: 'percent', // Show percentage on slices
                insidetextorientation: 'radial', // Orient text radially
                marker: {{
                    line: {{ color: '#333', width: 1 }} // Slightly darker line for contrast
                    // Colors will use Plotly's default categorical palette which works well
                }},
                hoverinfo: 'label+percent+value', // Show details on hover
                automargin: true
            }}];

            const pieLayout = {{
                paper_bgcolor: '#252526', // Dark background for the chart paper
                plot_bgcolor: '#252526',  // Dark background for the plot area
                font: {{ color: '#d4d4d4' }}, // Light font color for titles/axes/legend
                showlegend: true,
                legend: {{
                    bgcolor: 'rgba(0,0,0,0)', // Transparent background
                    font: {{ color: '#d4d4d4' }},
                    // Adjust legend position if needed, e.g., x: 1, y: 0.5
                }},
                margin: {{ l: 40, r: 40, t: 40, b: 40 }}, // Adjusted margins, reduced top margin
            }};

            const pieChartConfig = {{ responsive: true }};
            Plotly.newPlot('categoryPieChart', pieTrace, pieLayout, pieChartConfig);

        }} catch (error) {{
            console.error("Error rendering Pie Chart:", error);
            document.getElementById('categoryPieChart').innerText = 'Error rendering Pie Chart.';
        }}

        // --- Removed Word Cloud JavaScript ---

    </script>
</body>
</html>
"""

def generate_html_report(json_data_path: str, output_dir: str) -> str:
    """
    Generates an HTML report with a donut chart and a word cloud image
    from extracted data.

    Args:
        json_data_path: Path to the input JSON data file (_extracted_data.json).
        output_dir: Directory to save the generated HTML report and image.

    Returns:
        The path to the generated HTML file.

    Raises:
        FileNotFoundError: If the JSON data file doesn't exist.
        json.JSONDecodeError: If the JSON file is invalid.
        Exception: For other unexpected errors during processing.
    """
    log.info(f"Starting HTML report generation from: {json_data_path}")

    if not os.path.exists(json_data_path):
        log.error(f"JSON data file not found at {json_data_path}")
        raise FileNotFoundError(f"JSON data file not found at {json_data_path}")

    try:
        with open(json_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"Error decoding JSON from {json_data_path}: {e}")
        raise
    except Exception as e:
        log.error(f"Error reading JSON file {json_data_path}: {e}")
        raise

    categories = data.get("categories", {})
    original_topics = data.get("topics", {}) # Rename original dict

    # --- Deduplicate Topics (Case-Insensitive) ---
    log.info("Deduplicating topics (case-insensitive)...")
    topics = {} # This will hold the merged topics
    for topic, count in original_topics.items():
        normalized_topic = topic.lower() # Normalize to lowercase
        # Use title case for the final key for better readability in the cloud
        final_topic_key = topic.title()
        if normalized_topic in topics:
            # If normalized form exists, add count to the existing entry
            # We need to find the correctly capitalized key already in the dict
            # This assumes the first encountered capitalization is preferred,
            # or we can just use title case consistently. Let's use title case.
            # Remove the old key if it exists with different capitalization
            # This part is tricky if we want to preserve *one* original capitalization.
            # Simpler approach: always use title case as the key.
            existing_key_found = False
            for key in list(topics.keys()): # Iterate over a copy of keys
                 if key.lower() == normalized_topic:
                     topics[key] += count
                     existing_key_found = True
                     break
            if not existing_key_found: # Should not happen if logic is right, but safe fallback
                 topics[final_topic_key] = topics.get(final_topic_key, 0) + count

        else:
            # If normalized form doesn't exist, add it using title case
            topics[final_topic_key] = topics.get(final_topic_key, 0) + count

    if len(original_topics) != len(topics):
        log.info(f"Merged topics: Original count={len(original_topics)}, Merged count={len(topics)}")
    else:
        log.info("No duplicate topics found after case normalization.")


    # --- Generate Filenames ---
    base_filename = os.path.basename(json_data_path)
    date_str_match = re.match(r"(\d{4}-\d{2}-\d{2})", base_filename)
    if date_str_match:
        report_date = date_str_match.group(1)
    else:
        log.warning("Could not extract date from JSON filename, using current date.")
        report_date = datetime.now().strftime('%Y-%m-%d')

    html_filename = f"{report_date}_analysis_report.html"
    html_filepath = os.path.join(output_dir, html_filename)
    wordcloud_image_filename = f"{report_date}_wordcloud.png" # Image filename
    wordcloud_image_filepath = os.path.join(output_dir, wordcloud_image_filename) # Full image path

    log.info(f"HTML report will be saved to: {html_filepath}")
    log.info(f"Word cloud image will be saved to: {wordcloud_image_filepath}")

    # --- Generate Word Cloud Image ---
    if topics:
        try:
            log.info("Generating word cloud image...")
            # Adjust width, height, background_color as needed
            wordcloud = WordCloud(width=1024, height=1024,
                                  mode='RGBA',
                                  background_color=None,
                                  colormap='Set2',
                                  collocations=False # Avoid grouping words like 'New York'
                                  ).generate_from_frequencies(topics)

            # Save the image
            wordcloud.to_file(wordcloud_image_filepath)
            log.info(f"Word cloud image saved successfully.")
        except Exception as e:
            log.exception("Failed to generate or save word cloud image.")
            # Decide how to handle this - maybe skip the image in HTML?
            # For now, we'll continue and the HTML might show a broken image link.
            wordcloud_image_filename = "" # Clear filename so img src is empty
    else:
        # This log message might now trigger if original_topics existed but merged to empty (unlikely)
        log.warning("No topic data found or topics merged to empty, skipping word cloud image generation.")
        wordcloud_image_filename = "" # Clear filename

    # --- Prepare Data for Plotly Donut Chart ---
    sorted_categories = sorted(categories.items(), key=lambda item: item[1], reverse=True)
    category_labels = [item[0] for item in sorted_categories]
    category_values = [item[1] for item in sorted_categories]
    # Create a simple dictionary for pie chart data
    pie_data = {"labels": category_labels, "values": category_values}
    category_pie_data_json = json.dumps(pie_data) # Convert dict to JSON string

    # --- Generate HTML Content ---
    try:
        html_content = HTML_TEMPLATE.format(
            report_date=report_date,
            # Pass the pie chart data JSON to the template
            category_pie_data_json=category_pie_data_json,
            # Pass only the filename for the img src (relative path)
            wordcloud_image_filename=wordcloud_image_filename
        )

        # --- Write to HTML File ---
        os.makedirs(output_dir, exist_ok=True)
        with open(html_filepath, 'w', encoding='utf-8') as html_file:
            html_file.write(html_content)

        log.info(f"Successfully generated HTML report: {html_filepath}")
        return html_filepath

    except Exception as e:
        log.exception(f"An error occurred during HTML report generation: {e}")
        raise