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

# 改用最穩定的 pro 模型
model = genai.GenerativeModel('gemini-2.5-flash')

def process_intent_with_gemini(user_text):
    """
    讓 Gemini 判斷這是「聊天」還是「筆記」，並回傳對應格式
    """
    prompt = f"""
    你是一個聰明的個人助理。請分析使用者的輸入，判斷他的意圖是「純聊天」還是「想要紀錄事情」。

    使用者輸入: "{user_text}"

    請嚴格遵守以下兩種回傳格式之一（不要有額外的 Markdown 符號）：

    情況一：如果是閒聊、問知識、打招呼 (例如：你好、解釋量子力學、講個笑話)
    回傳格式：
    CHAT|||這裡放你對使用者的友善回應

    情況二：如果是想要紀錄、待辦事項、備忘錄 (例如：提醒我買牛奶、紀錄今天開會重點、記帳)
    回傳格式：
    SAVE|||標題|||標籤|||詳細內文

    關於 SAVE 格式的規則：
    1. 標題：簡短扼要
    2. 標籤：從 [待辦, 筆記, 學校, 靈感, 購物, 財務] 選一個最適合的
    3. 詳細內文：請將使用者的輸入整理成條列式或詳細說明，放在這裡。
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # 簡單防呆：確保回傳格式正確
        if "|||" in text:
            return text.split("|||")
        else:
            # 如果格式跑掉，預設當作聊天回應
            return ["CHAT", text]
            
    except Exception as e:
        app.logger.error(f"Gemini Error: {e}")
        return ["CHAT", "抱歉，我現在有點秀逗，請稍後再試。"]

def save_to_notion(title, tag, content):
    """
    寫入 Notion：標題與標籤在欄位，詳細內容在頁面內文
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
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "詳細筆記內容"}}]
                    }
                },
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
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    # 1. 呼叫 Gemini 進行意圖判斷
    result = process_intent_with_gemini(user_msg)
    
    # 取出判斷結果 (Action)
    action = result[0].strip().upper()
    
    if action == "SAVE" and len(result) >= 4:
        # --- 進入存檔流程 ---
        title = result[1].strip()
        tag = result[2].strip()
        content = result[3].strip()
        
        notion_url = save_to_notion(title, tag, content)
        
        if notion_url:
            reply_text = f"✅ 已幫你紀錄！\n\n📌 標題：{title}\n🏷️ 標籤：{tag}\n📝 內容：{content}\n\n🔗 連結：{notion_url}"
        else:
            reply_text = "❌ 寫入 Notion 失敗，請檢查 Log。"
            
    elif action == "CHAT":
        # --- 進入聊天流程 ---
        # result[1] 就是 Gemini 的回應內容
        reply_text = result[1].strip() if len(result) > 1 else "（沈默）"
        
    else:
        # --- 格式無法辨識時的備案 ---
        reply_text = result[-1] # 直接把最後一段文字回傳

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(port=5000, debug=True)