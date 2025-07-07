# FFmpeg Video Server

A Flask-based API server that creates videos from audio and image files using FFmpeg.

## Features

- Upload audio files (MP3, WAV, AAC, M4A)
- Upload multiple image files (JPEG, PNG, WebP)
- Automatically creates video slideshow with audio
- Cleanup of temporary files
- Ready for deployment on Render

## API Endpoints

### GET /
Returns API documentation

### POST /create-video
Creates a video from uploaded audio and images.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body:
  - `audio`: Audio file (MP3, WAV, AAC, M4A)
  - `images`: Multiple image files (JPEG, PNG, WebP)

**Response:**
- Returns the created video file as MP4

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install FFmpeg on your system

3. Run the server:
```bash
python main.py
```

## Deployment on Render

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Use the following settings:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn main:app`
   - **Plan**: Free

The server will automatically install FFmpeg during deployment.

## File Structure

- `main.py` - Main Flask application
- `requirements.txt` - Python dependencies
- `Procfile` - Process file for deployment
- `render.yaml` - Render configuration
- `index.html` - Test interface
