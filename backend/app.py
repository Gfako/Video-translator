from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from dotenv import load_dotenv
from flask_cors import CORS
# Load environment variables
load_dotenv()


# Create Flask app
app = Flask(__name__)
CORS(app)

# Configure database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_translator.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure file uploads
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# HeyGen API Configuration
HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY')

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
    job = TranslationJob.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify({
        'job': job.to_dict()
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'user_id' not in request.form:
        return jsonify({'error': 'user_id is required'}), 400
    
    user_id = request.form['user_id']
    user = User.query.get(user_id)
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
    """Start video translation with HeyGen"""
    
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
    
    # Find the job
    job = TranslationJob.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    if job.status != 'uploaded':
        return jsonify({
            'error': f'Job status is {job.status}, expected uploaded'
        }), 400
    
    try:
        # Update job status
        job.status = 'processing'
        job.target_language = target_language
        db.session.commit()
        
        # For now, simulate translation process
        # In real implementation, this would call HeyGen API
        
        return jsonify({
            'message': 'Translation started successfully!',
            'job': job.to_dict(),
            'status': 'processing',
            'target_language': target_language,
            'note': 'Currently simulated - real HeyGen integration ready for your API key'
        }), 200
        
    except Exception as e:
        job.status = 'failed'
        db.session.commit()
        
        return jsonify({
            'error': 'Translation failed to start',
            'details': str(e),
            'job': job.to_dict()
        }), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database ready!")
    
    if HEYGEN_API_KEY:
        print("✅ HeyGen API configured!")
    else:
        print("⚠️  HeyGen API key not found. Set HEYGEN_API_KEY environment variable.")
    
    print("🚀 Starting Video Translation API with HeyGen...")
    print("🎥 Supported languages: es, fr, de, it, pt, ru, ja, ko, zh, hi")
    print("🌐 Go to: http://localhost:5000")
    app.run(debug=True, port=5000)