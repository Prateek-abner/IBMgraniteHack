from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import traceback
import uuid
from werkzeug.utils import secure_filename
from granite_client import GraniteClient
from spec_parser import SpecParser
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['GENERATED_TESTS_FOLDER'] = 'generated_tests'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['GENERATED_TESTS_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'json', 'yaml', 'yml'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_test_generation_prompt(api_info):
    endpoints_summary = ""
    for endpoint in api_info['endpoints']:
        params = ", ".join([p.get('name', '') for p in endpoint.get('parameters', [])])
        responses = ", ".join(endpoint.get('responses', {}).keys())
        endpoints_summary += f"""
- {endpoint['method']} {endpoint['path']}
  Summary: {endpoint.get('summary', 'N/A')}
  Parameters: {params if params else 'None'}
  Responses: {responses if responses else 'N/A'}"""
    
    schemas_summary = ""
    for name, schema in api_info.get('schemas', {}).items():
        properties = schema.get('properties', {})
        prop_list = ", ".join([f"{k}: {v.get('type', 'unknown')}" for k, v in properties.items()])
        schemas_summary += f"- {name}: {prop_list}\n"
    
    prompt = f"""You are an expert QA engineer specializing in API testing. Generate comprehensive JUnit 5 test cases for this REST API.

API Information:
- Title: {api_info['title']}
- Version: {api_info['version']}
- Description: {api_info['description']}
- Base URL: {api_info['base_url']}

Endpoints:{endpoints_summary}

Data Models:
{schemas_summary if schemas_summary else 'No schemas defined'}

Requirements:
1. Generate complete JUnit 5 test classes with proper annotations
2. Include positive test cases for valid inputs
3. Include negative test cases for invalid data and error conditions
4. Add boundary value testing for numeric fields
5. Test edge cases (empty strings, null values, special characters)
6. Generate realistic test data matching API schemas
7. Use proper assertions for status codes, headers, and response body
8. Use RestTemplate or TestRestTemplate for API calls
9. Include setup and teardown methods
10. Follow Spring Boot testing best practices

Generate complete, runnable Java test classes:

package com.example.api.test;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
public class {api_info['title'].replace(' ', '')}ApiTest {{

Generate the complete test implementation now:"""
    return prompt

granite_client = GraniteClient()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_tests():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Please upload JSON, YAML, or YML files.'}), 400
        
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            file_content = f.read()
        
        file_extension = filename.rsplit('.', 1)[1].lower()
        api_info = SpecParser.parse_openapi_spec(file_content, file_extension)
        
        prompt = create_test_generation_prompt(api_info)
        generated_tests = granite_client.generate_test_cases(prompt)
        
        if not generated_tests or not generated_tests.strip():
            return jsonify({'error': 'Test generation failed or returned empty result.'}), 500
        
        test_filename = f"{api_info['title'].replace(' ', '_')}_Tests.java"
        test_filepath = os.path.join(app.config['GENERATED_TESTS_FOLDER'], test_filename)
        with open(test_filepath, 'w', encoding='utf-8') as f:
            f.write(generated_tests)
        
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'test_cases': generated_tests,
            'filename': test_filename,
            'api_title': api_info['title'],
            'endpoints_count': len(api_info['endpoints'])
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Failed to generate tests: {str(e)}',
            'details': traceback.format_exc()
        }), 500

@app.route('/download/<filename>')
def download_tests(filename):
    try:
        abs_generated_tests = os.path.abspath(app.config['GENERATED_TESTS_FOLDER'])
        return send_from_directory(abs_generated_tests, filename, as_attachment=True)
    except Exception as e:
        return jsonify({'error': f'File not found: {str(e)}'}), 404

@app.route('/health')
def health_check():
    try:
        test_prompt = "Hello, respond with 'OK' if you can process this request."
        response = granite_client.generate_test_cases(test_prompt)
        return jsonify({
            'status': 'healthy',
            'granite_model': granite_client.model_id,
            'project_id': granite_client.project_id,
            'test_response': response.strip()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/regenerate', methods=['POST'])
def regenerate_tests():
    try:
        data = request.get_json()
        filename = data.get('filename')
        suggestions = data.get('suggestions', '').strip()
        if not filename or not suggestions:
            return jsonify({'error': 'Missing filename or suggestions'}), 400

        test_path = os.path.join(app.config['GENERATED_TESTS_FOLDER'], filename)
        if not os.path.exists(test_path):
            return jsonify({'error': 'Test file not found'}), 404

        with open(test_path, 'r', encoding='utf-8') as f:
            old_test_code = f.read()

        api_title = filename.replace('_Tests.java', '').replace('_', ' ')
        matched_file = None
        for f in os.listdir(app.config['UPLOAD_FOLDER']):
            if api_title.lower().replace(" ", "") in f.lower():
                matched_file = f
                break

        if not matched_file:
            return jsonify({'error': 'Original API file not found for regeneration'}), 404

        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], matched_file)
        with open(upload_path, 'r', encoding='utf-8') as f:
            original_spec_content = f.read()
        file_extension = matched_file.rsplit('.', 1)[1].lower()
        api_info = SpecParser.parse_openapi_spec(original_spec_content, file_extension)
        original_prompt = create_test_generation_prompt(api_info)

        final_prompt = f"""
You are a senior QA automation engineer and Java expert.

Context:
The following JUnit 5 test code was previously generated using the given API specification.

ORIGINAL PROMPT:
{original_prompt}

EXISTING TEST CODE:
{old_test_code}

USER FEEDBACK:
{suggestions}

TASK:
Improve the test code based on user feedback and regenerate the complete updated test class following best practices.
"""

        improved_tests = granite_client.generate_test_cases(final_prompt)

        # Extract code block from markdown response
        if "```java" in improved_tests:
            code_start = improved_tests.find("```java") + len("```java")
            code_end = improved_tests.find("```", code_start)
            if code_end != -1:
                improved_tests = improved_tests[code_start:code_end].strip()
        elif "```" in improved_tests:
            parts = improved_tests.split("```")
            if len(parts) >= 3:
                improved_tests = parts[1].strip()

        with open(test_path, 'w', encoding='utf-8') as f:
            f.write(improved_tests)

        return jsonify({
            'success': True,
            'test_cases': improved_tests,
            'filename': filename,
            'message': 'Test cases regenerated successfully',
            'improvements_applied': suggestions,
            'api_title': api_title
        })
    except Exception as e:
        return jsonify({
            'error': f"Failed to regenerate tests: {str(e)}",
            'details': traceback.format_exc(),
            'success': False
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
