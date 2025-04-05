from flask import Flask, jsonify, abort, make_response, request
import firebase_admin
from firebase_admin import credentials, db
import datetime
import gradio as gr
from collections import deque
import time
import os

# Firebase Configuration
FIREBASE_DB_URL = "https://forest-fire-forcast-default-rtdb.firebaseio.com"
FIREBASE_CERTIFICATE_PATH = "firebase_admin.json"
cred = credentials.Certificate(FIREBASE_CERTIFICATE_PATH)
firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})

# Flask Configuration
NOT_FOUND = 'Not found'
BAD_REQUEST = 'Bad request'
app = Flask(__name__)

# Gradio Configuration
MAX_HISTORY = 20
data_history = deque(maxlen=MAX_HISTORY)

# Sensor ID Mapping
SENSOR_IDS = {
    "MQ135_CO2": "-OMZ52hULVlcWp1HjY_3",
    "MQ2_Smoke": "-OMZ5FRWYXmtZDwXTIGk",
    "MQ7_CO": "-OMZ5H08E2DKCTkymTxS",
    "MQ9_Flammable": "-OMZ5JIY7Ap7CyNTOwSY",
    "Temperature": "-OMZ5LVfac6SqXCeQRW-",
    "Humidity": "-OMZ5Mnv-R5fWNH3v4Vl",
    "Wind_Speed": "-OMZ5OO8U2upkMfXPwWQ",
    "Fire_Probability": "-OMZ5SCV9iN5PHStzJMR"
}

# Data Storage
latest_data = {
    "MQ135_CO2": 0,
    "MQ2_Smoke": 0,
    "MQ7_CO": 0,
    "MQ9_Flammable": 0,
    "Temperature": 0,
    "Humidity": 0,
    "Wind_Speed": 0,
    "Fire_Probability": -1,  # -1 means unknown/camera disconnected
    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
}

# API routes
def _get_sensor(id, limit=20):
    sensor_ref = db.reference('/data').child(id)
    return sensor_ref.get()

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': NOT_FOUND}), 404)

@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': BAD_REQUEST}), 400)

@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    result = db.reference('/sensors').get()
    return jsonify(result), 200

@app.route('/api/sensors/<id>', methods=['GET'])
def get_sensor(id):
    sensor = _get_sensor(id)
    if not sensor:
        abort(404)
    return jsonify(sensor), 200

@app.route('/api/sensors', methods=['POST'])
def create_sensor():
    if not request.json or 'description' not in request.json or 'sensor_name' not in request.json:
        abort(400)
    
    description = request.json.get('description')
    sensor_name = request.json.get('sensor_name')
    
    sensor_info = {"sensor_name": sensor_name, "description": description}
    sensor_id = db.reference('/sensors').push(sensor_info).key
    return str(sensor_id), 201

@app.route('/api/sensors/<id>', methods=['PUT'])
def update_sensor(id):
    if not request.json:
        abort(400)
    
    # Print received data for debugging
    print(f"Received data for sensor ID {id}: {request.json}")
    
    # Update Firebase database
    entry_ref = db.reference('/data').child(id)
    data = request.json.copy()
    data['last_updated'] = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    entry_ref.set(data)
    
    # Find corresponding sensor name by ID
    sensor_name = None
    for name, sid in SENSOR_IDS.items():
        if sid == id:
            sensor_name = name
            break
    
    if sensor_name and 'value' in data:
        old_value = latest_data[sensor_name]
        latest_data[sensor_name] = data['value']
        latest_data['timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"Updated sensor {sensor_name} from {old_value} to {data['value']}")
        
        # Only add to history after receiving updates for all sensors
        # or when a significant time has passed since the last history entry
        add_to_history = False
        
        # Add to history if this is a fire probability update (camera status)
        if sensor_name == "Fire_Probability":
            add_to_history = True
            
        # Or add to history if we haven't added any entries yet
        if len(data_history) == 0:
            add_to_history = True
        
        # Or add to history if some time has passed
        time_threshold = 5  # seconds
        if len(data_history) > 0:
            try:
                last_update = datetime.datetime.strptime(data_history[-1]['timestamp'], "%Y-%m-%d %H:%M:%S")
                if (datetime.datetime.now() - last_update).total_seconds() > time_threshold:
                    add_to_history = True
            except:
                add_to_history = True
        
        if add_to_history:
            # Create a complete data record and add to history
            history_entry = latest_data.copy()
            data_history.append(history_entry)
            print(f"Added new history entry at {history_entry['timestamp']}")
        
        # Check fire risk if it's not directly from the camera
        if sensor_name != "Fire_Probability":
            check_fire_risk()
    else:
        if not sensor_name:
            print(f"WARNING: Received data for unknown sensor ID: {id}")
            print(f"Available sensor IDs: {SENSOR_IDS}")
        elif 'value' not in data:
            print(f"WARNING: Received data doesn't contain 'value' field: {data}")
    
    return jsonify({}), 200

@app.route('/api/sensors/<id>', methods=['DELETE'])
def delete_sensor(id):
    db.reference('/sensors').child(id).delete()
    db.reference('/data').child(id).delete()
    return jsonify({}), 204

@app.route('/api/debug', methods=['GET'])
def debug_data():
    """Endpoint to debug current data state"""
    # 定义阈值（与dashboard中的相同）
    thresholds = {
        "Temperature": {"high": 28, "unit": "°C"},
        "Humidity": {"low": 20, "unit": "%"},      # 改为20%
        "Wind_Speed": {"high": 1, "unit": "km/h"},
        "MQ135_CO2": {"high": 800, "unit": "ppm"},
        "MQ2_Smoke": {"high": 40, "unit": "ppm"},  # 改为40ppm
        "MQ7_CO": {"high": 4, "unit": "ppm"},
        "MQ9_Flammable": {"high": 0.8, "unit": "ppm"}
    }
    
    # 计算超过阈值的传感器数量
    warning_count = 0
    
    # 检查所有传感器的阈值
    for sensor_name, threshold in thresholds.items():
        value = latest_data[sensor_name]
        if ("high" in threshold and value > threshold["high"]) or \
           ("low" in threshold and value < threshold["low"]):
            warning_count += 1
    
    # 检查火灾概率
    fire_prob = latest_data["Fire_Probability"]
    if fire_prob != -1 and fire_prob > 0.2:  # 如果摄像头连接且火灾概率超过0.2
        warning_count += 1
    
    debug_info = {
        'latest_data': latest_data,
        'history_count': len(data_history),
        'history': list(data_history)[-5:] if data_history else [],
        'warnings': warning_count
    }
    return jsonify(debug_info), 200

@app.route('/dashboard')
def dashboard():
    """Simple HTML dashboard without Gradio"""
    latest = latest_data
    fire_prob = latest['Fire_Probability']
    fire_status = "Unknown"
    fire_color = "gray"
    camera_status = ""
    
    # 定义每个传感器的阈值
    thresholds = {
        "Temperature": {"high": 28, "unit": "°C"},
        "Humidity": {"low": 20, "unit": "%"},      # 改为20%
        "Wind_Speed": {"high": 1, "unit": "km/h"},
        "MQ135_CO2": {"high": 800, "unit": "ppm"},
        "MQ2_Smoke": {"high": 40, "unit": "ppm"},  # 改为40ppm
        "MQ7_CO": {"high": 4, "unit": "ppm"},
        "MQ9_Flammable": {"high": 0.8, "unit": "ppm"}
    }
    
    # 检查摄像头状态
    if fire_prob == -1:
        fire_status = "Camera Disconnected"
        fire_color = "gray"
        camera_status = "<span style='color: orange; font-size: 14px;'>(⚠️ Camera disconnected, visual flame detection unavailable)</span>"
    else:
        if fire_prob < 0.2:
            fire_status = "Safe"
            fire_color = "green"
        elif fire_prob < 0.5:
            fire_status = "Low Risk"
            fire_color = "orange"
        elif fire_prob < 0.7:
            fire_status = "Medium Risk"
            fire_color = "darkorange"
        else:
            fire_status = "High Risk"
            fire_color = "red"
    
    # 检查每个传感器值是否超过阈值的函数
    def check_threshold(sensor_name, value):
        if sensor_name not in thresholds:
            return False, ""
        
        threshold = thresholds[sensor_name]
        unit = threshold["unit"]
        
        if "high" in threshold and value > threshold["high"]:
            return True, f"⚠️ High: > {threshold['high']}{unit}"
        if "low" in threshold and value < threshold["low"]:
            return True, f"⚠️ Low: < {threshold['low']}{unit}"
        return False, ""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Forest Fire Monitoring System</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .dashboard {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; }}
            .card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .card h3 {{ margin: 0 0 10px 0; }}
            .value {{ font-size: 24px; font-weight: bold; margin: 0; }}
            .warning {{ color: red; font-size: 12px; margin-top: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 8px; text-align: left; border: 1px solid #ddd; }}
            th {{ background: #f2f2f2; }}
            tr:nth-child(even) {{ background: #f9f9f9; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔥 Forest Fire Monitoring Dashboard</h1>
            <p>Last updated: {latest['timestamp']}</p>
            
            <div class="dashboard">
    """
    
    # 生成每个传感器的卡片
    sensors_display = [
        ("Temperature", "#e74c3c", latest['Temperature']),
        ("Humidity", "#3498db", latest['Humidity']),
        ("Wind_Speed", "#2ecc71", latest['Wind_Speed']),
        ("MQ135_CO2", "#9b59b6", latest['MQ135_CO2']),
        ("MQ2_Smoke", "#f39c12", latest['MQ2_Smoke']),
        ("MQ7_CO", "#16a085", latest['MQ7_CO']),
        ("MQ9_Flammable", "#d35400", latest['MQ9_Flammable'])
    ]
    
    for sensor_name, color, value in sensors_display:
        is_warning, warning_text = check_threshold(sensor_name, value)
        value_color = "red" if is_warning else color
        unit = thresholds[sensor_name]["unit"]
        
        html += f"""
                <div class="card">
                    <h3 style="color: {color};">{sensor_name}</h3>
                    <p class="value" style="color: {value_color};">{value}{unit}</p>
                    <p class="warning">{warning_text}</p>
                </div>
        """
    
    # 添加系统状态和火灾检测卡片
    html += f"""
                <div class="card">
                    <h3 style="color: #e67e22;">System Status</h3>
                    <p class="value">Active</p>
                </div>
                
                <div class="card">
                    <h3 style="color: {fire_color};">Fire Visual Detection {camera_status}</h3>
                    <p class="value" style="color: {fire_color};">
                        {fire_status} {'' if fire_prob == -1 else f'({fire_prob:.2f})'}
                    </p>
                </div>
            </div>

            <h2>History (Latest {len(data_history)} records)</h2>
            <table>
                <tr>
                    <th>Time</th>
                    <th>Temperature</th>
                    <th>Humidity</th>
                    <th>Wind</th>
                    <th>Fire Detection</th>
                </tr>
                """
    
    # Add history rows
    for d in list(data_history)[::-1]:  # Reverse display, newest first
        fire_color = 'gray'
        if d['Fire_Probability'] != -1:
            if d['Fire_Probability'] < 0.2:
                fire_color = 'green'
            elif d['Fire_Probability'] < 0.5:
                fire_color = 'orange'
            elif d['Fire_Probability'] < 0.7:
                fire_color = 'darkorange'
            else:
                fire_color = 'red'
        
        fire_status = 'Camera Disconnected'
        if d['Fire_Probability'] != -1:
            if d['Fire_Probability'] < 0.2:
                fire_status = 'Safe'
            elif d['Fire_Probability'] < 0.5:
                fire_status = 'Low Risk'
            elif d['Fire_Probability'] < 0.7:
                fire_status = 'Medium Risk'
            else:
                fire_status = 'High Risk'
        
        status_display = fire_status
        if d['Fire_Probability'] != -1:
            status_display += f" ({d['Fire_Probability']:.2f})"
        
        html += f"""
                <tr>
                    <td>{d['timestamp']}</td>
                    <td>{d['Temperature']}°C</td>
                    <td>{d['Humidity']}%</td>
                    <td>{d['Wind_Speed']} km/h</td>
                    <td style="color: {fire_color};">{status_display}</td>
                </tr>
        """
    
    html += """
            </table>
            
            <div style="margin-top: 20px; text-align: center;">
                <p>Edge-Fog-Cloud IoT System for Environmental Monitoring</p>
            </div>
        </div>
        
        <script>
            // Simple JavaScript to highlight values that change
            document.addEventListener('DOMContentLoaded', function() {
                // Future enhancement: Add animations for changing values
            });
        </script>
    </body>
    </html>
    """
    
    return html

# Add favicon route to avoid 404 errors
@app.route('/favicon.ico')
def favicon():
    return "", 204  # Return no content status code

# Make root redirect to dashboard
@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Forest Fire Monitoring System</title>
        <meta http-equiv="refresh" content="0;URL='/dashboard'" />
    </head>
    <body>
        <p>Redirecting to dashboard...</p>
    </body>
    </html>
    """

# Fire risk assessment
def check_fire_risk():
    # 不再需要计算风险分数，只记录当前传感器值用于调试
    print(f"Current sensor values:")
    for key, value in latest_data.items():
        if key != 'timestamp':
            print(f"  {key}: {value}")
    
    # 如果摄像头断开（Fire_Probability = -1），保持该值
    # 否则不做任何修改，保持摄像头发送的原始概率值
    if latest_data["Fire_Probability"] == -1:
        print("Camera is disconnected, keeping Fire_Probability as -1")
    else:
        print(f"Using camera's fire probability: {latest_data['Fire_Probability']:.2f}")

if __name__ == '__main__':
    print("Starting Forest Fire Monitoring System...")
    print("Dashboard will be available at: http://localhost:50000/dashboard")
    print("API endpoints available at: http://localhost:50000/api/*")
    # Start the Flask app with debug mode off for production use
    app.run(host='0.0.0.0', port=50000, debug=False) 