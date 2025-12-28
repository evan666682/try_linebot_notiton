import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextMessage, TextSendMessage
import google.generativeai as genai
from notion_client import Client

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --- 環境變數設定 ---
# 請確保這些變數在 Render 或 .env 檔案中都已設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')

# --- 初始化 ---
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
genai.configure(api_key=GEMINI_API_KEY)
notion = Client(auth=NOTION_API_KEY)

def process_text_with_gemini(user_text):
    """
    使用 Gemini 將輸入整理成結構化資料 (標題、標籤、內文)
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    你是一個個人助理。請將使用者的輸入整理成 Notion 筆記格式。
    使用者輸入: "{user_text}"
    
    請嚴格依照以下格式回傳，用 "|||" 分隔三個部分：
    標題|||標籤|||詳細內文
    
    規則：
    1. 標籤請從這幾個選一個最適合的：[待辦, 筆記, 學校, 靈感, 購物]
    2. 內文請整理成易讀的格式
    
    範例輸入: 明天要交VLSI作業，還要記得買牛奶
    範例輸出: 繳交作業與購物|||待辦|||- 完成 VLSI 作業\n- 購買牛奶
    """
    try:
        response = model.generate_content(prompt)
        # 簡單的防呆機制，確保格式正確
        if "|||" in response.text:
            parts = response.text.split("|||")
            if len(parts) >= 3:
                return parts[0].strip(), parts[1].strip(), parts[2].strip()
        
        # 如果格式跑掉，就當作一般筆記
        return "新筆記", "筆記", user_text
    except Exception as e:
        app.logger.error(f"Gemini Error: {e}")
        return "Error Note", "錯誤", str(e)

def save_to_notion(title, tag, content):
    """
    呼叫 Notion API 建立新 Page
    """
    try:
        response = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "Title": {"title": [{"text": {"content": title}}]},
                "Tag": {"multi_select": [{"name": tag}]}
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                }
            ]
        )
        return response['url'] # 回傳 Notion 頁面連結
    except Exception as e:
        app.logger.error(f"Notion Error: {e}")
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(TextMessage)
def handle_message(event):
    user_msg = event.message.text
    
    # 1. 讓 Gemini 思考並整理
    title, tag, content = process_text_with_gemini(user_msg)
    
    # 2. 寫入 Notion
    notion_url = save_to_notion(title, tag, content)
    
    if notion_url:
        reply = f"✅ 已存入 Notion\n📌 [{tag}] {title}\n\n{content}\n\n🔗 {notion_url}"
    else:
        reply = "❌ 寫入 Notion 失敗，請檢查 Log。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(port=5000, debug=True)