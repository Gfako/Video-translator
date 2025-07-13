from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from dotenv import load_dotenv
from flask_cors import CORS
import threading
import time
import requests
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv, find_dotenv
import os

# Load environment variables
dotenv_path = find_dotenv()
print("Found .env at:", dotenv_path)
load_dotenv(dotenv_path=dotenv_path)

# Debug environment variables
print("AWS_ACCESS_KEY_ID:", os.getenv("AWS_ACCESS_KEY_ID"))
print("AWS_SECRET_ACCESS_KEY:", os.getenv("AWS_SECRET_ACCESS_KEY")[:10] + "..." if os.getenv("AWS_SECRET_ACCESS_KEY") else "None")
print("AWS_DEFAULT_REGION:", os.getenv("AWS_DEFAULT_REGION"))

# HEYGEN API KEY DEBUG - ADDED HERE
print("=== HEYGEN API KEY CHECK ===")
heygen_key = os.getenv('HEYGEN_API_KEY')
if heygen_key:
    print(f"✅ HeyGen key found")
    print(f"Key length: {len(heygen_key)}")
    print(f"Key starts with: {heygen_key[:15]}...")
    print(f"Key ends with: ...{heygen_key[-10:]}")
else:
    print("❌ No HeyGen API key found!")
print("===============================")

# QUICK HEYGEN API TEST - TESTING V2 ENDPOINTS AND VIDEO TRANSLATE
if heygen_key:
    print("🧪 Quick HeyGen API Test...")
    headers = {"x-api-key": heygen_key, "accept": "application/json", "Content-Type": "application/json"}
    
    # Test v2 endpoints that showed 401
    print("   Testing v2 endpoints...")
    v2_endpoints = [
        "https://api.heygen.com/v2/user/remaining_quota",
        "https://api.heygen.com/v2/avatars"
    ]
    
    for endpoint in v2_endpoints:
        try:
            response = requests.get(endpoint, headers=headers)
            print(f"   {endpoint}: {response.status_code}")
            if response.status_code == 200:
                print(f"   ✅ SUCCESS! API key is valid")
                print(f"   Response: {response.json()}")
            elif response.status_code == 401:
                print(f"   ❌ API key is INVALID or EXPIRED")
            elif response.status_code == 403:
                print(f"   ❌ API key valid but no permissions/credits")
            else:
                print(f"   Unexpected: {response.text[:100]}...")
        except Exception as e:
            print(f"   Error: {e}")
    
    # Test video translate with minimal POST (should fail but give us better error info)
    print("   Testing video translate with POST...")
    try:
        minimal_payload = {"video_url": "https://example.com/test.mp4", "output_language": "es"}
        response = requests.post("https://api.heygen.com/v2/video_translate", headers=headers, json=minimal_payload)
        print(f"   Video translate POST: {response.status_code}")
        if response.status_code == 200:
            print(f"   ✅ Video translate endpoint works!")
        elif response.status_code == 401:
            print(f"   ❌ Invalid API key for video translate")
        elif response.status_code == 403:
            print(f"   ❌ No permissions/credits for video translate")
        elif response.status_code == 400:
            print(f"   ⚠️  Bad request (expected - we used dummy data)")
            print(f"   This means the endpoint works but needs valid data")
        print(f"   Response: {response.text[:200]}...")
    except Exception as e:
        print(f"   Video translate test error: {e}")
        
else:
    print("❌ No HeyGen key to test")
print("===============================")

# Create Flask app
app = Flask(__name__)
CORS(app, origins=['http://localhost:8080', 'http://localhost:3000', 'http://localhost:5173'], supports_credentials=True)

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_translator.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure file uploads
UPLOAD_FOLDER = 'uploads'
TRANSLATED_FOLDER = 'translated'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TRANSLATED_FOLDER, exist_ok=True)

# HeyGen API Configuration
HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY')

# S3 Configuration - UPDATE THIS WITH YOUR ACTUAL BUCKET NAME
S3_BUCKET_NAME = 'video-translator-your-name-2025'  # Replace with your actual bucket name

def upload_to_s3_and_get_url(local_file_path, bucket_name, object_name=None):
    """Upload file to S3 and return public URL - Fixed for ACL disabled buckets"""
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_DEFAULT_REGION', 'eu-north-1')
    )
    
    if object_name is None:
        object_name = os.path.basename(local_file_path)
    
    try:
        print(f"Uploading {local_file_path} to s3://{bucket_name}/{object_name}")
        
        # Upload file WITHOUT ACL (since your bucket has ACLs disabled)
        s3_client.upload_file(local_file_path, bucket_name, object_name)
        
        # Generate public URL with correct region
        region = os.getenv('AWS_DEFAULT_REGION', 'eu-north-1')
        if region == 'us-east-1':
            url = f"https://{bucket_name}.s3.amazonaws.com/{object_name}"
        else:
            url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{object_name}"
        
        print(f"✅ Upload successful: {url}")
        return url
        
    except FileNotFoundError:
        print(f"❌ File not found: {local_file_path}")
        return None
    except NoCredentialsError:
        print("❌ AWS credentials not found")
        return None
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"❌ Failed to upload {local_file_path} to {bucket_name}/{object_name}:")
        print(f"   Error: {error_code} - {error_message}")
        
        # Specific error handling
        if error_code == 'InvalidAccessKeyId':
            print("   → Check your AWS_ACCESS_KEY_ID in .env file")
        elif error_code == 'SignatureDoesNotMatch':
            print("   → Check your AWS_SECRET_ACCESS_KEY in .env file")
        elif error_code == 'AccessDenied':
            print("   → Your AWS user needs S3 permissions")
        elif error_code == 'NoSuchBucket':
            print(f"   → Bucket '{bucket_name}' does not exist")
            
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None

# Initialize database
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }

class TranslationJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    target_language = db.Column(db.String(10), nullable=True)
    status = db.Column(db.String(20), default='uploaded')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'original_filename': self.original_filename,
            'target_language': self.target_language,
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

# Routes
@app.route('/')
def home():
    return jsonify({
        "message": "Video Translator API with HeyGen Integration!",
        "status": "working",
        "heygen_configured": bool(HEYGEN_API_KEY),
        "s3_bucket": S3_BUCKET_NAME,
        "aws_region": os.getenv('AWS_DEFAULT_REGION'),
        "endpoints": [
            "GET / - This welcome message",
            "GET /api/test - Test endpoint", 
            "GET /api/users - List all users",
            "POST /api/users - Create new user",
            "GET /api/jobs - List all jobs",
            "POST /api/upload - Upload video file",
            "POST /api/translate - Start video translation",
            "GET /api/jobs/<id> - Check job status"
        ]
    })

@app.route('/api/test')
def test():
    return jsonify({
        "status": "success",
        "message": "HeyGen video translation API is ready!",
        "heygen_api_configured": bool(HEYGEN_API_KEY),
        "s3_bucket_configured": bool(S3_BUCKET_NAME),
        "aws_credentials_configured": bool(os.getenv('AWS_ACCESS_KEY_ID')),
        "supported_languages": [
            "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh", "hi"
        ],
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify({
        "users": [user.to_dict() for user in users],
        "count": len(users)
    })

@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.get_json()
    
    if not data or 'email' not in data:
        return jsonify({'error': 'Email is required'}), 400
    
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        return jsonify({'error': 'User already exists'}), 400
    
    user = User(email=data['email'])
    db.session.add(user)
    db.session.commit()
    
    return jsonify({
        'message': 'User created successfully',
        'user': user.to_dict()
    }), 201

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    jobs = TranslationJob.query.all()
    return jsonify({
        "jobs": [job.to_dict() for job in jobs],
        "count": len(jobs)
    })

@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get specific job status"""
    job = db.session.get(TranslationJob, job_id)  # Fixed SQLAlchemy warning
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify({
        'job': job.to_dict()
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'user_id' not in request.form:
        return jsonify({'error': 'user_id is required'}), 400
    
    try:
        user_id = int(request.form['user_id'])
    except ValueError:
        return jsonify({'error': 'user_id must be a valid integer'}), 400
    
    user = db.session.get(User, user_id)  # Fixed SQLAlchemy warning
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        filename = file.filename
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        job = TranslationJob(
            user_id=user_id,
            original_filename=filename,
            status='uploaded'
        )
        
        db.session.add(job)
        db.session.commit()
        
        return jsonify({
            'message': 'File uploaded successfully!',
            'job': job.to_dict(),
            'filename': filename,
            'next_step': 'Use /api/translate to start translation'
        }), 201
        
    except Exception as e:
        return jsonify({
            'error': 'Upload failed',
            'details': str(e)
        }), 500

@app.route('/api/translate', methods=['POST'])
def start_translation():
    if not HEYGEN_API_KEY:
        return jsonify({
            'error': 'HeyGen API not configured',
            'message': 'Please set HEYGEN_API_KEY environment variable'
        }), 500

    data = request.get_json()

    if not data or 'job_id' not in data or 'target_language' not in data:
        return jsonify({
            'error': 'job_id and target_language are required',
            'supported_languages': ['es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh', 'hi']
        }), 400

    job_id = data['job_id']
    target_language = data['target_language']

    job = db.session.get(TranslationJob, job_id)  # Fixed SQLAlchemy warning
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if job.status != 'uploaded':
        return jsonify({
            'error': f'Job status is {job.status}, expected uploaded'
        }), 400

    try:
        # Update job status to processing
        job.status = 'processing'
        job.target_language = target_language
        db.session.commit()

        def heygen_translate(job_id, input_filename, target_language):
            print("Starting HeyGen translation thread for:", input_filename, target_language)
            try:
                video_path = os.path.join(UPLOAD_FOLDER, input_filename)
                print("Uploading to S3:", video_path)
                video_public_url = upload_to_s3_and_get_url(video_path, S3_BUCKET_NAME)
                print("S3 public URL:", video_public_url)
                
                if not video_public_url:
                    raise Exception("Failed to upload video to S3")

                headers = {
                    "x-api-key": HEYGEN_API_KEY,
                    "accept": "application/json",
                    "Content-Type": "application/json"
                }
                payload = {
                    "video_url": video_public_url,
                    "output_language": target_language,
                    "title": f"Translated {input_filename}"
                }
                
                print("Sending request to HeyGen API...")
                response = requests.post("https://api.heygen.com/v2/video_translate", headers=headers, json=payload)
                response.raise_for_status()
                video_translate_id = response.json()["data"]["video_translate_id"]
                print(f"HeyGen translation ID: {video_translate_id}")

                status_url = f"https://api.heygen.com/v2/video_translate/{video_translate_id}"
                while True:
                    print("Checking translation status...")
                    status_response = requests.get(status_url, headers=headers)
                    status_response.raise_for_status()
                    status_data = status_response.json()["data"]
                    status = status_data["status"]
                    print(f"Translation status: {status}")
                    
                    if status == "success":
                        translated_video_url = status_data["url"]
                        print(f"Translation completed! URL: {translated_video_url}")
                        break
                    elif status == "failed":
                        raise Exception(f"HeyGen translation failed: {status_data.get('message')}")
                    time.sleep(5)

                # Download translated video
                print("Downloading translated video...")
                video_content = requests.get(translated_video_url).content
                translated_filename = f"translated_{input_filename}"
                translated_path = os.path.join(TRANSLATED_FOLDER, translated_filename)
                
                with open(translated_path, "wb") as f:
                    f.write(video_content)
                print(f"Translated video saved: {translated_path}")

                # Update job status
                with app.app_context():
                    job = db.session.get(TranslationJob, job_id)  # Fixed SQLAlchemy warning
                    if job:
                        job.status = 'completed'
                        job.original_filename = translated_filename
                        db.session.commit()
                        print("Job marked as completed")
                        
            except Exception as e:
                print("Translation error:", e)
                with app.app_context():
                    job = db.session.get(TranslationJob, job_id)  # Fixed SQLAlchemy warning
                    if job:
                        job.status = 'failed'
                        db.session.commit()

        threading.Thread(target=heygen_translate, args=(job_id, job.original_filename, target_language)).start()

        return jsonify({
            'message': 'Translation started with HeyGen!',
            'job': job.to_dict(),
            'status': 'processing',
            'target_language': target_language,
            'note': 'Real HeyGen translation in progress.'
        }), 200

    except Exception as e:
        job.status = 'failed'
        db.session.commit()
        return jsonify({
            'error': 'Translation failed to start',
            'details': str(e),
            'job': job.to_dict()
        }), 500

@app.route('/translated/<filename>', methods=['GET'])
def download_translated(filename):
    """Download translated video file"""
    return send_from_directory(TRANSLATED_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database ready!")
    
    if HEYGEN_API_KEY:
        print("✅ HeyGen API configured!")
    else:
        print("⚠️  HeyGen API key not found. Set HEYGEN_API_KEY environment variable.")
    
    if os.getenv('AWS_ACCESS_KEY_ID'):
        print("✅ AWS credentials configured!")
        print(f"✅ S3 bucket: {S3_BUCKET_NAME}")
    else:
        print("⚠️  AWS credentials not found. Set AWS credentials in .env file.")
    
    print("🚀 Starting Video Translation API with HeyGen...")
    print("🎥 Supported languages: es, fr, de, it, pt, ru, ja, ko, zh, hi")
    print("🌐 Go to: http://localhost:5000")
    
    # Fixed for Render deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)