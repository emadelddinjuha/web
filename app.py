"""
YouTube Karaoke Generator - Flask Web Application
==================================================
Replicates desktop_app.py functionality as a web app

Phase 1: Download → Cut → Extract German SRT → [EDIT GERMAN SRT]
Phase 2: Translate to Arabic → [EDIT ARABIC SRT] → Create ASS → Produce Video

Web UI using Flask with Bootstrap 5
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, send_from_directory
import subprocess
import os
import sys
from datetime import datetime
import threading
import json
from srt import parse as srt_parse
from deep_translator import GoogleTranslator
import pysubs2

app = Flask(__name__)
app.secret_key = 'youtube_karaoke_secret_key'

# ================= إعدادات =================
class Settings:
    YOUTUBE_URL = "https://www.youtube.com/watch?v=6E_161JvL2Q"
    START_TIME = "00:01:30"
    END_TIME = "00:02:30"
    
    VIDEO_NAME = "video.mp4"
    CUT_VIDEO = "cut.mp4"
    AUDIO_WAV = "cut_audio.wav"
    SUBS_SRT_DE = "cut_de.srt"
    SUBS_SRT_AR = "cut_ar.srt"
    SUBS_ASS = "cut_ass.ass"
    FINAL_VIDEO = "final_video.mp4"
    
    YTDLP_PATH = ["python3", "-m", "yt_dlp"]   # يجب تثبيت yt-dlp في البيئة
    FFMPEG = "ffmpeg"      # يجب أن يكون ffmpeg مثبتاً
    WHISPER = "python3 -m whisper"  # افترض أن whisper مثبت


# ================= Application State =================
class AppState:
    def __init__(self):
        self.step_status = [''] * 8
        self.german_srt_content = ""
        self.arabic_srt_content = ""
        self.is_processing = False
        self.logs = []
    
    def reset(self):
        self.step_status = [''] * 8
        self.german_srt_content = ""
        self.arabic_srt_content = ""
        self.is_processing = False
        self.logs = []

app_state = AppState()

# ================= Routes =================

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html', settings=Settings, step_status=app_state.step_status)

@app.route('/api/status')
def get_status():
    """Get current status"""
    return jsonify({
        'step_status': app_state.step_status,
        'is_processing': app_state.is_processing,
        'files': get_files_info(),
        'logs': app_state.logs[-50:]  # Last 50 log entries
    })

@app.route('/api/refresh')
def refresh_data():
    """Refresh all data"""
    return jsonify({
        'step_status': app_state.step_status,
        'is_processing': app_state.is_processing,
        'files': get_files_info(),
        'german_content': get_file_content(Settings.SUBS_SRT_DE),
        'arabic_content': get_file_content(Settings.SUBS_SRT_AR)
    })

# ================= Step Execution =================

@app.route('/api/step/<int:step_num>', methods=['POST'])
def run_step(step_num):
    """Run a single step"""
    if app_state.is_processing:
        return jsonify({'error': 'Processing already in progress'})
    
    data = request.json or {}
    url = data.get('url', Settings.YOUTUBE_URL)
    start_time = data.get('start_time', Settings.START_TIME)
    end_time = data.get('end_time', Settings.END_TIME)
    
    # Log received parameters for debugging
    log(f"API received - URL: {url}")
    log(f"API received - Time: {start_time} --> {end_time}")
    
    app_state.is_processing = True
    thread = threading.Thread(target=_run_step_thread, args=(step_num, url, start_time, end_time))
    thread.start()
    
    return jsonify({'message': f'Step {step_num + 1} started'})

def _run_step_thread(step_num, url, start_time, end_time):
    """Thread function for running steps"""
    try:
        log(f"Starting step {step_num + 1}...")
        log(f"URL: {url}")
        log(f"Time: {start_time} --> {end_time}")
        if step_num == 0:
            _step_download(url)
        elif step_num == 1:
            _step_cut(start_time, end_time)
        elif step_num == 2:
            _step_extract_german()
        elif step_num == 4:
            _step_translate()
        elif step_num == 6:
            _step_create_ass()
        elif step_num == 7:
            _step_produce_video()
        else:
            log(f"Unknown step: {step_num}")
    except Exception as e:
        log(f"Error in step {step_num + 1}: {str(e)}")
        # Reset step status on error
        if step_num < len(app_state.step_status):
            app_state.step_status[step_num] = '✗'
    finally:
        app_state.is_processing = False
        log("Processing finished")

# ================= Step Functions =================

def log(message):
    """Add log message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    app_state.logs.append(log_entry)
    print(f"[WEB] {message}")
    sys.stdout.flush()

def _step_download(url):
    """Download video from YouTube"""
    log(f"Starting download with URL: {url}")
    app_state.step_status[0] = '⏳'
    
    # Check if URL is different from default
    if url != Settings.YOUTUBE_URL:
        log(f"Using custom URL (different from default)")
    
    if os.path.exists(Settings.VIDEO_NAME):
        # Check if we should re-download with different URL
        log(f"Video already exists: {Settings.VIDEO_NAME}")
        log("Delete the file if you want to re-download with a new URL")
        app_state.step_status[0] = '✓'
        return
    
    result = subprocess.run(
        Settings.YTDLP_PATH+[
        "--cookies-from-browser", "chrome",
        "-f", "bv*[height<=1080]+ba/best",
        "--merge-output-format", "mp4",
        "-o", Settings.VIDEO_NAME,
        url
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # Print output
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            if line:
                log(f"yt-dlp: {line}")
    
    if result.returncode != 0:
        log(f"Download failed with code: {result.returncode}")
        app_state.step_status[0] = '✗'
        return
    
    log("Download complete")
    app_state.step_status[0] = '✓'


def _parse_time_to_seconds(time_str):
    """
    Parse time string to seconds.
    Supports formats: "HH:MM:SS", "MM:SS", or just seconds as integer string.
    """
    try:
        # Try parsing as HH:MM:SS or MM:SS
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) == 3:
                # HH:MM:SS format
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                # MM:SS format
                minutes = int(parts[0])
                seconds = int(parts[1])
                return minutes * 60 + seconds
        else:
            # Just seconds
            return int(time_str)
    except (ValueError, IndexError) as e:
        log(f"Error parsing time '{time_str}': {e}")
        return None


def _step_cut(start_time, end_time):
    """Cut video to selected segment"""
    log(f"Cutting video from '{start_time}' to '{end_time}'...")
    app_state.step_status[1] = '⏳'
    
    # Validate source video exists
    if not os.path.exists(Settings.VIDEO_NAME):
        log(f"Error: Source video not found: {Settings.VIDEO_NAME}")
        log("Please run Step 1 (Download) first!")
        app_state.step_status[1] = '✗'
        return
    
    # Parse times to seconds for validation and duration calculation
    start_seconds = _parse_time_to_seconds(start_time)
    end_seconds = _parse_time_to_seconds(end_time)
    
    if start_seconds is None:
        log(f"Error: Invalid start time format: '{start_time}'")
        log("Supported formats: HH:MM:SS, MM:SS, or seconds")
        app_state.step_status[1] = '✗'
        return
    
    if end_seconds is None:
        log(f"Error: Invalid end time format: '{end_time}'")
        log("Supported formats: HH:MM:SS, MM:SS, or seconds")
        app_state.step_status[1] = '✗'
        return
    
    # Validate end time is after start time
    if end_seconds <= start_seconds:
        log(f"Error: End time ({end_time} = {end_seconds}s) must be after start time ({start_time} = {start_seconds}s)")
        app_state.step_status[1] = '✗'
        return
    
    # Calculate duration
    duration = end_seconds - start_seconds
    log(f"Cut duration: {duration} seconds ({start_seconds}s -> {end_seconds}s)")
    
    # Check for existing cut video
    if os.path.exists(Settings.CUT_VIDEO):
        existing_size = os.path.getsize(Settings.CUT_VIDEO) / (1024 * 1024)
        log(f"Cut video already exists: {Settings.CUT_VIDEO} ({existing_size:.2f} MB)")
        log("Delete the file if you want to re-cut with new times")
        app_state.step_status[1] = '✓'
        return
    
    # Build FFmpeg command with both -t (duration) and -to (end time) for reliability
    ffmpeg_cmd = [
        Settings.FFMPEG, "-y",
        "-i", Settings.VIDEO_NAME,
        "-ss", str(start_seconds),  # Start time in seconds
        "-t", str(duration),        # Duration (more reliable than -to)
        "-to", str(end_seconds),    # End time (as backup)
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-movflags", "+faststart",
        Settings.CUT_VIDEO
    ]
    
    log(f"Running FFmpeg with duration {duration}s...")
    
    result = subprocess.run(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300  # 5 minute timeout
    )
    
    # Log FFmpeg output (filter out verbose lines)
    if result.stdout:
        output_lines = result.stdout.strip().split('\n')
        important_lines = [line for line in output_lines if any(keyword in line.lower() for keyword in 
            ['error', 'warning', 'duration', 'stream', 'frame', 'video', 'audio', 'bitrate', 'size', 'time=', 'fps'])]
        for line in important_lines[:10]:  # Limit to first 10 important lines
            if line:
                log(f"ffmpeg: {line}")
    
    if result.returncode != 0:
        log(f"FFmpeg cut failed with code: {result.returncode}")
        log(f"FFmpeg stderr: {result.stderr[:500] if result.stderr else 'No stderr'}")
        app_state.step_status[1] = '✗'
        return
    
    # Verify output file
    if os.path.exists(Settings.CUT_VIDEO):
        size = os.path.getsize(Settings.CUT_VIDEO) / (1024 * 1024)
        log(f"✓ Cut complete: {Settings.CUT_VIDEO}")
        log(f"  File size: {size:.2f} MB")
        log(f"  Duration: {duration} seconds")
        app_state.step_status[1] = '✓'
    else:
        log("✗ Cut failed: output file not created")
        app_state.step_status[1] = '✗'


def _step_extract_german():
    """Extract German subtitles using Whisper"""
    log("Extracting German subtitles with Whisper...")
    app_state.step_status[2] = '⏳'
    
    # Extract audio first to WAV for reliable Whisper processing
    if not os.path.exists(Settings.AUDIO_WAV):
        log("Extracting audio to WAV (16kHz mono PCM)...")
        cmd = [
            Settings.FFMPEG, "-y",
            "-i", Settings.CUT_VIDEO,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            "-map_metadata", "0",
            Settings.AUDIO_WAV
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line:
                    log(f"ffmpeg: {line}")
        
        if os.path.exists(Settings.AUDIO_WAV):
            wav_size = os.path.getsize(Settings.AUDIO_WAV)
            log(f"WAV file created: {wav_size} bytes")
    
    # Run Whisper
    audio_file = Settings.AUDIO_WAV if os.path.exists(Settings.AUDIO_WAV) else Settings.CUT_VIDEO
    log(f"Running Whisper on: {audio_file}")
    
    cmd = [
        "python3", "-m", "whisper",
        audio_file,
        "--model", "small",
        "--task", "transcribe",
        "--language", "de",
        "--output_format", "srt",
        "--output_dir", ".",
    ]
    
    log(f"Whisper command: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    if result.stdout:
        for line in result.stdout.strip().split('\n')[:20]:
            if line:
                log(f"whisper: {line}")
    
    # Check for SRT file
    srt_locations = ["cut.srt", os.path.join(".", "cut.srt"), os.path.splitext(audio_file)[0] + ".srt"]
    srt_created = False
    for srt_path in srt_locations:
        if os.path.exists(srt_path):
            log(f"Found SRT at: {srt_path}")
            with open(srt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(Settings.SUBS_SRT_DE, 'w', encoding='utf-8') as f:
                f.write(content)
            srt_created = True
            break
    
    if srt_created and os.path.exists(Settings.SUBS_SRT_DE):
        with open(Settings.SUBS_SRT_DE, 'r', encoding='utf-8') as f:
            content = f.read()
        if content.strip():
            log(f"Created: {Settings.SUBS_SRT_DE} ({len(content)} chars)")
            app_state.step_status[2] = '✓'
            app_state.german_srt_content = content
            return
    
    log("Failed to create SRT")
    app_state.step_status[2] = '✗'


def _step_translate():
    """Translate German to Arabic"""
    log("Translating to Arabic...")
    app_state.step_status[4] = '⏳'
    
    if not os.path.exists(Settings.SUBS_SRT_DE):
        log("German SRT not found!")
        return
    
    with open(Settings.SUBS_SRT_DE, "r", encoding="utf-8") as f:
        subs = list(srt_parse(f.read()))
    
    arabic_subtitles = []
    for sub in subs:
        german_text = sub.content
        arabic = _translate_to_arabic(german_text)
        arabic_subtitles.append({
            'start': sub.start,
            'end': sub.end,
            'content': arabic
        })
    
    with open(Settings.SUBS_SRT_AR, "w", encoding="utf-8") as f:
        for i, sub in enumerate(arabic_subtitles, 1):
            f.write(f"{i}\n{sub['start']} --> {sub['end']}\n{sub['content']}\n\n")
    
    log(f"Created: {Settings.SUBS_SRT_AR}")
    app_state.step_status[4] = '✓'
    
    # Load content
    with open(Settings.SUBS_SRT_AR, 'r', encoding='utf-8') as f:
        app_state.arabic_srt_content = f.read()


def _translate_to_arabic(text):
    """Translate text to Arabic"""
    try:
        return GoogleTranslator(source="de", target="ar").translate(text)
    except Exception as e:
        log(f"Translation error: {e}")
        return text


def _step_create_ass():
    """Create ASS subtitle file"""
    log("Creating ASS file...")
    app_state.step_status[6] = '⏳'
    
    if not os.path.exists(Settings.SUBS_SRT_DE) or not os.path.exists(Settings.SUBS_SRT_AR):
        log("German or Arabic SRT not found!")
        return
    
    with open(Settings.SUBS_SRT_DE, "r", encoding="utf-8") as f:
        german_subs = list(srt_parse(f.read()))
    
    with open(Settings.SUBS_SRT_AR, "r", encoding="utf-8") as f:
        arabic_subs = list(srt_parse(f.read()))
    
    ass = pysubs2.SSAFile()
    ass.styles["German"] = pysubs2.SSAStyle(
        fontname="Arial",
        fontsize=22,
        primarycolor=pysubs2.Color(255, 255, 255, 0),
        marginv=90
    )
    
    ass.styles["Arabic"] = pysubs2.SSAStyle(
        fontname="Arial",
        fontsize=18,
        primarycolor=pysubs2.Color(255, 255, 0, 0),
        marginv=40
    )
    
    # Add German with karaoke
    for sub in german_subs:
        words = sub.content.split()
        if not words:
            continue
        total_ms = (sub.end.total_seconds() - sub.start.total_seconds()) * 1000
        per_word = max(50, int(total_ms / len(words)))
        karaoke = "".join(f"{{\\k{per_word//10}}}{w} " for w in words)
        
        ass.append(pysubs2.SSAEvent(
            start=int(sub.start.total_seconds() * 1000),
            end=int(sub.end.total_seconds() * 1000),
            text=karaoke,
            style="German"
        ))
    
    # Add Arabic
    for sub in arabic_subs:
        ass.append(pysubs2.SSAEvent(
            start=int(sub.start.total_seconds() * 1000),
            end=int(sub.end.total_seconds() * 1000),
            text=sub.content,
            style="Arabic"
        ))
    
    ass.save(Settings.SUBS_ASS)
    log(f"Created: {Settings.SUBS_ASS}")
    app_state.step_status[6] = '✓'


def _step_produce_video():
    """Produce final video with subtitles"""
    log("Producing final video...")
    app_state.step_status[7] = '⏳'
    
    if not os.path.exists(Settings.CUT_VIDEO):
        log("Cut video not found!")
        return
    
    result = subprocess.run([
        Settings.FFMPEG, "-y",
        "-i", Settings.CUT_VIDEO,
        "-vf", f"ass={Settings.SUBS_ASS}",
        "-c:v", "libx264",
        "-c:a", "aac",
        Settings.FINAL_VIDEO
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    if result.stdout:
        for line in result.stdout.strip().split('\n')[:20]:
            if line:
                log(f"ffmpeg: {line}")
    
    if result.returncode != 0:
        log(f"FFmpeg error: {result.returncode}")
        app_state.step_status[7] = '✗'
        return
    
    log(f"Created: {Settings.FINAL_VIDEO}")
    app_state.step_status[7] = '✓'


# ================= File Operations =================

@app.route('/api/file/german', methods=['GET', 'POST'])
def german_file():
    """Get or save German SRT"""
    if request.method == 'GET':
        content = get_file_content(Settings.SUBS_SRT_DE)
        return jsonify({'content': content})
    
    data = request.json
    content = data.get('content', '')
    with open(Settings.SUBS_SRT_DE, 'w', encoding='utf-8') as f:
        f.write(content)
    app_state.german_srt_content = content
    log("Saved German SRT")
    return jsonify({'message': 'German SRT saved'})


@app.route('/api/file/arabic', methods=['GET', 'POST'])
def arabic_file():
    """Get or save Arabic SRT"""
    if request.method == 'GET':
        content = get_file_content(Settings.SUBS_SRT_AR)
        return jsonify({'content': content})
    
    data = request.json
    content = data.get('content', '')
    with open(Settings.SUBS_SRT_AR, 'w', encoding='utf-8') as f:
        f.write(content)
    app_state.arabic_srt_content = content
    log("Saved Arabic SRT")
    return jsonify({'message': 'Arabic SRT saved'})


@app.route('/api/file/reload/german')
def reload_german():
    """Reload German SRT from file"""
    content = get_file_content(Settings.SUBS_SRT_DE)
    app_state.german_srt_content = content
    log("Reloaded German SRT")
    return jsonify({'content': content})


@app.route('/api/file/reload/arabic')
def reload_arabic():
    """Reload Arabic SRT from file"""
    content = get_file_content(Settings.SUBS_SRT_AR)
    app_state.arabic_srt_content = content
    log("Reloaded Arabic SRT")
    return jsonify({'content': content})


@app.route('/api/file/files_info')
def files_info():
    """Get files info"""
    return jsonify(get_files_info())


def get_file_content(filepath):
    """Get file content"""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def get_files_info():
    """Get information about generated files"""
    info = []
    files = [
        (Settings.FINAL_VIDEO, "Final Video"),
        (Settings.SUBS_ASS, "ASS Subtitles"),
        (Settings.SUBS_SRT_DE, "German SRT"),
        (Settings.SUBS_SRT_AR, "Arabic SRT"),
    ]
    for filename, desc in files:
        if os.path.exists(filename):
            size = os.path.getsize(filename) / (1024 * 1024)
            info.append({'name': desc, 'file': filename, 'size': f"{size:.2f} MB", 'exists': True})
        else:
            info.append({'name': desc, 'file': filename, 'size': "N/A", 'exists': False})
    return info


# ================= Utility Routes =================

@app.route('/api/clear', methods=['POST'])
def clear_files():
    """Clear all generated files"""
    files = [Settings.VIDEO_NAME, Settings.CUT_VIDEO, Settings.AUDIO_WAV,
            Settings.SUBS_SRT_DE, Settings.SUBS_SRT_AR, Settings.SUBS_ASS,
            Settings.FINAL_VIDEO]
    for f in files:
        if os.path.exists(f):
            os.remove(f)
    
    app_state.step_status = [''] * 8
    app_state.logs = []
    log("Deleted all files")
    return jsonify({'message': 'All files deleted'})


@app.route('/api/logs')
def get_logs():
    """Get all logs"""
    return jsonify({'logs': app_state.logs})


@app.route('/api/video/play', methods=['POST'])
def play_video():
    """Open video in default player (sends command to client)"""
    # This is handled client-side with a link to the video file
    return jsonify({
        'video_url': url_for('static_files', filename=Settings.FINAL_VIDEO),
        'message': 'Video ready to play'
    })


@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return app.send_static_file(filename)


@app.route('/<filename>')
def serve_file(filename):
    """Serve files from the app root directory (like final_video.mp4)"""
    # Security: only allow certain file extensions
    allowed_extensions = {'mp4', 'srt', 'ass', 'wav', 'mp3', 'webm', 'mkv'}
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    if ext not in allowed_extensions:
        return jsonify({'error': 'File type not allowed'}), 403
    
    filepath = os.path.join(os.getcwd(), filename)
    if os.path.exists(filepath):
        return send_from_directory(os.getcwd(), filename)
    return jsonify({'error': 'File not found'}), 404


if __name__ == "__main__":
    print("=" * 50)
    print("YouTube Karaoke Generator - Web App")
    print("=" * 50)
    print("Starting server at http://localhost:5001")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5001)
