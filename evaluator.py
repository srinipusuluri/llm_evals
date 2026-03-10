import json
import openai
import streamlit as st
from typing import List, Dict, Any
import time
import subprocess
import os

class Evaluator:
    def __init__(self, api_key: str):
        import httpx
        # Create a custom httpx client without proxies
        http_client = httpx.Client(
            timeout=httpx.Timeout(60.0),
        )
        self.client = openai.OpenAI(api_key=api_key, http_client=http_client)
        
    def evaluate_response(self, prompt: str, response: str, expected_answer: str) -> Dict[str, Any]:
        """Evaluate a response using OpenAI as the judge"""
        try:
            completion = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert evaluator. Rate responses on a scale of 1-10 based on accuracy, completeness, and relevance to the prompt. Provide a score and brief justification."
                    },
                    {
                        "role": "user",
                        "content": f"""Prompt: {prompt}

Expected Answer Guidelines: {expected_answer}

Response to Evaluate: {response}

Please provide:
1. A score from 1-10
2. A brief justification for the score"""
                    }
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            evaluation_text = completion.choices[0].message.content
            score = self.extract_score(evaluation_text)
            
            return {
                "score": score,
                "evaluation": evaluation_text,
                "response": response
            }
            
        except Exception as e:
            return {
                "score": 0,
                "evaluation": f"Error evaluating response: {str(e)}",
                "response": response
            }
    
    def extract_score(self, evaluation_text: str) -> int:
        """Extract numerical score from evaluation text"""
        import re
        # Look for patterns like "Score: 8" or "8/10" or just "8"
        score_patterns = [
            r'Score:\s*(\d+)',
            r'(\d+)\s*/\s*10',
            r'(\d+)\s*/10',
            r'(\d+)\s*out of 10',
            r'(\d+)\s+out of ten'
        ]
        
        for pattern in score_patterns:
            match = re.search(pattern, evaluation_text, re.IGNORECASE)
            if match:
                score = int(match.group(1))
                return max(1, min(10, score))  # Ensure score is between 1-10
        
        # If no pattern matches, try to find any number between 1-10
        numbers = re.findall(r'\b([1-9]|10)\b', evaluation_text)
        if numbers:
            return int(numbers[0])
        
        return 5  # Default score if no clear score found

def load_prompts(file_path: str) -> List[Dict[str, str]]:
    """Load evaluation prompts from JSON file"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            # Flatten the nested structure into a list
            prompts_list = []
            for category in data.get('evaluation_categories', []):
                prompt = {
                    'id': category['name'],
                    'prompt': category['example_prompt'],
                    'expected_answer': category['description']
                }
                prompts_list.append(prompt)
            return prompts_list
    except FileNotFoundError:
        st.error(f"Prompts file not found: {file_path}")
        return []
    except json.JSONDecodeError as e:
        st.error(f"Error parsing JSON file: {e}")
        return []

def get_ollama_models():
    """Get list of available Ollama models sorted by modification time"""
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        models = []
        for line in lines:
            if line.strip():
                parts = line.split()
                if len(parts) >= 1:
                    models.append(parts[0])
        
        # Sort models by modification time (newest first)
        # We'll use the modification time from the list output if available
        # or sort alphabetically as a fallback
        if models:
            # Try to get modification times
            model_times = []
            for model in models:
                try:
                    # Get model info to check modification time
                    info_result = subprocess.run(['ollama', 'show', model, '--modelfile'], 
                                               capture_output=True, text=True, check=True)
                    # If successful, assume it's a valid model
                    model_times.append((model, time.time()))  # Use current time as approximation
                except:
                    model_times.append((model, 0))
            
            # Sort by time (newest first)
            model_times.sort(key=lambda x: x[1], reverse=True)
            return [model for model, _ in model_times]
        
        return models
    except subprocess.CalledProcessError:
        return []

def run_ollama_prompt(model_name: str, prompt: str) -> tuple:
    """Run a prompt with Ollama model and return response and execution time"""
    try:
        start_time = time.time()
        result = subprocess.run(
            ['ollama', 'run', model_name, prompt],
            capture_output=True,
            text=True,
            timeout=120  # Increased timeout for multiple models
        )
        end_time = time.time()
        execution_time = end_time - start_time
        return result.stdout.strip(), execution_time
    except subprocess.TimeoutExpired:
        return "Error: Model response timed out", 120.0
    except Exception as e:
        return f"Error running model: {str(e)}", 0.0

def main():
    st.set_page_config(page_title="LLM Response Evaluator", layout="wide")
    st.title("🤖 LLM Response Evaluator")
    st.markdown("Compare responses from different prompts and get AI-powered evaluations")
    
    # Sidebar for configuration
    st.sidebar.header("Configuration")
    api_key = st.sidebar.text_input("OpenAI API Key", type="password", value="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")
    
    if not api_key:
        st.warning("Please enter your OpenAI API key in the sidebar.")
        return
    
    # Get available Ollama models
    ollama_models = get_ollama_models()
    
    if not ollama_models:
        st.warning("No Ollama models found. Please install and run Ollama with some models.")
        return
    
    selected_models = st.sidebar.multiselect("Select Ollama Models", ollama_models, default=ollama_models[:1])
    if not selected_models:
        st.warning("Please select at least one model.")
        return
    st.sidebar.write(f"Selected models: **{', '.join(selected_models)}**")
    
    # Initialize evaluator
    evaluator = Evaluator(api_key)
    
    # Load prompts
    prompts = load_prompts("eval_prompts.json")
    
    if not prompts:
        st.error("No prompts loaded. Please check the eval_prompts.json file.")
        return
    
    # Main content
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.header("Select Prompts")
        selected_indices = st.multiselect(
            "Choose prompts to evaluate",
            options=range(len(prompts)),
            format_func=lambda x: f"Prompt {prompts[x]['id']}: {prompts[x]['prompt'][:50]}..."
        )
        
        st.header("Model Responses")
        if st.button("Run Selected Prompts with Ollama"):
            if not selected_indices:
                st.warning("Please select at least one prompt.")
            else:
                with st.spinner("Running prompts with Ollama models..."):
                    # Run prompts for all selected models
                    all_model_results = {}
                    for model in selected_models:
                        model_responses = {}
                        model_times = {}
                        for i in selected_indices:
                            prompt = prompts[i]['prompt']
                            response, exec_time = run_ollama_prompt(model, prompt)
                            model_responses[i] = response
                            model_times[i] = exec_time
                        
                        all_model_results[model] = {
                            'responses': model_responses,
                            'times': model_times
                        }
                    
                    # Store all results in session state
                    st.session_state['all_model_results'] = all_model_results
                    st.success("Prompts executed successfully!")
        
        # Display Ollama responses if available
        if 'all_model_results' in st.session_state:
            st.subheader("Ollama Model Responses")
            all_model_results = st.session_state['all_model_results']
            
            for model in selected_models:
                if model in all_model_results:
                    with st.expander(f"Model: {model}"):
                        st.write(f"**Model:** {model}")
                        for i in selected_indices:
                            if i in all_model_results[model]['responses']:
                                with st.container():
                                    st.write(f"**Prompt {prompts[i]['id']}:**")
                                    st.write(prompts[i]['prompt'])
                                    st.write(f"**Response:**")
                                    st.text_area("", all_model_results[model]['responses'][i], height=150, key=f"{model}_resp_{i}")
                                    st.write(f"**Execution Time:** {all_model_results[model]['times'][i]:.2f} seconds")
    
    with col2:
        st.header("Evaluation Results")
        
        if st.button("Evaluate Ollama Responses"):
            if not selected_indices:
                st.warning("Please select at least one prompt.")
            elif 'all_model_results' not in st.session_state:
                st.warning("Please run the prompts with Ollama first.")
            else:
                with st.spinner("Evaluating Ollama responses..."):
                    all_results = []
                    execution_times = {}
                    
                    # Evaluate responses for all models
                    all_model_results = st.session_state['all_model_results']
                    for model in selected_models:
                        if model in all_model_results:
                            model_results = []
                            model_times = []
                            for i in selected_indices:
                                if i in all_model_results[model]['responses']:
                                    prompt = prompts[i]['prompt']
                                    response = all_model_results[model]['responses'][i]
                                    expected = prompts[i].get('expected_answer', '')
                                    
                                    evaluation = evaluator.evaluate_response(prompt, response, expected)
                                    model_results.append({
                                        'prompt_id': prompts[i]['id'],
                                        'prompt': prompt,
                                        'model': model,
                                        'score': evaluation['score'],
                                        'evaluation': evaluation['evaluation'],
                                        'response': response
                                    })
                                    model_times.append(all_model_results[model]['times'][i])
                            
                            all_results.extend(model_results)
                            execution_times[model] = model_times
                    
                    # Display execution time comparison
                    st.subheader("Execution Time Comparison")
                    if execution_times:
                        # Create execution time chart
                        import pandas as pd
                        time_data = {}
                        for model, times in execution_times.items():
                            time_data[model] = times
                        
                        # Average execution times
                        avg_times = {model: sum(times)/len(times) for model, times in time_data.items()}
                        st.bar_chart(avg_times)
                    
                    # Display results
                    st.subheader("Model Performance Summary")
                    if all_results:
                        # Group by model and prompt for comparison
                        import pandas as pd
                        df = pd.DataFrame(all_results)
                        
                        # Create pivot table for comparison
                        pivot_df = df.pivot(index='prompt_id', columns='model', values='score')
                        st.dataframe(pivot_df)
                        
                        # Calculate metrics per model
                        st.subheader("Model Metrics")
                        for model in selected_models:
                            model_scores = [r['score'] for r in all_results if r['model'] == model]
                            if model_scores:
                                avg_score = sum(model_scores) / len(model_scores)
                                st.metric(f"Average Score - {model}", f"{avg_score:.1f}/10")
                    
                    st.subheader("Detailed Results")
                    for result in all_results:
                        with st.expander(f"Prompt {result['prompt_id']} - {result['model']} - Score: {result['score']}/10"):
                            st.write("**Model:**", result['model'])
                            st.write("**Prompt:**")
                            st.write(result['prompt'])
                            st.write("**Model Response:**")
                            st.text_area("", result['response'], height=150, key=f"{result['model']}_resp_{result['prompt_id']}")
                            st.write("**Evaluation:**")
                            st.write(result['evaluation'])
                    
                    # Add export functionality
                    if st.button("Export Results to HTML"):
                        from datetime import datetime
                        filename = f"evaluation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                        filepath = save_results_to_html(all_results, execution_times, filename)
                        st.success(f"Results exported to {filepath}")

def save_results_to_html(results, execution_times, filename):
    """Save evaluation results to an HTML file"""
    import pandas as pd
    from datetime import datetime
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>LLM Evaluation Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            h1 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .metric {{ font-size: 18px; margin: 10px 0; }}
            .chart-container {{ margin: 20px 0; }}
        </style>
    </head>
    <body>
        <h1>LLM Response Evaluation Results</h1>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h2>Model Performance Summary</h2>
        <div class="chart-container">
            <h3>Execution Times (Average)</h3>
    """
    
    # Add execution time chart
    if execution_times:
        for model, times in execution_times.items():
            avg_time = sum(times) / len(times)
            html_content += f"<p class='metric'><strong>{model}:</strong> {avg_time:.2f} seconds</p>"
    
    html_content += """
        </div>
        
        <h2>Detailed Results</h2>
        <table>
            <tr>
                <th>Prompt ID</th>
                <th>Model</th>
                <th>Score</th>
                <th>Prompt</th>
                <th>Response</th>
                <th>Evaluation</th>
            </tr>
    """
    
    # Add detailed results
    for result in results:
        html_content += f"""
            <tr>
                <td>{result['prompt_id']}</td>
                <td>{result['model']}</td>
                <td>{result['score']}/10</td>
                <td>{result['prompt']}</td>
                <td>{result['response'][:200]}...</td>
                <td>{result['evaluation'][:200]}...</td>
            </tr>
        """
    
    html_content += """
        </table>
    </body>
    </html>
    """
    
    # Save to docs folder with timestamp
    docs_dir = "docs"
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
    
    filepath = os.path.join(docs_dir, filename)
    with open(filepath, 'w') as f:
        f.write(html_content)
    
    return filepath

if __name__ == "__main__":
    main()
