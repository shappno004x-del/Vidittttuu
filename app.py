# app.py - Vercel Optimized
from flask import Flask, request, jsonify
import json
import requests
import os
import threading
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii

app = Flask(__name__)

# Configuration
REGION_CONFIG = {
    'bd': {
        'domain': 'clientbp.ggpolarbear.com',
        'token_file': 'tokens_bd.json'
    }
}

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

def load_tokens(region):
    """Load tokens - Vercel compatible"""
    try:
        config = REGION_CONFIG.get(region)
        if not config:
            return None
        
        # Vercel path fix
        base_path = os.path.dirname(os.path.abspath(__file__))
        token_path = os.path.join(base_path, config['token_file'])
        
        # Check if file exists
        if not os.path.exists(token_path):
            # Try current directory
            if os.path.exists('tokens_bd.json'):
                token_path = 'tokens_bd.json'
            else:
                return None
                
        with open(token_path, 'r') as f:
            tokens = json.load(f)
            return tokens
    except Exception as e:
        print(f"Error loading tokens: {e}")
        return None

def encrypt_message(plaintext_bytes):
    """AES encryption"""
    try:
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        padded = pad(plaintext_bytes, AES.block_size)
        encrypted = cipher.encrypt(padded)
        return encrypted.hex()
    except:
        return None

def create_uid_payload(uid):
    """Create simple payload - avoiding protobuf issues"""
    # Simple JSON payload (fallback if protobuf fails)
    return json.dumps({"uid": str(uid), "garena": 1}).encode()

def enc(uid):
    """Encrypt UID"""
    try:
        # Try protobuf first
        import danger_generator_pb2
        msg = danger_generator_pb2.danger_generator()
        msg.saturn_ = int(uid)
        msg.garena = 1
        pb_data = msg.SerializeToString()
        return encrypt_message(pb_data)
    except:
        # Fallback to JSON
        return encrypt_message(create_uid_payload(uid))

def decode_response(content):
    """Decode response - handle both protobuf and JSON"""
    try:
        # Try protobuf first
        import danger_count_pb2
        info = danger_count_pb2.Danger_ff_like()
        info.ParseFromString(content)
        
        # Convert to dict manually
        from google.protobuf.json_format import MessageToJson
        data = json.loads(MessageToJson(info))
        account = data.get("AccountInfo", {})
        return account.get("PlayerNickname", "Unknown"), account.get("UID", None)
    except:
        # Try JSON fallback
        try:
            data = json.loads(content)
            return data.get("PlayerNickname", "Unknown"), data.get("UID", None)
        except:
            return "Unknown", None

def get_player_info(uid, region):
    """Get player info"""
    tokens = load_tokens(region)
    if not tokens:
        return None, None

    config = REGION_CONFIG.get(region)
    if not config:
        return None, None

    # Try first 5 tokens
    for i, token_data in enumerate(tokens[:5]):
        token = token_data.get('token')
        if not token:
            continue
            
        try:
            encrypted_uid = enc(uid)
            if not encrypted_uid:
                continue
                
            url = f"https://{config['domain']}/GetPlayerPersonalShow"
            
            headers = {
                'User-Agent': "Dalvik/2.1.0",
                'Authorization': f"Bearer {token}",
                'Content-Type': "application/x-www-form-urlencoded",
                'X-Unity-Version': "2018.4.11f1",
                'ReleaseVersion': "OB54"
            }

            response = requests.post(
                url,
                data=bytes.fromhex(encrypted_uid),
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                name, uid_result = decode_response(response.content)
                if name != "Unknown":
                    return name, uid_result or uid
                    
        except Exception as e:
            print(f"Token {i+1} failed: {e}")
            continue

    return None, None

def send_friend_request(uid, token, domain, results, lock):
    """Send friend request"""
    try:
        from byte import Encrypt_ID, encrypt_api
        
        encrypted_id = Encrypt_ID(uid)
        payload = f"08a7c4839f1e10{encrypted_id}1801"
        encrypted_payload = encrypt_api(payload)
        
        url = f"https://{domain}/RequestAddingFriend"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Unity-Version": "2018.4.11f1",
            "ReleaseVersion": "OB54",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Dalvik/2.1.0"
        }

        response = requests.post(
            url,
            data=bytes.fromhex(encrypted_payload),
            headers=headers,
            timeout=10
        )

        with lock:
            if response.status_code == 200:
                results['success'] += 1
            else:
                results['failed'] += 1
                
    except Exception as e:
        with lock:
            results['failed'] += 1

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "region": "BD",
        "message": "FreeFire API on Vercel",
        "endpoints": {
            "/send_requests?uid=<UID>": "Send friend requests",
            "/health": "Health check"
        }
    })

@app.route("/health", methods=["GET"])
def health():
    tokens = load_tokens("bd")
    return jsonify({
        "status": "healthy",
        "tokens": len(tokens) if tokens else 0,
        "region": "BD",
        "platform": "Vercel"
    })

@app.route("/send_requests", methods=["GET"])
def handle_friend_request():
    try:
        uid = request.args.get("uid")
        region = request.args.get("region", "bd")

        if not uid:
            return jsonify({"error": "uid required"}), 400

        if region != "bd":
            return jsonify({"error": "Only BD region is supported"}), 400

        # Get player info
        player_name, player_uid = get_player_info(uid, region)

        # Load tokens
        tokens = load_tokens(region)
        if not tokens:
            return jsonify({"error": "No tokens available"}), 500

        config = REGION_CONFIG.get(region)
        domain = config['domain']

        # Send requests (max 20 for Vercel timeout)
        results = {"success": 0, "failed": 0}
        lock = threading.Lock()
        threads = []

        max_tokens = min(20, len(tokens))
        
        for i in range(max_tokens):
            token = tokens[i]['token']
            thread = threading.Thread(
                target=send_friend_request,
                args=(uid, token, domain, results, lock)
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        return jsonify({
            "PlayerName": player_name if player_name else "Unknown",
            "UID": player_uid if player_uid else uid,
            "Region": region.upper(),
            "Success": results["success"],
            "Failed": results["failed"],
            "Status": 1 if results["success"] > 0 else 2
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Vercel handler
app.debug = False