import os
from flask import Flask, render_template, request, jsonify
import requests
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
app.config['UPLOAD_EXTENSIONS'] = ['.xlsx', '.xls']

# n8n webhook URL from environment variable
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'https://your-n8n.com/webhook/rvtm-upload')


@app.route('/')
def index():
    return render_template('index.html', webhook_url=N8N_WEBHOOK_URL)


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected'}), 400
    
    # Check file extension
    filename = secure_filename(file.filename)
    file_ext = os.path.splitext(filename)[1].lower()
    
    if file_ext not in app.config['UPLOAD_EXTENSIONS']:
        return jsonify({
            'status': 'error', 
            'message': f'Invalid file type. Allowed: {", ".join(app.config["UPLOAD_EXTENSIONS"])}'
        }), 400
    
    try:
        # Forward file to n8n webhook
        files = {'data': (filename, file.stream, file.content_type)}
        response = requests.post(N8N_WEBHOOK_URL, files=files, timeout=120)
        
        # Return n8n response
        try:
            n8n_response = response.json()
        except:
            n8n_response = {'raw_response': response.text}
        
        return jsonify({
            'status': 'success' if response.status_code == 200 else 'error',
            'message': 'File sent to n8n successfully' if response.status_code == 200 else 'n8n returned an error',
            'n8n_status_code': response.status_code,
            'n8n_response': n8n_response
        }), response.status_code
        
    except requests.exceptions.Timeout:
        return jsonify({
            'status': 'error',
            'message': 'Request to n8n timed out. The file may still be processing.'
        }), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to connect to n8n: {str(e)}'
        }), 502


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'webhook_configured': bool(N8N_WEBHOOK_URL)})


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'false').lower() == 'true')
