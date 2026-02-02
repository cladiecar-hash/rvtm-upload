import os
import uuid
import base64
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
import requests
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
app.config['UPLOAD_EXTENSIONS'] = ['.xlsx', '.xls']

# n8n webhook URL from environment variable
N8N_WEBHOOK_URL = os.getenv('N8N_WEBHOOK_URL', 'https://your-n8n.com/webhook/rvtm-upload')

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://oxcqxvjibbqcprnhwrcb.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im94Y3F4dmppYmJxY3Bybmh3cmNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE1Njc5NzgsImV4cCI6MjA3NzE0Mzk3OH0.qFp0C6OoJfleu6vTlBAxd37NkpCRLAMuGLiqiGOdSZU')
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Get the app's public URL for callback (Railway sets this)
APP_URL = os.getenv('RAILWAY_PUBLIC_DOMAIN', os.getenv('APP_URL', 'localhost:5000'))
if not APP_URL.startswith('http'):
    APP_URL = f'https://{APP_URL}'

# In-memory job storage (use Redis for production with multiple instances)
jobs = {}


def process_file_async(job_id, filename, file_content, content_type):
    """Process file in background thread"""
    try:
        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['message'] = 'File sent to n8n, processing...'

        # Prepare callback URL for n8n
        callback_url = f"{APP_URL}/callback/{job_id}"

        # Send file to n8n with job_id and callback URL
        files = {'data': (filename, file_content, content_type)}
        data = {
            'job_id': job_id,
            'callback_url': callback_url,
            'filename': filename
        }

        response = requests.post(
            N8N_WEBHOOK_URL,
            files=files,
            data=data,
            timeout=600  # 10 min timeout for n8n
        )

        # If n8n responds immediately (small file or sync mode)
        if response.status_code == 200:
            try:
                n8n_response = response.json()
                # Check if n8n returned final result or just acknowledgment
                if n8n_response.get('status') == 'processing':
                    # n8n will call back later
                    jobs[job_id]['message'] = 'n8n is processing the file...'
                else:
                    # n8n returned final result
                    jobs[job_id]['status'] = 'completed'
                    jobs[job_id]['result'] = n8n_response
                    jobs[job_id]['message'] = 'Analysis completed'
            except:
                jobs[job_id]['status'] = 'completed'
                jobs[job_id]['result'] = {'raw_response': response.text}
                jobs[job_id]['message'] = 'Analysis completed'
        else:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['message'] = f'n8n returned status {response.status_code}'

    except requests.exceptions.Timeout:
        # Timeout doesn't mean failure - n8n might still be processing
        jobs[job_id]['message'] = 'Processing is taking longer than expected. Still waiting for n8n...'
    except requests.exceptions.RequestException as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['message'] = f'Failed to connect to n8n: {str(e)}'


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

    # Generate unique job ID
    job_id = str(uuid.uuid4())

    # Read file content before returning (stream can only be read once)
    file_content = file.read()
    content_type = file.content_type

    # Initialize job status
    jobs[job_id] = {
        'status': 'queued',
        'message': 'File received, sending to n8n...',
        'filename': filename,
        'created_at': datetime.utcnow().isoformat(),
        'result': None
    }

    # Process file in background thread
    thread = threading.Thread(
        target=process_file_async,
        args=(job_id, filename, file_content, content_type)
    )
    thread.start()

    # Return immediately with job_id
    return jsonify({
        'status': 'accepted',
        'message': 'File upload accepted, processing started',
        'job_id': job_id
    }), 202


@app.route('/status/<job_id>')
def get_status(job_id):
    """Polling endpoint - frontend calls this every few seconds"""
    if job_id not in jobs:
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404

    job = jobs[job_id]
    response = {
        'status': job['status'],
        'message': job['message'],
        'filename': job['filename']
    }

    # Include result if completed
    if job['status'] == 'completed' and job['result']:
        result = job['result']
        # Don't send base64 data in status response (too large)
        response['result'] = {
            k: v for k, v in result.items()
            if k != 'file_base64'
        }
        # Add download URL if file is available
        if result.get('file_base64'):
            response['download_url'] = f'/download/{job_id}'
            response['file_name'] = result.get('file_name', 'analysis_results.xlsx')

    return jsonify(response)


@app.route('/download/<job_id>')
def download_file(job_id):
    """Download the result file"""
    if job_id not in jobs:
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404

    job = jobs[job_id]

    if job['status'] != 'completed' or not job.get('result'):
        return jsonify({'status': 'error', 'message': 'Job not completed yet'}), 400

    result = job['result']

    if not result.get('file_base64'):
        return jsonify({'status': 'error', 'message': 'No file available'}), 404

    # Decode base64 file
    try:
        file_data = base64.b64decode(result['file_base64'])
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to decode file: {str(e)}'}), 500

    file_name = result.get('file_name', 'analysis_results.xlsx')
    mime_type = result.get('mime_type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    return Response(
        file_data,
        mimetype=mime_type,
        headers={
            'Content-Disposition': f'attachment; filename="{file_name}"',
            'Content-Length': len(file_data)
        }
    )


@app.route('/callback/<job_id>', methods=['POST'])
def callback(job_id):
    """n8n calls this endpoint when processing is complete"""
    if job_id not in jobs:
        return jsonify({'status': 'error', 'message': 'Job not found'}), 404

    # Get result from n8n
    try:
        result = request.json
    except:
        result = {'raw': request.data.decode('utf-8', errors='ignore')}

    # Update job status
    jobs[job_id]['status'] = 'completed'
    jobs[job_id]['message'] = 'Analysis completed'
    jobs[job_id]['result'] = result
    jobs[job_id]['completed_at'] = datetime.utcnow().isoformat()

    return jsonify({'status': 'success', 'message': 'Callback received'})


@app.route('/api/progress/<job_id>')
def get_progress(job_id):
    """Get job progress from Supabase database"""
    try:
        response = supabase.table('job_progress') \
            .select('*') \
            .eq('job_id', job_id) \
            .single() \
            .execute()

        if response.data:
            data = response.data
            return jsonify({
                'status': data.get('status', 'pending'),
                'current_batch': data.get('current_batch', 0),
                'total_batches': data.get('total_batches', 0),
                'processed_requirements': data.get('processed_requirements', 0),
                'total_requirements': data.get('total_requirements', 0),
                'percent_complete': data.get('percent_complete', 0),
                'updated_at': data.get('updated_at'),
                'error_message': data.get('error_message')
            })
        return jsonify({'status': 'not_found', 'message': 'Job not found in database'}), 404

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'webhook_configured': bool(N8N_WEBHOOK_URL),
        'supabase_configured': bool(SUPABASE_URL and SUPABASE_KEY),
        'active_jobs': len([j for j in jobs.values() if j['status'] == 'processing'])
    })


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'false').lower() == 'true')
