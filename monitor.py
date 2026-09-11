import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

# --- 基本設定區 ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CACHE_FILE = "known_products.json"

# 1. Funbox 官網設定
FUNBOX_URL = "https://shop.funbox.com.tw/categories/takaratomy/beyblade"

# 2. 蝦皮商城設定 (fun box 玩具旗艦館)
SHOPEE_SHOP_ID = "285705541"
SHOPEE_API_URL = f"https://shopee.tw/api/v4/shop/search_items?shopid={SHOPEE_SHOP_ID}&limit=30&offset=0&keyword=戰鬥陀螺"

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

SHOPEE_HEADERS = {
    **COMMON_HEADERS,
    "Referer": f"https://shopee.tw/shop/{SHOPEE_SHOP_ID}/search?keyword=%E6%88%B0%E9%87%98%E9%99%80%E8%9E%BA",
    "x-requested-with": "XMLHttpRequest",
    "af-ac-enc-dat": "",
}


def send_discord(title, link, price, source_name="Funbox 官網", notice_type="新品上架"):
    if not DISCORD_WEBHOOK_URL:
        print("未設定 DISCORD_WEBHOOK_URL，跳過推播。")
        return

    # 補貨為綠色，新品為橘金色
    color = 3066993 if notice_type == "現貨補貨" else 15844367

    embed = {
        "title": f"【{source_name} - {notice_type}】{title}",
        "url": link,
        "color": color,
        "fields": [
            {"name": "狀態", "value": "🔥 現貨可購買！", "inline": True},
            {"name": "售價", "value": price or "請見頁面", "inline": True},
        ],
        "footer": {"text": f"{source_name} 自動監控通知"},
    }

    payload = {
        "username": "Funbox 戰鬥陀螺雷達",
        "embeds": [embed],
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print(f"成功發送通知 [{source_name}]：{title} ({notice_type})")
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
    except Exception as e:
        print(f"讀取快取失敗: {e}")
        return {}


def save_known_products(products_dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(products_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"寫入快取失敗: {e}")


def check_official(known_products, current_round):
    print("正在巡邏 Funbox 官網...")
    try:
        resp = requests.get(FUNBOX_URL, headers=COMMON_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"官網請求失敗: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select(".box, .product-item, [class*='ProductItem']") or soup.select("a[href*='/products/']")

    for card in cards:
        link_elem = card if card.name == "a" else card.select_one("a[href*='/products/']")
        if not link_elem or not link_elem.get("href"):
            continue

        raw_link = link_elem["href"]
        link = raw_link if raw_link.startswith("http") else f"https://shop.funbox.com.tw{raw_link}"
        link = link.split("?")[0]

        title = link_elem.get_text(strip=True)
        text = card.get_text(separator=" ", strip=True)

        price_match = re.search(r"NT\$\s*[\d,]+", text)
        price = price_match.group(0) if price_match else ""

        is_sold_out = any(k in text for k in ["售完", "補貨中", "缺貨", "售罄", "Sold Out"])
        has_stock = not is_sold_out

        current_round[link] = has_stock

        if link not in known_products:
            if has_stock:
                send_discord(title, link, price, source_name="Funbox 官網", notice_type="新品上架")
        else:
            if not known_products.get(link, False) and has_stock:
                send_discord(title, link, price, source_name="Funbox 官網", notice_type="現貨補貨")


def check_shopee(known_products, current_round):
    print("正在巡邏 Funbox 蝦皮商城...")
    try:
        resp = requests.get(SHOPEE_API_URL, headers=SHOPEE_HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"蝦皮 API 請求未成功，狀態碼: {resp.status_code}")
            return
        data = resp.json()
    except Exception as e:
        print(f"蝦皮請求失敗: {e}")
        return

    items = data.get("data", {}).get("items", [])
    if not items:
        print("蝦皮未搜尋到相關商品或 API 回傳為空。")
        return

    for item in items:
        item_basic = item.get("item_basic", {})
        item_id = item_basic.get("itemid")
        shop_id = item_basic.get("shopid")
        name = item_basic.get("name", "")
        stock = item_basic.get("stock", 0)

        raw_price = item_basic.get("price", 0)
        price = f"NT$ {int(raw_price / 100000)}" if raw_price else ""

        if not item_id:
            continue

        link = f"https://shopee.tw/product/{shop_id}/{item_id}"
        has_stock = stock > 0
        current_round[link] = has_stock

        if link not in known_products:
            if has_stock:
                send_discord(name, link, price, source_name="Funbox 蝦皮", notice_type="新品上架")
        else:
            if not known_products.get(link, False) and has_stock:
                send_discord(name, link, price, source_name="Funbox 蝦皮", notice_type="現貨補貨")


def main():
    known_products = load_known_products()
    current_round = {}

    check_official(known_products, current_round)
    time.sleep(2)
    check_shopee(known_products, current_round)

    known_products.update(current_round)
    save_known_products(known_products)
    print("全部監控檢查完成，資料庫已更新。")


if __name__ == "__main__":
    main()
