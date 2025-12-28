import requests
import json

# ==========================================
# 請貼上你的 GAS 部署網址
# ==========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbwf0W4IDiCgfx9h-uFpJbFQpRqtaMNIR_VtxLpAWsKbQ8Kt7ia1L7IpwXbT0I7ICmnh-Q/exec" 

# 準備要傳送的測試資料
payload = {
    "title": "API 測試筆記",
    "content": "這是透過 Python POST 發送的測試內容。"
}

print(f"正在發送請求到: {GAS_URL} ...")

try:
    # 發送 POST 請求
    # 因為 GAS 重新導向的特性，這是正常的 HTTP 行為
    response = requests.post(GAS_URL, json=payload, allow_redirects=True)
    
    # 印出結果
    print("\n--- 伺服器回傳 ---")
    print(response.text)
    
    # 嘗試解析回傳的 JSON
    try:
        data = response.json()
        if data.get("status") == "success":
            print("\n✅ 測試成功！請去 Google Keep 檢查有沒有多出一張筆記！")
        else:
            print("\n❌ 測試失敗 (GAS 內部錯誤):")
            print(f"錯誤訊息: {data.get('message')}")
    except:
        pass

except Exception as e:
    print(f"\n❌ 連線錯誤: {e}")