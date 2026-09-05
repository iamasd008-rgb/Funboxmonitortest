import json
import os
import re
import requests
from bs4 import BeautifulSoup

# 戰鬥陀螺主分類頁面（依上架時間由新到舊排序）
TARGET_URL = "https://shop.funbox.com.tw/categories/takaratomy/beyblade?sort_by=created_at&order_by=desc"
CACHE_FILE = "known_products.json"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}


def send_discord(title, link, price, is_sold_out):
    if not DISCORD_WEBHOOK_URL:
        print("未設定 DISCORD_WEBHOOK_URL，跳過通知。")
        return

    # 綠色(現貨): 3066993, 紅色(售罄): 15158332
    color = 15158332 if is_sold_out else 3066993
    status_text = "⚠️ 售完待補貨 / 缺貨中" if is_sold_out else "🔥 現貨可購買！"

    fields = [
        {"name": "狀態", "value": status_text, "inline": True},
    ]
    if price:
        fields.append({"name": "售價", "value": price, "inline": True})

    payload = {
        "username": "Funbox 戰鬥陀螺雷達",
        "embeds": [
            {
                "title": f"【新品上架】{title}",
                "url": link,
                "color": color,
                "fields": fields,
                "footer": {"text": "Funbox 官網自動監控通知"},
            }
        ],
    }

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code != 204:
            print(f"Discord 推播失敗，狀態碼: {resp.status_code}")
    except Exception as e:
        print(f"發送 Discord 發生異常: {e}")


def load_known_products():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_known_products(products_set):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(products_set), f, ensure_ascii=False, indent=2)


def main():
    print(f"正在檢查頁面: {TARGET_URL}")
    try:
        resp = requests.get(TARGET_URL, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"網路連線異常: {e}")
        return

    if resp.status_code != 200:
        print(f"網頁請求失敗，狀態碼: {resp.status_code}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")

    # 選取商品卡片
    product_elements = soup.select(
        ".product-item, .box-item, .Product-item, div[class*='ProductList'] > div"
    )

    current_products = {}
    for el in product_elements:
        # 抓取商品標題
        title_el = el.select_one(
            ".title, .product-title, .title-container, a[class*='title']"
        )
        link_el = el.select_one("a[href*='/products/']") or el.select_one(
            "a[href]"
        )

        if not title_el or not link_el:
            continue

        title = title_el.get_text(strip=True)
        if not title:
            continue

        link = link_el.get("href", "")
        if link.startswith("/"):
            link = f"https://shop.funbox.com.tw{link}"

        # 抓取商品售價
        price_el = el.select_one(".price, .current-price, .price-sale")
        price = price_el.get_text(strip=True) if price_el else ""
        if price:
            # 清理多餘空白與換行
            price = re.sub(r"\s+", " ", price)

        # 檢查是否已售完
        raw_card_text = el.get_text()
        is_sold_out = any(
            kw in raw_card_text for kw in ["售完待補貨", "庫存不足", "補貨中"]
        ) or bool(el.select_one(".sold-out, .out-of-stock"))

        # 使用連結或品名作為唯一識別碼
        current_products[link] = {
            "title": title,
            "link": link,
            "price": price,
            "sold_out": is_sold_out,
        }

    known_products = load_known_products()
    new_items_found = []

    for link, info in current_products.items():
        if link not in known_products:
            new_items_found.append(info)
            known_products.add(link)

    # 如果有新商品，發送通知
    if new_items_found:
        print(f"發現 {len(new_items_found)} 項新商品！正在發送通知...")
        for item in new_items_found:
            send_discord(
                title=item["title"],
                link=item["link"],
                price=item["price"],
                is_sold_out=item["sold_out"],
            )
        save_known_products(known_products)
    else:
        print("目前沒有發現新上架商品。")


if __name__ == "__main__":
    main()
