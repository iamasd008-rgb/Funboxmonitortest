import json
import os
import re
import requests
from bs4 import BeautifulSoup

TARGET_URL = "https://shop.funbox.com.tw/categories/takaratomy/beyblade"
CACHE_FILE = "known_products.json"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


def send_discord(title, link, price, notice_type="新品上架"):
    if not DISCORD_WEBHOOK_URL:
        print("未設定 DISCORD_WEBHOOK_URL，跳過通知。")
        return

    # 補貨用亮綠色，新品用橘金色
    color = 3066993 if notice_type == "現貨補貨" else 15844367

    embed = {
        "title": f"【{notice_type}】{title}",
        "url": link,
        "color": color,
        "fields": [
            {"name": "狀態", "value": "🔥 現貨可購買！", "inline": True},
            {"name": "售價", "value": price or "請見官網", "inline": True},
        ],
        "footer": {"text": "Funbox 戰鬥陀螺雷達 (補貨與新品監控)"},
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
            # 相容舊版陣列格式
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


def check_funbox():
    print("正在檢查 Funbox 戰鬥陀螺專區...")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"抓取網頁失敗: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    known_products = load_known_products()
    current_products = {}

    product_cards = soup.select(".box, .product-item, [class*='ProductItem']")
    if not product_cards:
        product_cards = soup.select("a[href*='/products/']")

    for card in product_cards:
        link_elem = card if card.name == "a" else card.select_one("a[href*='/products/']")
        if not link_elem:
            continue

        raw_link = link_elem.get("href", "")
        if not raw_link:
            continue

        link = raw_link if raw_link.startswith("http") else f"https://shop.funbox.com.tw{raw_link}"
        link = link.split("?")[0]  # 清理參數

        title = link_elem.get_text(strip=True)
        card_text = card.get_text(separator=" ", strip=True)

        price_match = re.search(r"NT\$\s*[\d,]+", card_text)
        price = price_match.group(0) if price_match else ""

        # 判斷是否售罄
        is_sold_out = any(keyword in card_text for keyword in ["售完", "補貨中", "缺貨", "售罄", "Sold Out"])
        has_stock = not is_sold_out

        current_products[link] = has_stock

        # 比對邏輯：
        if link not in known_products:
            # 情況 1：全新商品上架（且為現貨）
            if has_stock:
                send_discord(title, link, price, notice_type="新品上架")
        else:
            # 情況 2：先前已售罄 (False)，現在重新補貨 (True)
            was_in_stock = known_products.get(link, False)
            if not was_in_stock and has_stock:
                send_discord(title, link, price, notice_type="現貨補貨")

    # 更新記錄檔
    known_products.update(current_products)
    save_known_products(known_products)
    print("檢查完成，資料庫已更新。")


if __name__ == "__main__":
    check_funbox()
