import json
import time
import requests
import csv
import os
from datetime import datetime, timezone
from dateutil import parser
from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, async_mode='threading')

# 설정 로드
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

BASE_URL = config['base_url']
POLLING_INTERVAL = config['polling_interval']
TIMEOUT_LIMIT = config.get('timeout_limit_seconds', 20) # 💡 콘피그에서 제한 시간 로드

# CSV 로드 (인코딩 자동 감지)
sensor_meta = {}
csv_path = 'sensors.csv'
for enc in ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']:
    try:
        if os.path.exists(csv_path):
            with open(csv_path, 'r', encoding=enc) as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) > 8 and row[8].strip().isdigit():
                        tid = int(row[8].strip())
                        sensor_meta[tid] = {
                            "date": row[0].strip(), 
                            "provider": row[1].strip(), 
                            "alias": row[4].strip(), 
                            "location": row[5].strip(), 
                            "notes": row[6].strip()
                        }
            print(f"✅ CSV 메타데이터 로드 성공 (인코딩: {enc})")
            break
    except: 
        continue

THINGS = list(sensor_meta.keys())

def fetch_and_process_data():
    while True:
        sensor_data = {}
        now = datetime.now(timezone.utc)

        for thing_id in THINGS:
            tid_str = str(thing_id)
            url = f"{BASE_URL}/Things({thing_id})?$expand=Locations,MultiDatastreams($expand=ObservedProperties,Observations($orderby=phenomenonTime desc;$top=100))"
            meta = sensor_meta.get(thing_id, {})
            
            try:
                response = requests.get(url, timeout=5)
                data = response.json()
                
                mds_list = data.get('MultiDatastreams', [])
                if not mds_list: continue

                mds = mds_list[0]
                observations = mds.get('Observations', [])
                if not observations: continue

                # 1. 최근 100개 데이터 기준 평균 주기 계산
                times = [parser.parse(obs['phenomenonTime'].split('/')[0]) for obs in observations]
                avg_delta = 60
                if len(times) >= 2:
                    deltas = [(times[i] - times[i+1]).total_seconds() for i in range(len(times)-1)]
                    avg_delta = max(sum(deltas) / len(deltas), 1)

                # 2. 측정 후 경과 시간 및 남은 시간 도출
                last_time = times[0]
                data_age = int((now - last_time).total_seconds())
                remaining_seconds = int(avg_delta - data_age)

                # 3. 콘피그 제한 초를 넘었을 때만 백엔드 status를 timeout으로 변경
                status = "normal"
                if remaining_seconds <= -TIMEOUT_LIMIT:
                    status = "timeout"

                # 4. 구조화 데이터 바인딩
                details = []
                obs_props = mds.get('ObservedProperties', [])
                units = mds.get('unitOfMeasurements', [])
                latest_result = observations[0]['result']
                
                for idx, val in enumerate(latest_result):
                    prop = obs_props[idx]['name'] if idx < len(obs_props) else f"Prop {idx}"
                    unit = units[idx]['symbol'] if idx < len(units) else ""
                    details.append({"property": prop, "unit": unit, "result": val})

                sensor_data[tid_str] = {
                    "alias": meta.get('alias', data.get('name')),
                    "csv_location": meta.get('location', '-'),
                    "provider": meta.get('provider', '-'),
                    "date": meta.get('date', '-'),
                    "frost_name": data.get('name'),
                    "frost_location": data.get('Locations')[0].get('name') if data.get('Locations') else '-',
                    "notes": meta.get('notes', ''),
                    "status": status,
                    "preview": latest_result[:2],
                    "details": details,
                    "last_update": last_time.isoformat(),
                    "remaining_seconds": remaining_seconds,
                    "data_age": data_age,
                    "timeout_limit": TIMEOUT_LIMIT # 💡 프론트엔드로 제한 초 전달
                }
            except Exception as e:
                print(f"❌ Error Thing {thing_id}: {e}")
                sensor_data[tid_str] = {
                    "alias": meta.get('alias', f"Thing {thing_id} (오프라인)"),
                    "csv_location": meta.get('location', '-'),
                    "provider": meta.get('provider', '-'),
                    "date": meta.get('date', '-'),
                    "frost_name": "Error",
                    "frost_location": "Error",
                    "notes": meta.get('notes', '서버 통신 에러가 발생했습니다.'),
                    "status": "error",
                    "preview": [], "details": [], "last_update": "No Data",
                    "remaining_seconds": 0, "data_age": 0, "timeout_limit": TIMEOUT_LIMIT
                }

        socketio.emit('sensor_update', sensor_data)
        time.sleep(POLLING_INTERVAL)

@app.route('/')
def index(): 
    return render_template('index.html')

if __name__ == '__main__':
    socketio.start_background_task(fetch_and_process_data)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)