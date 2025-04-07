from flask import Flask, request, jsonify
from paddleocr import PaddleOCR
import cv2
import re
import os
import requests
import json
import tempfile
import base64
from PIL import Image
from io import BytesIO

AK = "WHVtloyHoHqAcqZdSLDV0CnltomCPKDZ"
ocr = PaddleOCR(use_angle_cls=True, lang="ch")

app = Flask(__name__)

def get_position(address):
    url = f"http://api.map.baidu.com/place/v2/search?query={address}&region=全国&output=json&ak={AK}"
    res = requests.get(url)
    json_data = json.loads(res.text)
    if json_data["status"] == 0:
        lat = json_data["results"][0]["location"]["lat"]
        lng = json_data["results"][0]["location"]["lng"]
        return f"{lat},{lng}", 0
    else:
        return "0,0", json_data["status"]

def get_distance(start, end):
    url = f"https://api.map.baidu.com/directionlite/v1/driving?origin={start}&destination={end}&ak={AK}"
    res = requests.get(url)
    json_data = json.loads(res.text)
    if json_data["status"] == 0:
        return json_data["result"]["routes"][0]["distance"] / 1000
    else:
        return -1

@app.route('/ocr_route', methods=['POST'])
def ocr_route():
    try:
        img_base64 = request.json.get("image_base64")
        if not img_base64:
            return jsonify({"error": "缺少 image_base64 参数"}), 400

        image_data = base64.b64decode(img_base64.split(",")[-1])
        img = Image.open(BytesIO(image_data))
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            img_path = tmp.name
            img.save(img_path)
        
        cv_img = cv2.imread(img_path)
        cropped_img = cv_img[:2300, :]
        cropped_path = img_path.replace(".jpg", "_cropped.jpg")
        cv2.imwrite(cropped_path, cropped_img)
        result = ocr.ocr(cropped_path, cls=True)

        text_list = [word[1][0] for line in result for word in line]
        full_text = " ".join(text_list)

        driver_name = re.search(r"(\S+)", full_text)
        date_time_match = re.search(r"(\d{4}\.\d{2}\.\d{2})\s*(\d{2}:\d{2})", full_text)
        date_time_str = f"{date_time_match.group(1)} {date_time_match.group(2)}" if date_time_match else "未匹配"
        distance = re.search(r"(\d+(?:\.\d+)?)\s*km(?!/h)", full_text)
        duration = re.search(r"(\d+:\d+:\d+)", full_text)
        speed_matches = re.findall(r"(\d+)\s*km/h", full_text)
        avg_speed = min(map(int, speed_matches)) if speed_matches else None
        max_speed = max(map(int, speed_matches)) if speed_matches else None
        locations = re.findall(r"([\u4e00-\u9fa5]+(?:（.*?）)?)", full_text)
        start_location = locations[-2] if len(locations) >= 2 else ""
        end_location = locations[-1] if len(locations) >= 2 else ""

        if not distance:
            start_coords, status1 = get_position(start_location)
            end_coords, status2 = get_position(end_location)
            if status1 == 0 and status2 == 0:
                calculated_distance = get_distance(start_coords, end_coords)
                distance_value = f"{calculated_distance:.2f} km" if calculated_distance >= 0 else "计算失败"
            else:
                distance_value = "地址解析失败"
        else:
            distance_value = distance.group(1)

        data = {
            "驾驶人": driver_name.group(1) if driver_name else None,
            "日期时间": date_time_str,
            "出发地": start_location,
            "目的地": end_location,
            "行驶里程": distance_value,
            "驾驶时长": duration.group(1) if duration else None,
            "平均速度": avg_speed,
            "最快速度": max_speed,
        }

        if all(data.values()):
            return jsonify({"status": "success", "data": data})
        else:
            return jsonify({"status": "partial", "data": data, "message": "部分信息未识别完整"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
