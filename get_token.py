import gpsoauth

# ==========================================
# 請在這裡填入你的 Google 資訊
# ==========================================
email = 'evan666682@gmail.com'

# ⚠️ 注意：如果你有開啟兩步驟驗證，這裡不能填原本的登入密碼
# 必須去 Google 帳戶設定 -> 安全性 -> 應用程式密碼 (App Password) 產生一組給它用
# 應用程式密碼通常是 16 碼英文，例如 'abcdefghijklmnop'
password = 'ncjzvhhnsxnugwkm' 

android_id = '1234567890abc123' # 這個不用改，維持原樣即可
# ==========================================

print("正在嘗試登入...")
response = gpsoauth.perform_master_login(email, password, android_id)

if 'Token' in response:
    print("\n✅ 成功！請複製下面的 Master Token：\n")
    print(response['Token'])
    print("\n(這串 Token 等一下要貼到 Render 的環境變數 KEEP_MASTER_TOKEN)")
else:
    print("\n❌ 失敗，請檢查錯誤訊息：")
    print(response)