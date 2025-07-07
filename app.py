from flask import Flask, request, send_file, jsonify, render_template_string
import os
import uuid
import subprocess
import shutil
import atexit
import threading
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'aac', 'm4a'}

# Global cleanup tracker
cleanup_jobs = []

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def create_session_folder():
    """Create a unique session folder for file processing"""
    session_id = str(uuid.uuid4())
    session_path = os.path.join(UPLOAD_FOLDER, session_id)
    os.makedirs(session_path, exist_ok=True)
    return session_path, session_id

def cleanup_session_folder(session_path):
    """Remove session folder and all its contents"""
    if os.path.exists(session_path):
        shutil.rmtree(session_path)

@app.route('/')
def hello_world():
    # Read and serve the HTML file
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return '''
        <h1>Video Creator API</h1>
        <p>Use POST /create-video with audio file and images to create a video.</p>
        <p>Send multipart/form-data with:</p>
        <ul>
            <li>audio: MP3/WAV audio file</li>
            <li>images: Multiple image files (JPEG/PNG/WebP)</li>
        </ul>
        '''

@app.route('/create-video', methods=['POST'])
def create_video():
    try:
        # Check if files are present
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        if 'images' not in request.files:
            return jsonify({'error': 'No image files provided'}), 400
        
        audio_file = request.files['audio']
        image_files = request.files.getlist('images')
        
        # Validate audio file
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        if not allowed_file(audio_file.filename, ALLOWED_AUDIO_EXTENSIONS):
            return jsonify({'error': 'Invalid audio file format. Use MP3, WAV, AAC, or M4A'}), 400
        
        # Validate image files
        if len(image_files) == 0:
            return jsonify({'error': 'No image files provided'}), 400
        
        for img in image_files:
            if img.filename == '':
                return jsonify({'error': 'One or more image files are empty'}), 400
            if not allowed_file(img.filename, ALLOWED_IMAGE_EXTENSIONS):
                return jsonify({'error': f'Invalid image file format: {img.filename}. Use JPEG, PNG, or WebP'}), 400
        
        # Create session folder
        session_path, session_id = create_session_folder()
        
        try:
            # Save audio file
            audio_filename = secure_filename(audio_file.filename)
            audio_extension = audio_filename.rsplit('.', 1)[1].lower()
            audio_path = os.path.join(session_path, f'audio.{audio_extension}')
            audio_file.save(audio_path)
            
            # Save and rename images in order
            image_paths = []
            for i, img in enumerate(image_files):
                img_filename = f'img{i:03d}.jpg'
                img_path = os.path.join(session_path, img_filename)
                img.save(img_path)
                image_paths.append(img_path)
            
            # Create video using FFmpeg
            output_video_path = os.path.join(session_path, 'output_video.mp4')
            
            # FFmpeg command to create video from images and audio
            # -framerate 1: 1 frame per second
            # -i img%03d.jpg: input images pattern
            # -i audio: input audio file
            # -c:v libx264: video codec
            # -c:a aac: audio codec
            # -pix_fmt yuv420p: pixel format for compatibility
            # -shortest: end when shortest input ends (audio)
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file
                '-framerate', '1',  # 1 frame per second
                '-i', os.path.join(session_path, 'img%03d.jpg'),  # Input images pattern
                '-i', audio_path,  # Input audio
                '-c:v', 'libx264',  # Video codec
                '-c:a', 'aac',  # Audio codec
                '-pix_fmt', 'yuv420p',  # Pixel format for compatibility
                '-shortest',  # End when audio ends
                output_video_path
            ]
            
            # Run FFmpeg command with timeout to prevent hanging
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                cleanup_session_folder(session_path)
                return jsonify({
                    'error': 'FFmpeg processing failed',
                    'details': result.stderr
                }), 500
            
            # Check if output video was created
            if not os.path.exists(output_video_path):
                cleanup_session_folder(session_path)
                return jsonify({'error': 'Video creation failed - output file not found'}), 500
            
            # Send the video file
            response = send_file(
                output_video_path,
                as_attachment=True,
                download_name=f'video_{session_id}.mp4',
                mimetype='video/mp4'
            )
            
            # Schedule cleanup after response is sent
            def delayed_cleanup():
                time.sleep(5)  # Wait 5 seconds before cleanup
                cleanup_session_folder(session_path)
            
            cleanup_thread = threading.Thread(target=delayed_cleanup, daemon=True)
            cleanup_thread.start()
            
            return response
            
        except Exception as e:
            cleanup_session_folder(session_path)
            return jsonify({'error': f'Processing error: {str(e)}'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Request error: {str(e)}'}), 500

@app.after_request
def cleanup_temp_files(response):
    """Clean up temporary files after request"""
    # Note: This is a simple cleanup. In production, you might want a more sophisticated cleanup strategy
    return response

def periodic_cleanup():
    """Periodically clean up old session folders"""
    while True:
        try:
            # Get current time
            now = time.time()
            
            # Iterate over session folders in the upload directory
            for folder in os.listdir(UPLOAD_FOLDER):
                folder_path = os.path.join(UPLOAD_FOLDER, folder)
                
                # Skip if not a directory
                if not os.path.isdir(folder_path):
                    continue
                
                # Get folder creation time
                folder_creation_time = os.path.getctime(folder_path)
                
                # If folder is older than 1 hour, delete it
                if now - folder_creation_time > 3600:
                    shutil.rmtree(folder_path)
        
        except Exception as e:
            app.logger.error(f'Error during periodic cleanup: {str(e)}')
        
        # Sleep for 10 minutes
        time.sleep(600)

def cleanup_old_files():
    """Background cleanup of old temporary files"""
    while True:
        try:
            if os.path.exists(UPLOAD_FOLDER):
                for session_folder in os.listdir(UPLOAD_FOLDER):
                    session_path = os.path.join(UPLOAD_FOLDER, session_folder)
                    if os.path.isdir(session_path):
                        # Remove folders older than 1 hour
                        if time.time() - os.path.getctime(session_path) > 3600:
                            shutil.rmtree(session_path)
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(300)  # Check every 5 minutes

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    # Create upload directory if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Start periodic cleanup thread
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
