#!/usr/bin/env python3
"""
把 payload.json 套進 templates/card_template.html,渲染成 1080x1350 的 PNG。

用法:
    python3 render_card.py --payload payload.json --out output/card.png
"""
import argparse
import json
import pathlib
import sys

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent


SCALAR_CLS_FIELDS = ("taiex_change", "otc_change", "margin_change")
LIST_CLS_FIELDS = ("us_indices", "adr", "institutional")


def load_payload(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 幫漲跌數字自動補上顏色 class(如果 payload 沒帶 cls 欄位),
    # 用 +/- 開頭判斷,依台股習慣紅漲綠跌。
    def infer_cls(item):
        if "cls" not in item:
            item["cls"] = "up" if item["value"].strip().startswith("+") else "down"
        return item

    for key in LIST_CLS_FIELDS:
        if key in data:
            data[key] = [infer_cls(x) for x in data[key]]

    for key in SCALAR_CLS_FIELDS:
        if key in data:
            data[f"{key}_cls"] = "up" if str(data[key]).strip().startswith("+") else "down"

    return data


def render_html(data: dict, template_name: str) -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    template = env.get_template(template_name)
    return template.render(**data)


# 內文長度每天都不一樣(新聞則數、族群清單長短...),固定字級版面很容易爆版。
# 套用 .fit-text class 的區塊,在真的塞不下時自動一起等比縮小字級/行距,
# 縮到 MIN_FIT_SCALE 還塞不下就放棄,印警告但照樣輸出(比整批失敗好處理)。
MIN_FIT_SCALE = 0.55

AUTOFIT_JS = """
(minScale) => {
  const card = document.querySelector('.card');
  const targets = Array.from(document.querySelectorAll('.fit-text'));
  const available = card.clientHeight;

  targets.forEach(el => {
    if (!el.dataset.baseFont) {
      el.dataset.baseFont = parseFloat(getComputedStyle(el).fontSize);
      el.dataset.baseMarginBottom = parseFloat(getComputedStyle(el).marginBottom) || 0;
    }
  });

  let scale = 1.0;
  let guard = 0;
  while (card.scrollHeight > available && scale > minScale && guard < 90) {
    scale = Math.max(minScale, scale - 0.01);
    targets.forEach(el => {
      el.style.fontSize = (el.dataset.baseFont * scale) + 'px';
      el.style.marginBottom = (el.dataset.baseMarginBottom * scale) + 'px';
    });
    guard++;
  }

  return { scale, fits: card.scrollHeight <= available, scrollHeight: card.scrollHeight, available };
}
"""


def html_to_png(html: str, out_path: str):
    out_dir = pathlib.Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_html = out_dir / "_card_tmp.html"
    tmp_html.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})
        page.goto(f"file://{tmp_html.resolve()}")

        result = page.evaluate(AUTOFIT_JS, MIN_FIT_SCALE)
        if not result["fits"]:
            print(
                f"警告:內容過長,字級縮到 {result['scale']:.2f} 倍(下限)還是塞不下"
                f"(內容高度 {result['scrollHeight']}px > 可用 {result['available']}px),"
                f"圖卡底部可能還是被裁切,建議精簡文案。",
                file=sys.stderr,
            )

        page.screenshot(path=out_path)
        browser.close()

    tmp_html.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", required=True, help="payload.json 路徑")
    ap.add_argument("--out", required=True, help="輸出 PNG 路徑")
    ap.add_argument(
        "--template",
        default="card_template.html",
        help="templates/ 底下的模板檔名(預設 card_template.html)",
    )
    args = ap.parse_args()

    data = load_payload(args.payload)
    html = render_html(data, args.template)
    html_to_png(html, args.out)
    print(f"圖卡已輸出: {args.out}")


if __name__ == "__main__":
    sys.exit(main())
