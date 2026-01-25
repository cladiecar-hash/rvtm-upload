# RVTM INCOSE Analyzer - Web Upload

Web application for uploading RVTM Excel files to n8n for INCOSE GtWR v4 Gap Analysis.

![Upload Interface](https://img.shields.io/badge/Flask-3.0-blue) ![Railway](https://img.shields.io/badge/Deploy-Railway-purple)

## Features

- 🖱️ Drag & Drop file upload
- 📊 Excel file validation (.xlsx, .xls)
- 🔄 Progress bar during upload
- 📈 Display analysis stats from n8n
- 🎨 Modern dark UI with Tailwind CSS

## Quick Deploy to Railway

### 1. Create GitHub Repository

```bash
# Clone or create new repo
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/rvtm-upload.git
git push -u origin main
```

### 2. Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Railway auto-detects Python and deploys

### 3. Configure Environment Variables

In Railway dashboard → Your Project → Variables:

| Variable | Value |
|----------|-------|
| `N8N_WEBHOOK_URL` | `https://stc-project.app.n8n.cloud/webhook/rvtm-upload` |

### 4. Get Your URL

Railway provides a URL like: `https://rvtm-upload-production.up.railway.app`

## Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your n8n webhook URL

# Run
python app.py
```

Open http://localhost:5000

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Upload interface |
| `/upload` | POST | Upload Excel file (multipart/form-data) |
| `/health` | GET | Health check |

## n8n Workflow

Make sure your n8n workflow has:
1. **Webhook node** listening on `/webhook/rvtm-upload`
2. **Binary data** enabled to receive files
3. **Respond to Webhook** node returning JSON stats

## Tech Stack

- **Backend**: Flask + Gunicorn
- **Frontend**: Tailwind CSS + Vanilla JS
- **Hosting**: Railway
- **Workflow**: n8n

## License

MIT
