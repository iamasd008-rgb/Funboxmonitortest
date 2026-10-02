import json
import os
import re
import requests

# --- 基本設定區 ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CACHE_FILE = "known_products.json"

# Funbox 官網 API 接口 (TAKARA TOMY 戰鬥陀螺專區)
# 透過 Shopline 後端 API 直接取得商品列表資料
API_URL = "https://shop.funbox.com.tw/api/products"
API_PARAMS = {
    "category": "takaratomy/beyblade",
    "page": 1,
    "limit": 50,
    "sort_by": "created_at",
    "order": "desc"
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://shop.funbox.com.tw/categories/takaratomy/beyblade",
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
            {"name": "售價", "value": price or "請見官網", "inline": True},
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
    print("正在請求 Funbox 官網商品數據...")
    try:
        resp = requests.get(API_URL, params=API_PARAMS, headers=HEADERS, timeout=15)
        # 若 API 端點結構不同則嘗試直接抓分類頁 JSON-LD
        if resp.status_code != 200:
            print(f"API 回傳狀態碼: {resp.status_code}，切換備用解析機制...")
            check_funbox_fallback(known_products, current_round)
            return
        data = resp.json()
    except Exception as e:
        print(f"請求 API 發生錯誤: {e}，切換備用機制...")
        check_funbox_fallback(known_products, current_round)
        return

    items = data.get("products") or data.get("data") or []
    print(f"成功取得商品數量: {len(items)}")

    for item in items:
        title = item.get("title") or item.get("name", "")
        handle = item.get("handle") or item.get("id", "")
        link = f"https://shop.funbox.com.tw/products/{handle}" if handle else "https://shop.funbox.com.tw"

        # 庫存判斷
        has_stock = item.get("has_stock", True)
        if "quantity" in item and item["quantity"] <= 0:
            has_stock = False

        price_val = item.get("price") or item.get("regular_price") or ""
        price = f"NT$ {price_val}" if price_val else ""

        print(f"解析到商品: {title} | 現貨: {has_stock}")
        current_round[link] = has_stock

        if link not in known_products:
            if has_stock:
                send_discord(title, link, price, notice_type="新品上架")
        else:
            if not known_products.get(link, False) and has_stock:
                send_discord(title, link, price, notice_type="現貨補貨")


def check_funbox_fallback(known_products, current_round):
    """備用方案：抓取網頁原始碼內嵌入的商品 JSON 資料"""
    fallback_url = "https://shop.funbox.com.tw/categories/takaratomy/beyblade"
    try:
        resp = requests.get(fallback_url, headers=HEADERS, timeout=15)
        html = resp.text
        # 從 HTML 提取 window.__INITIAL_STATE__ 或 ld+json
        json_matches = re.findall(r'<script type="application/ld\+json">({.*?})</script>', html, re.DOTALL)
        count = 0
        for raw in json_matches:
            try:
                js = json.loads(raw)
                if js.get("@type") == "Product":
                    title = js.get("name", "")
                    link = js.get("url", fallback_url)
                    offers = js.get("offers", {})
                    avail = offers.get("availability", "")
                    has_stock = "InStock" in avail
                    price = f"NT$ {offers.get('price', '')}"

                    count += 1
                    current_round[link] = has_stock
                    print(f"[備用] 發現商品: {title} | 現貨: {has_stock}")

                    if link not in known_products:
                        if has_stock:
                            send_discord(title, link, price, notice_type="新品上架")
                    else:
                        if not known_products.get(link, False) and has_stock:
                            send_discord(title, link, price, notice_type="現貨補貨")
            except Exception:
                continue
        print(f"備用方案解析完成，找到 {count} 筆商品。")
    except Exception as e:
        print(f"備用方案抓取失敗: {e}")


def main():
    known_products = load_known_products()
    current_round = {}

    check_funbox(known_products, current_round)

    known_products.update(current_round)
    save_known_products(known_products)
    print("檢查流程結束，快取已更新。")


if __name__ == "__main__":
    main()
