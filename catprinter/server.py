#!/usr/bin/env python3
"""
Termux server that receives image paths from Arduino macro,
converts them to 1-bit packed rows, and sends to ESP32 printer AP.

ESP32 creates WiFi AP: ESP32_PRINTER / printer123
Connect to it, then run:

  python3 server.py --esp32-ip 192.168.4.1 --port 5000

Then from Arduino macro trigger:
  http://192.168.0.X:5000/print?image=/path/to/photo.jpg
  (where 192.168.0.X is Termux IP on the AP)
"""

from flask import Flask, request, jsonify
from PIL import Image, ImageEnhance
import sys
import os
import argparse
import requests
from pathlib import Path

app = Flask(__name__)

# Global config
ESP32_IP = "192.168.4.1"
ESP32_PORT = 80
PRINTER_WIDTH = 384
GRAYSCALE_DENSITY = 65

def convert_image_to_packed(image_path, width=384, density=65):
    """Convert image to 1-bit packed rows."""
    if not os.path.exists(image_path):
        return None, f"Image not found: {image_path}"
    
    try:
        img = Image.open(image_path)
        print(f"[*] Loaded: {image_path} ({img.size})")
        
        # Resize to width (preserve aspect ratio)
        aspect_ratio = img.size[1] / img.size[0]
        target_height = int(width * aspect_ratio)
        img = img.resize((width, target_height), Image.Resampling.LANCZOS)
        print(f"[*] Resized to: {width}x{target_height}")
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Adjust brightness for grayscale density
        density_factor = (100 - density) / 100.0
        img = ImageEnhance.Brightness(img).enhance(1.0 - (density_factor * 0.4))
        
        # Dither to 1-bit
        img = img.convert('1')
        print(f"[*] Dithered to 1-bit with {density}% density")
        
        # Pack 8 pixels per byte
        pixels = img.load()
        image_width, image_height = img.size
        bytes_per_row = (image_width + 7) // 8
        packed_data = []
        
        for y in range(image_height):
            for x in range(0, image_width, 8):
                byte = 0
                for bit_idx in range(8):
                    px = x + bit_idx
                    if px < image_width:
                        pixel_val = pixels[px, y]
                        bit = 0 if pixel_val > 127 else 1
                        byte |= (bit << (7 - bit_idx))
                packed_data.append(byte)
        
        print(f"[*] Packed: {len(packed_data)} bytes ({image_height} rows)")
        return (image_width, image_height, packed_data), None
        
    except Exception as e:
        return None, f"Error converting image: {str(e)}"

def send_to_esp32(width, height, packed_data):
    """Send packed image data to ESP32 via HTTP."""
    # Convert bytes to hex string
    hex_data = ''.join(f'{b:02x}' for b in packed_data)
    
    # Send to ESP32
    url = f"http://{ESP32_IP}:{ESP32_PORT}/print"
    params = {
        'width': width,
        'height': height,
        'data': hex_data
    }
    
    try:
        print(f"[*] Sending to ESP32 at {ESP32_IP}...")
        response = requests.post(url, params=params, timeout=30)
        if response.status_code == 200:
            print(f"[+] ESP32 response: {response.text}")
            return True, response.text
        else:
            return False, f"ESP32 error: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"Failed to reach ESP32: {str(e)}"

@app.route('/print', methods=['GET', 'POST'])
def handle_print():
    """
    Receive image path from Arduino macro.
    
    Usage (from Arduino macro):
      GET http://termux-ip:5000/print?image=/path/to/image.jpg
    """
    image_path = request.args.get('image') or request.form.get('image')
    
    if not image_path:
        return jsonify({'error': 'Missing image parameter'}), 400
    
    print(f"\n[>>] Received print request: {image_path}")
    
    # Convert image
    result, error = convert_image_to_packed(image_path, PRINTER_WIDTH, GRAYSCALE_DENSITY)
    if error:
        print(f"[-] {error}")
        return jsonify({'error': error}), 400
    
    width, height, packed_data = result
    
    # Send to ESP32
    success, message = send_to_esp32(width, height, packed_data)
    if success:
        print(f"[+] Print successful!\n")
        return jsonify({
            'status': 'success',
            'message': message,
            'dimensions': f'{width}x{height}',
            'data_size': len(packed_data)
        }), 200
    else:
        print(f"[-] {message}\n")
        return jsonify({'error': message}), 502

@app.route('/status', methods=['GET'])
def handle_status():
    """Check server and ESP32 status."""
    try:
        esp32_response = requests.get(f"http://{ESP32_IP}:{ESP32_PORT}/status", timeout=5)
        esp32_status = esp32_response.json()
    except:
        esp32_status = {'status': 'unreachable'}
    
    return jsonify({
        'server': 'ready',
        'esp32': esp32_status
    }), 200

@app.route('/config', methods=['GET', 'POST'])
def handle_config():
    """Get/set configuration."""
    global ESP32_IP, GRAYSCALE_DENSITY
    
    if request.method == 'POST':
        data = request.get_json() or request.form
        if 'esp32_ip' in data:
            ESP32_IP = data['esp32_ip']
            print(f"[*] ESP32 IP set to: {ESP32_IP}")
        if 'density' in data:
            GRAYSCALE_DENSITY = int(data['density'])
            print(f"[*] Grayscale density set to: {GRAYSCALE_DENSITY}%")
        return jsonify({'status': 'updated'}), 200
    
    return jsonify({
        'esp32_ip': ESP32_IP,
        'esp32_port': ESP32_PORT,
        'printer_width': PRINTER_WIDTH,
        'grayscale_density': GRAYSCALE_DENSITY
    }), 200

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Termux photo printer server')
    parser.add_argument('--port', type=int, default=5000, help='Server port (default: 5000)')
    parser.add_argument('--esp32-ip', default='192.168.4.1', help='ESP32 AP IP (default: 192.168.4.1)')
    parser.add_argument('--density', type=int, default=65, help='Grayscale density 0-100 (default: 65)')
    parser.add_argument('--host', default='0.0.0.0', help='Server host (default: 0.0.0.0)')
    
    args = parser.parse_args()
    
    ESP32_IP = args.esp32_ip
    GRAYSCALE_DENSITY = args.density
    
    print(f"""
╔════════════════════════════════════════════╗
║   TERMUX PHOTO PRINTER SERVER              ║
║   (Connected to ESP32 WiFi AP)             ║
╚════════════════════════════════════════════╝

Setup:
  1. ESP32 starts and creates WiFi AP
  2. Phone connects to "ESP32_PRINTER" (password: printer123)
  3. Run this server on Termux

Config:
  - Termux Server: http://0.0.0.0:{args.port}
  - ESP32 AP IP: {ESP32_IP}:{ESP32_PORT}
  - Grayscale Density: {GRAYSCALE_DENSITY}%

Endpoints:
  GET/POST /print?image=<path>  - Print image
  GET      /status              - Check status
  GET/POST /config              - Get/set config

""")
    
    app.run(host=args.host, port=args.port, debug=False)
