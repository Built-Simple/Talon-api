# complete-setup.ps1
# Run this in your talon-api folder

Write-Host "=== TALON API COMPLETE SETUP ===" -ForegroundColor Cyan
Write-Host "Setting up everything for deployment..." -ForegroundColor Green

# Get current directory
$currentDir = Get-Location

# Create all necessary files
Write-Host "`n1. Creating deployment files..." -ForegroundColor Yellow

# requirements.txt
@"
Flask==2.3.2
flask-cors==4.0.0
chromadb==0.4.14
stripe==5.5.0
PyJWT==2.8.0
gunicorn==21.2.0
python-dotenv==1.0.0
requests==2.31.0
"@ | Out-File -FilePath "requirements.txt" -Encoding UTF8 -NoNewline
Write-Host "   ✓ requirements.txt" -ForegroundColor Green

# Procfile (CRITICAL: Must be ASCII, no BOM)
$procfileContent = "web: gunicorn talon_api:app --bind 0.0.0.0:`$PORT --timeout 120"
[System.IO.File]::WriteAllText("$currentDir\Procfile", $procfileContent, [System.Text.Encoding]::ASCII)
Write-Host "   ✓ Procfile" -ForegroundColor Green

# runtime.txt
"python-3.11.4" | Out-File -FilePath "runtime.txt" -Encoding UTF8 -NoNewline
Write-Host "   ✓ runtime.txt" -ForegroundColor Green

# .gitignore
@"
.env
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
*.log
.vscode/
.idea/
"@ | Out-File -FilePath ".gitignore" -Encoding UTF8 -NoNewline
Write-Host "   ✓ .gitignore" -ForegroundColor Green

# Update the config to use the D: drive path
$chromaConfig = @{
    chroma_path = "D:\so_vectors_quality\chroma_db"
} | ConvertTo-Json

$chromaConfig | Out-File -FilePath "talon_chromadb_config.json" -Encoding UTF8 -NoNewline
Write-Host "   ✓ Updated ChromaDB config" -ForegroundColor Green

# Create talon_api.py with your specific paths
Write-Host "`n2. Creating talon_api.py..." -ForegroundColor Yellow

$apiCode = @'
#!/usr/bin/env python3
"""
Talon API Backend - Production Ready
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import chromadb
import json
import stripe
import os
from datetime import datetime
import jwt
import logging
import re
from pathlib import Path
import sys

app = Flask(__name__)
CORS(app)

# Configuration
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-this')
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID', 'price_test')
stripe.api_key = STRIPE_SECRET_KEY

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ChromaDB Configuration
# Try multiple paths for flexibility
POSSIBLE_PATHS = [
    r"D:\so_vectors_quality\chroma_db",  # Your local path
    "/app/chromadb_data",  # Railway container path
    "./chromadb_data",  # Local relative path
    os.getenv('CHROMADB_PATH', '')  # Environment variable
]

CHROMA_PATH = None
for path in POSSIBLE_PATHS:
    if os.path.exists(path):
        CHROMA_PATH = path
        break

if not CHROMA_PATH:
    # Use in-memory for deployment if no persistent storage found
    CHROMA_PATH = "./chromadb_temp"
    os.makedirs(CHROMA_PATH, exist_ok=True)

logger.info(f"Using ChromaDB at: {CHROMA_PATH}")

# Initialize ChromaDB
try:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    
    # Try to get existing collections
    try:
        rules_collection = client.get_collection("talon_prevention_rules")
        logger.info(f"Connected to rules collection: {rules_collection.count()} items")
    except:
        # Create if doesn't exist
        rules_collection = client.create_collection("talon_prevention_rules")
        logger.info("Created new rules collection")
        
    try:
        stackoverflow_collection = client.get_collection("stackoverflow_quality")
        logger.info(f"Connected to Stack Overflow collection: {stackoverflow_collection.count()} items")
    except:
        stackoverflow_collection = None
        logger.warning("No Stack Overflow collection found")
        
except Exception as e:
    logger.error(f"ChromaDB init error: {e}")
    # Create in-memory collections as fallback
    client = chromadb.Client()
    rules_collection = client.create_collection("talon_prevention_rules")
    stackoverflow_collection = None

# Simple in-memory user database (use Redis in production)
user_db = {}

@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        'service': 'Talon Error Prevention API',
        'version': '1.0.0',
        'status': 'healthy',
        'rules_loaded': rules_collection.count() if rules_collection else 0,
        'so_loaded': stackoverflow_collection.count() if stackoverflow_collection else 0,
        'chroma_path': CHROMA_PATH
    })

@app.route('/v1/analyze', methods=['POST', 'OPTIONS'])
def analyze_code():
    """Analyze Python code for potential errors"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.json
        code = data.get('code', '')
        
        if not code:
            return jsonify({'error': 'No code provided'}), 400
        
        # Check authentication
        auth_header = request.headers.get('Authorization')
        is_pro = False
        user_id = 'free-tier'
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
                user_id = payload['user_id']
                is_pro = payload.get('tier') == 'pro'
            except jwt.InvalidTokenError:
                logger.warning("Invalid JWT token")
        
        # Check rate limits for free tier
        if not is_pro:
            current_month = datetime.now().strftime('%Y-%m')
            user_key = f"{user_id}:{current_month}"
            
            if user_key not in user_db:
                user_db[user_key] = 0
            
            if user_db[user_key] >= 100:
                return jsonify({
                    'error': 'Free tier limit reached (100/month)',
                    'upgrade_url': 'https://talon-lang.io/upgrade'
                }), 429
            
            user_db[user_key] += 1
        
        # Analyze code for errors
        errors = detect_potential_errors(code)
        
        # Enhance with ChromaDB rules
        enhanced_errors = []
        for error in errors:
            try:
                # Search in both collections if available
                prevention = None
                
                if rules_collection:
                    results = rules_collection.query(
                        query_texts=[f"{error['type']} {error.get('message', '')}"],
                        n_results=1
                    )
                    if results['documents'] and results['documents'][0]:
                        prevention = extract_prevention(results['documents'][0][0])
                
                if not prevention and stackoverflow_collection:
                    results = stackoverflow_collection.query(
                        query_texts=[f"Python {error['type']} fix solution"],
                        n_results=1
                    )
                    if results['documents'] and results['documents'][0]:
                        prevention = f"Based on Stack Overflow: {results['documents'][0][0][:200]}..."
                
                error['prevention'] = prevention or f"Use defensive programming to prevent {error['type']}"
                enhanced_errors.append(error)
                
            except Exception as e:
                logger.error(f"Rule lookup error: {e}")
                error['prevention'] = "Follow Python best practices"
                enhanced_errors.append(error)
        
        return jsonify({
            'errors': enhanced_errors,
            'analyzed_lines': len(code.split('\n')),
            'tier': 'pro' if is_pro else 'free',
            'usage': user_db.get(f"{user_id}:{datetime.now().strftime('%Y-%m')}", 0) if not is_pro else 'unlimited'
        })
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({'error': 'Analysis failed', 'details': str(e)}), 500

def detect_potential_errors(code):
    """Enhanced error detection using patterns"""
    errors = []
    lines = code.split('\n')
    
    # Pattern-based detection
    patterns = {
        'ModuleNotFoundError': [
            (r'import\s+(\w+)', "Module '{module}' might not be installed"),
            (r'from\s+(\w+)\s+import', "Module '{module}' might not be installed")
        ],
        'AttributeError': [
            (r'(\w+)\.(\w+)\s*\(', "'{obj}' might be None"),
            (r'(\w+)\.(\w+)\s*=', "'{obj}' might not have attribute '{attr}'")
        ],
        'TypeError': [
            (r'(\w+)\s*\+\s*(\w+)', "Type mismatch in operation"),
            (r'(\w+)\[(\w+)\]', "Invalid index type")
        ],
        'NameError': [
            (r'print\((\w+)\)', "Variable '{var}' might not be defined"),
            (r'return\s+(\w+)', "Variable '{var}' might not be defined")
        ],
        'FileNotFoundError': [
            (r'open\([\'"]([^\'"]+)[\'"]\)', "File '{file}' might not exist"),
            (r'with\s+open\([\'"]([^\'"]+)[\'"]\)', "File '{file}' might not exist")
        ],
        'ZeroDivisionError': [
            (r'(\w+)\s*/\s*(\w+)', "Possible division by zero"),
            (r'(\w+)\s*//\s*(\w+)', "Possible division by zero")
        ]
    }
    
    for i, line in enumerate(lines):
        for error_type, pattern_list in patterns.items():
            for pattern, message in pattern_list:
                match = re.search(pattern, line)
                if match:
                    errors.append({
                        'type': error_type,
                        'message': message.format(
                            module=match.group(1) if match.lastindex >= 1 else '',
                            obj=match.group(1) if match.lastindex >= 1 else '',
                            attr=match.group(2) if match.lastindex >= 2 else '',
                            var=match.group(1) if match.lastindex >= 1 else '',
                            file=match.group(1) if match.lastindex >= 1 else ''
                        ),
                        'line': i,
                        'column': match.start(),
                        'code_snippet': line.strip()
                    })
    
    return errors

def extract_prevention(doc_text):
    """Extract prevention advice from document"""
    lines = doc_text.split('\n')
    prevention_text = ""
    
    for i, line in enumerate(lines):
        if 'Prevention:' in line:
            if ':' in line:
                prevention_text = line.split(':', 1)[1].strip()
            if i + 1 < len(lines) and prevention_text:
                prevention_text += " " + lines[i + 1].strip()
            break
        elif 'Talon Syntax:' in line and i + 1 < len(lines):
            prevention_text = f"Use Talon: {lines[i + 1].strip()}"
            break
    
    return prevention_text[:200] if prevention_text else "Use Talon's safe syntax"

@app.route('/v1/subscribe', methods=['POST'])
def subscribe():
    """Handle Stripe subscription"""
    try:
        data = request.json
        email = data.get('email')
        payment_method = data.get('payment_method')
        
        if not email or not payment_method:
            return jsonify({'error': 'Email and payment method required'}), 400
        
        # Create Stripe customer
        customer = stripe.Customer.create(
            email=email,
            payment_method=payment_method,
            invoice_settings={'default_payment_method': payment_method}
        )
        
        # Create subscription
        subscription = stripe.Subscription.create(
            customer=customer['id'],
            items=[{'price': STRIPE_PRICE_ID}],
            expand=['latest_invoice.payment_intent']
        )
        
        # Generate API key
        api_key = jwt.encode({
            'user_id': customer['id'],
            'email': email,
            'tier': 'pro',
            'created': datetime.now().isoformat()
        }, JWT_SECRET, algorithm='HS256')
        
        return jsonify({
            'subscription_id': subscription['id'],
            'api_key': api_key,
            'status': 'active',
            'next_invoice': subscription['current_period_end']
        })
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Subscription error: {e}")
        return jsonify({'error': 'Subscription failed'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
'@

$apiCode | Out-File -FilePath "talon_api.py" -Encoding UTF8 -NoNewline
Write-Host "   ✓ talon_api.py created" -ForegroundColor Green

# Create .env template
Write-Host "`n3. Creating environment template..." -ForegroundColor Yellow
@"
# Get these from https://stripe.com
STRIPE_SECRET_KEY=sk_test_YOUR_KEY_HERE
STRIPE_PRICE_ID=price_YOUR_PRICE_ID

# Generate a random string for JWT
JWT_SECRET=change-this-to-random-string-$(Get-Random)

# Your GitHub token
GITHUB_TOKEN=your_github_token_here

# Port for local testing
PORT=5000

# ChromaDB path (optional, will auto-detect)
CHROMADB_PATH=D:\so_vectors_quality\chroma_db
"@ | Out-File -FilePath ".env.example" -Encoding UTF8 -NoNewline
Write-Host "   ✓ .env.example" -ForegroundColor Green

# Copy secure_talon_complete.py if it exists
if (Test-Path "..\secure_talon_complete.py") {
    Copy-Item "..\secure_talon_complete.py" -Destination "."
    Write-Host "   ✓ Copied secure_talon_complete.py" -ForegroundColor Green
}

# Copy safe_executor.py if it exists
if (Test-Path "..\safe_executor.py") {
    Copy-Item "..\safe_executor.py" -Destination "."
    Write-Host "   ✓ Copied safe_executor.py" -ForegroundColor Green
}

Write-Host "`n✅ SETUP COMPLETE!" -ForegroundColor Green
Write-Host "`nNEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Copy .env.example to .env and add your real keys" -ForegroundColor White
Write-Host "2. Test locally:" -ForegroundColor White
Write-Host "   python talon_api.py" -ForegroundColor Cyan
Write-Host "3. Visit http://localhost:5000 to check it's working" -ForegroundColor White
Write-Host "4. Deploy to Railway:" -ForegroundColor White
Write-Host "   railway login" -ForegroundColor Cyan
Write-Host "   railway init" -ForegroundColor Cyan
Write-Host "   railway up" -ForegroundColor Cyan

Write-Host "`nFILES CREATED:" -ForegroundColor Green
Get-ChildItem -File | Select-Object Name, Length, LastWriteTime | Format-Table