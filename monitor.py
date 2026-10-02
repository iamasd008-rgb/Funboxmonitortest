import json
import os
import requests

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CACHE_FILE = "known_products.json"

# Cyberbiz 分類資料的標準 JSON 端點
TARGET_JSON_URL = "https://shop.funbox.com.tw/categories/takaratomy/beyblade.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
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
            {"name": "售價", "value": price or "請見頁面", "inline": True},
        ],
        "footer": {"text": "Funbox 戰鬥陀螺雷達 (Cyberbiz)"},
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
    print("正在請求 Cyberbiz 分類 JSON 數據...")
    try:
        resp = requests.get(TARGET_JSON_URL, headers=HEADERS, timeout=15)
        print(f"回應狀態碼: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"讀取分類 JSON 失敗: {e}")
        return

    # Cyberbiz 的商品清單通常存放在 products 陣列中
    products = data.get("products", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    print(f"取得商品總數: {len(products)}")

    for item in products:
        title = item.get("title") or item.get("name", "未命名商品")
        handle = item.get("handle") or str(item.get("id", ""))
        link = f"https://shop.funbox.com.tw/products/{handle}" if handle else "https://shop.funbox.com.tw"

        # 庫存判斷：available 或 variants 內的 available 旗標
        has_stock = item.get("available", True)
        if "variants" in item and item["variants"]:
            has_stock = any(v.get("available", False) for v in item["variants"])

        # 售價提取
        price_val = item.get("price") or item.get("price_min")
        price = f"NT$ {price_val}" if price_val else ""

        print(f"成功解析: {title} | 現貨: {has_stock} | 連結: {link}")
        current_round[link] = has_stock

        if link not in known_products:
            if has_stock:
                send_discord(title, link, price, notice_type="新品上架")
        else:
            if not known_products.get(link, False) and has_stock:
                send_discord(title, link, price, notice_type="現貨補貨")


def main():
    known_products = load_known_products()
    current_round = {}

    check_funbox(known_products, current_round)

    known_products.update(current_round)
    save_known_products(known_products)
    print("檢查完成。")


if __name__ == "__main__":
    main()
