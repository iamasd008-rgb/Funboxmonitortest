import json
import os
import re
import requests
from bs4 import BeautifulSoup

# --- 基本設定區 ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
CACHE_FILE = "known_products.json"

# 帶上依上架時間倒序排序的完整網址，促使伺服器直接輸出列表 HTML
TARGET_URL = "https://shop.funbox.com.tw/categories/takaratomy/beyblade?sort_by=created_at&order=desc"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh-Hant;q=0.9",
    "Referer": "https://shop.funbox.com.tw/",
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
    print("正在請求 Funbox 官網陀螺專區...")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"網頁請求失敗: {e}")
        return

    soup = BeautifulSoup(html, "html.parser")

    # 抓取包含 products 的所有連結，並過濾掉導航列或無效連結
    all_links = soup.find_all("a", href=True)
    product_cards = []
    
    for a in all_links:
        href = a["href"]
        if "/products/" in href and not href.endswith("/products/"):
            product_cards.append(a)

    print(f"頁面初步匹配到商品連結數量: {len(product_cards)}")

    found_count = 0
    for link_elem in product_cards:
        raw_link = link_elem["href"]
        link = raw_link if raw_link.startswith("http") else f"https://shop.funbox.com.tw{raw_link}"
        link = link.split("?")[0]

        # 向上找到卡片區塊
        parent_box = link_elem.find_parent("li") or link_elem.find_parent("div") or link_elem
        box_text = parent_box.get_text(separator=" ", strip=True)

        # 尋找名稱與價格
        title = link_elem.get_text(strip=True)
        if not title:
            img = link_elem.find("img")
            if img and img.get("alt"):
                title = img.get("alt").strip()
            elif parent_box:
                title = parent_box.get_text(strip=True)[:40]

        if not title or len(title) < 3 or "加入購物車" == title:
            continue

        price_match = re.search(r"NT\$\s*[\d,]+", box_text)
        price = price_match.group(0) if price_match else ""

        is_sold_out = any(k in box_text for k in ["售完", "補貨中", "缺貨", "售罄", "Sold Out"])
        has_stock = not is_sold_out

        if link in current_round:
            continue

        found_count += 1
        current_round[link] = has_stock
        print(f"成功捕捉到商品: {title} | 售價: {price} | 現貨: {has_stock}")

        if link not in known_products:
            if has_stock:
                send_discord(title, link, price, notice_type="新品上架")
        else:
            if not known_products.get(link, False) and has_stock:
                send_discord(title, link, price, notice_type="現貨補貨")

    print(f"有效商品比對完成，共辨識出 {found_count} 筆。")


def main():
    known_products = load_known_products()
    current_round = {}

    check_funbox(known_products, current_round)

    known_products.update(current_round)
    save_known_products(known_products)
    print("全流程執行結束。")


if __name__ == "__main__":
    main()
