import json
import os
import re
import requests
from bs4 import BeautifulSoup

# --- 基本設定區 ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CACHE_FILE = "known_products.json"

# 使用搜尋頁面路徑，Shopline 搜尋頁會把商品直接打包在 HTML 的 JS 資料中
SEARCH_URL = "https://shop.funbox.com.tw/products?query=戰鬥陀螺"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
}


def send_discord(title, link, price, notice_type="新品上架"):
    if not DISCORD_WEBHOOK_URL:
        print("未設定 DISCORD_WEBHOOK_URL，跳過推播。")
        return

    color = 3066993 if notice_type == "現貨補貨" else 15844367

    embed = {
        "title": f"【Funbox 官網 - {notice_type}】{title}",
        "url": link,
        "color": color,
        "fields": [
            {"name": "狀態", "value": "🔥 現貨可購買！", "inline": True},
            {"name": "售價", "value": price or "請見頁面", "inline": True},
        ],
        "footer": {"text": "Funbox 戰鬥陀螺雷達"},
    }

    payload = {
        "username": "Funbox 戰鬥陀螺雷達",
        "embeds": [embed],
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print(f"成功發送通知：{title} ({notice_type})")
    except Exception as e:
        print(f"發送 Discord 失敗: {e}")


def load_known_products():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {url: False for url in data}
            return data
    except Exception:
        return {}


def save_known_products(products_dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(products_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"寫入快取失敗: {e}")


def check_funbox(known_products, current_round):
    print("正在請求 Funbox 官網搜尋資料...")
    try:
        resp = requests.get(SEARCH_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html_text = resp.text
    except Exception as e:
        print(f"網頁請求失敗: {e}")
        return

    # 1. 先用正規表達式直接從整個 HTML 原始碼中尋找所有商品 ID 與 Handle
    # Shopline 典型路徑：/products/64xxxxxx 或 /products/beyblade-xxx
    product_matches = re.findall(r'href=["\'](/products/[a-zA-Z0-9\-_]+)["\']', html_text)
    product_handles = set(product_matches)

    print(f"HTML 正則匹配到的商品網址數: {len(product_handles)}")

    # 2. 如果頁面採用 JSON 注入（例如 window.__INITIAL_STATE__）
    json_products = []
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL)
    for sc in scripts:
        if "products" in sc and ("price" in sc or "title" in sc):
            # 尋找 JSON 物件字串
            objs = re.findall(r'(\{"_id":.*?"title":.*?\})', sc)
            if objs:
                json_products.extend(objs)

    print(f"內嵌 Script 提取到的商品數量: {len(json_products)}")

    # 3. 逐一處理抓到的商品網址
    for handle_path in product_handles:
        link = f"https://shop.funbox.com.tw{handle_path}"
        current_round[link] = True

        if link not in known_products:
            # 取得商品標題簡述
            send_discord("戰鬥陀螺新品", link, "請進頁面查看", notice_type="新品上架")
        else:
            if not known_products.get(link, False):
                send_discord("戰鬥陀螺補貨", link, "請進頁面查看", notice_type="現貨補貨")

    # 4. 如果正則與 Script 均未抓到，印出除錯標籤
    if not product_handles and not json_products:
        print("未抓到任何商品元素，嘗試印出網頁前 500 字元供排查：")
        print(html_text[:500])


def main():
    known_products = load_known_products()
    current_round = {}

    check_funbox(known_products, current_round)

    known_products.update(current_round)
    save_known_products(known_products)
    print("檢查結束。")


if __name__ == "__main__":
    main()
