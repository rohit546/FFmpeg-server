from flask import Flask, request, send_file, jsonify
import os
import uuid
import subprocess
import shutil
import re
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)

UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'aac', 'm4a'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def create_session_folder():
    session_id = str(uuid.uuid4())
    session_path = os.path.join(UPLOAD_FOLDER, session_id)
    os.makedirs(session_path, exist_ok=True)
    return session_path, session_id

def cleanup_session_folder(session_path):
    if os.path.exists(session_path):
        shutil.rmtree(session_path)
        print(f"🗑️ Cleaned up: {session_path}")

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

def get_audio_duration(audio_path):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
        ], capture_output=True, text=True)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    return 60.0  # fallback

def create_subtitles_from_text(text, audio_duration, output_srt_path):
    try:
        if not text or not text.strip():
            print("❌ Empty subtitle text")
            return False

        # Split text into sentences using punctuation
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            print("❌ No valid sentences")
            return False

        segment_duration = audio_duration / len(sentences)

        with open(output_srt_path, 'w', encoding='utf-8') as f:
            for i, sentence in enumerate(sentences):
                start_time = i * segment_duration
                end_time = (i + 1) * segment_duration
                f.write(f"{i + 1}\n")
                f.write(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}\n")
                f.write(f"{sentence}\n\n")

        print("✅ Subtitles created at:", output_srt_path)
        return True
    except Exception as e:
        print(f"Subtitle creation error: {e}")
        return False

@app.route('/')
def hello():
    return '''
    <h1>🎬 Video Creator with Subtitles</h1>
    <p>POST to /create-video with:</p>
    <ul>
        <li><b>audio</b>: .mp3/.wav file</li>
        <li><b>images</b>: multiple .jpg/.png/.webp files</li>
        <li><b>subtitle_text</b>: (optional) plain text</li>
    </ul>
    '''

@app.route('/create-video', methods=['POST'])
def create_video():
    session_path = None
    try:
        if 'audio' not in request.files or 'images' not in request.files:
            return jsonify({'error': 'Missing audio or images'}), 400

        audio_file = request.files['audio']
        image_files = request.files.getlist('images')
        subtitle_text = request.form.get('subtitle_text', '').strip()

        if audio_file.filename == '' or not allowed_file(audio_file.filename, ALLOWED_AUDIO_EXTENSIONS):
            return jsonify({'error': 'Invalid or missing audio file'}), 400

        if not image_files or any(img.filename == '' or not allowed_file(img.filename, ALLOWED_IMAGE_EXTENSIONS) for img in image_files):
            return jsonify({'error': 'Invalid or missing image files'}), 400

        session_path, session_id = create_session_folder()

        try:
            # Save audio
            audio_path = os.path.join(session_path, 'audio.' + audio_file.filename.rsplit('.', 1)[1].lower())
            audio_file.save(audio_path)

            # Convert and save all images to JPG format
            for i, img_file in enumerate(image_files):
                img = Image.open(img_file)
                rgb_img = img.convert('RGB')  # Ensures compatibility with JPG
                rgb_img.save(os.path.join(session_path, f'img{i:03d}.jpg'), format='JPEG')

            # Get duration
            audio_duration = get_audio_duration(audio_path)

            # Subtitle processing
            subtitle_success = False
            srt_path = os.path.abspath(os.path.join(session_path, 'subtitles.srt'))

            if subtitle_text:
                subtitle_success = create_subtitles_from_text(subtitle_text, audio_duration, srt_path)

            # FFmpeg build
            framerate = len(image_files) / audio_duration
            output_path = os.path.join(session_path, 'video.mp4')
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-framerate', str(framerate), '-i',
                os.path.join(session_path, 'img%03d.jpg'), '-i', audio_path,
                '-c:v', 'libx264', '-c:a', 'aac', '-pix_fmt', 'yuv420p', '-shortest'
            ]

            if subtitle_success:
                ffmpeg_cmd += ['-vf', f"subtitles='{srt_path.replace(os.sep, '/')}'"]
                print("✅ Subtitles will be embedded")

            ffmpeg_cmd.append(output_path)

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            print("FFmpeg stderr:\n", result.stderr)

            if result.returncode != 0 or not os.path.exists(output_path):
                return jsonify({
                    'error': 'FFmpeg failed',
                    'stderr': result.stderr
                }), 500

            # Read the video file into memory before cleanup
            with open(output_path, 'rb') as f:
                video_data = f.read()

            # Clean up temp files immediately after reading video
            cleanup_session_folder(session_path)
            session_path = None  # Mark as cleaned

            # Return video from memory
            from io import BytesIO
            video_buffer = BytesIO(video_data)
            video_buffer.seek(0)

            return send_file(
                video_buffer,
                as_attachment=True,
                download_name=f'video_{session_id}.mp4',
                mimetype='video/mp4'
            )

        except Exception as e:
            import traceback
            return jsonify({
                'error': f'Processing error: {e}',
                'traceback': traceback.format_exc()
            }), 500

    except Exception as e:
        import traceback
        return jsonify({
            'error': f'Request failed: {e}',
            'traceback': traceback.format_exc()
        }), 500

    finally:
        # Ensure cleanup happens no matter what
        if session_path and os.path.exists(session_path):
            cleanup_session_folder(session_path)

if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(host="0.0.0.0", port=8080, debug=True)
