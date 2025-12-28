import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
from notion_client import Client

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --- 環境變數設定 ---
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

# --- 這裡先設定一個預設模型，避免變數沒定義 ---
model = genai.GenerativeModel('gemini-2.5-flash') 

def process_text_with_gemini(user_text):
    """
    使用 Gemini 將輸入整理成結構化資料
    """
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
        if "|||" in response.text:
            parts = response.text.split("|||")
            if len(parts) >= 3:
                return parts[0].strip(), parts[1].strip(), parts[2].strip()
        return "新筆記", "筆記", user_text
    except Exception as e:
        app.logger.error(f"Gemini Error: {e}")
        # 如果失敗，回傳錯誤原因讓你知道
        return "Error Note", "錯誤", str(e)

def save_to_notion(title, tag, content):
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
        return response['url']
    except Exception as e:
        app.logger.error(f"Notion Error: {e}")
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip() # 去除前後空白

    # === 🕵️‍♂️ 密技指令區：輸入 "debug" 就會執行這段 ===
    if user_msg.lower() == "debug":
        reply_text = "🔍 正在查詢可用模型...\n"
        try:
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
                    # 也順便印到 Log 裡給你備查
                    app.logger.info(f"Find Model: {m.name}")
            
            if available_models:
                reply_text += "✅ 找到以下模型：\n" + "\n".join(available_models)
            else:
                reply_text += "⚠️ 沒有找到任何支援 generateContent 的模型"
                
        except Exception as e:
            reply_text += f"❌ 查詢失敗: {str(e)}"
            app.logger.error(f"List Models Error: {e}")

        # 直接回傳給使用者
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return # 結束，不繼續執行後面的 Notion 存檔
    # =================================================

    # 正常的筆記流程
    title, tag, content = process_text_with_gemini(user_msg)
    notion_url = save_to_notion(title, tag, content)
    
    if notion_url:
        reply = f"✅ 已存入 Notion\n📌 [{tag}] {title}\n\n{content}\n\n🔗 {notion_url}"
    else:
        reply = f"❌ 寫入 Notion 失敗\nGemini 回應: {content}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(port=5000, debug=True)