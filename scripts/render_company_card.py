#!/usr/bin/env python3
"""
把 deck.json(公司介紹卡片專用 schema,結構跟 briefing/closing 的扁平 payload 不同)
套進 templates/company_card.html,渲染成 1080x1350 的 PNG 輪播。

跟 render_card.py 分開成獨立 script,是因為這條 track 的資料結構是「N 張、每張帶
type」的清單(cover/intro/bullets/financial/competitors/sections/cta),不是
Jinja2 模板各自對應一份扁平欄位,套用的是字串 {{PLACEHOLDER}} replace 而非 Jinja2。
兩者渲染機制不同,不要硬塞進同一支 script。

輸出檔名沿用 render_card.py 的慣例(slide-1.png、slide-2.png...),讓 workflow 裡
commit/jsDelivr 那段邏輯可以共用同一套「跑 output/*.png 全部丟上去」的寫法。

用法:
    python3 render_company_card.py --deck deck.json --out-dir output \
        --template templates/company_card.html
"""
import argparse
import base64
import io
import json
import pathlib
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from playwright.sync_api import sync_playwright

W, H = 1080, 1350

# GitHub Actions 端額外裝 fonts-noto-cjk(見 workflow)就是裝在這條路徑,
# 本機測試如果沒有這個字型,月營收圖表的中文座標軸會變成方框,不影響其他張卡片。
CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)
CHART_RED = "#DC2626"
CHART_INK = "#232724"
CHART_GRID = "#ddd6c5"


def find_cjk_font():
    for path in CJK_FONT_CANDIDATES:
        if pathlib.Path(path).exists():
            return fm.FontProperties(fname=path)
    return None


def render_revenue_chart_b64(revenue_chart: dict) -> str:
    """月營收長條圖(+ 選填年增率折線),回傳 base64 PNG(透明背景),嵌進 <img> 用。"""
    months = revenue_chart["months"]
    revenue = revenue_chart["revenue"]
    yoy = revenue_chart.get("yoy")
    font_prop = find_cjk_font()

    fig, ax1 = plt.subplots(figsize=(9.2, 3.3), dpi=150)
    fig.patch.set_alpha(0)
    ax1.set_facecolor("none")

    ax1.bar(range(len(months)), revenue, color=CHART_RED, width=0.6, zorder=3)
    ax1.set_ylabel("月營收(億)", color=CHART_INK, fontsize=13, fontproperties=font_prop)
    ax1.tick_params(axis="y", colors=CHART_INK, labelsize=11)
    ax1.tick_params(axis="x", colors=CHART_INK, labelsize=11)
    ax1.set_xticks(range(len(months)))
    ax1.set_xticklabels(months, rotation=0, fontproperties=font_prop)
    ax1.grid(axis="y", color=CHART_GRID, linewidth=0.8, zorder=0)
    for spine in ax1.spines.values():
        spine.set_visible(False)

    last_label = f"{revenue[-1]:.2f}"
    if yoy:
        last_label += f" ({yoy[-1]:+.1f}%)"
    ax1.text(
        len(months) - 1.3, revenue[-1] * 1.06, last_label,
        color=CHART_RED, ha="center", fontsize=13, fontweight="bold", zorder=4,
    )

    if yoy:
        ax2 = ax1.twinx()
        ax2.set_facecolor("none")
        ax2.plot(range(len(months)), yoy, color=CHART_INK, linewidth=2.2, marker="o", markersize=4, zorder=5)
        ax2.set_ylabel("年增率(%)", color=CHART_INK, fontsize=13, fontproperties=font_prop)
        ax2.tick_params(axis="y", colors=CHART_INK, labelsize=11)
        for spine in ax2.spines.values():
            spine.set_visible(False)
        ax2.set_xlim(-0.6, len(months) - 1 + 0.6)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def md_bold(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def render_bullets(items, compact=False):
    cls = "bullets bullets-compact" if compact else "bullets"
    lis = "".join(f"<li>{md_bold(i)}</li>" for i in items)
    return f'<ul class="{cls}">{lis}</ul>'


def build_body(slide: dict) -> str:
    t = slide.get("type")

    if t == "cover":
        icon = slide.get("icon", "")
        industry_html = (
            f'<div class="industry-tag">📂 {slide["industry"]}</div>' if slide.get("industry") else ""
        )
        return f'''
        <div class="cover-body" style="position:relative;flex:1;display:flex;flex-direction:column;justify-content:center;">
          <div class="tag">{slide.get("tag","公司介紹")}</div>
          <div class="headline">{md_bold(slide.get("title",""))}</div>
          <div class="subline">{slide.get("subtitle","")}</div>
          {industry_html}
          <div class="cover-icon">{icon}</div>
        </div>'''

    if t == "intro":
        paras = "".join(f'<div class="paragraph">{p}</div>' for p in slide.get("paragraphs", []))
        return f'''
        <div class="tag">{slide.get("tag","公司介紹")}</div>
        <div class="body">{paras}</div>'''

    if t == "bullets":
        return f'''
        <div class="tag">{slide.get("tag","主要產品/服務介紹")}</div>
        <div class="body">{render_bullets(slide.get("items", []))}</div>'''

    if t == "financial":
        chart_html = ""
        if slide.get("revenue_chart"):
            chart_b64 = render_revenue_chart_b64(slide["revenue_chart"])
            chart_html = f'<div class="chart-wrap"><img src="data:image/png;base64,{chart_b64}"></div>'
        stats = slide.get("stats", [])
        stat_html = ""
        if stats:
            boxes = "".join(
                f'<div class="stat-box"><div class="stat-label">{s["label"]}</div>'
                f'<div class="stat-value">{s["value"]}</div></div>'
                for s in stats
            )
            stat_html = f'<div class="stat-row">{boxes}</div>'
        bullets_html = render_bullets(slide.get("items", []), compact=True) if slide.get("items") else ""
        return f'''
        <div class="tag">{slide.get("tag","營收獲利表現")}</div>
        <div class="body">{chart_html}{stat_html}{bullets_html}</div>'''

    if t == "sections":
        blocks = ""
        for sec in slide.get("sections", []):
            blocks += f'''
            <div class="section-block">
              <div class="section-title">{sec["title"]}</div>
              {render_bullets(sec.get("items", []))}
            </div>'''
        return f'''
        <div class="tag">{slide.get("tag","未來展望")}</div>
        <div class="body">{blocks}</div>'''

    if t == "competitors":
        summary_html = (
            f'<div class="competitor-summary">{md_bold(slide["summary"])}</div>' if slide.get("summary") else ""
        )
        items_html = "".join(
            f'''<div class="competitor-item">
                  <div class="competitor-region">{c.get("region","")}</div>
                  <div>
                    <div class="competitor-name">{c["name"]}</div>
                    <div class="competitor-note">{c.get("note","")}</div>
                  </div>
                </div>'''
            for c in slide.get("competitors", [])
        )
        return f'''
        <div class="tag">{slide.get("tag","競爭對手")}</div>
        <div class="body">{summary_html}<div class="competitor-list">{items_html}</div></div>'''

    if t == "cta":
        icon_heart = '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12.001 4.529c2.349-2.532 6.146-2.532 8.495 0 2.348 2.532 2.348 6.638 0 9.17L12 21.999l-8.496-8.3c-2.348-2.532-2.348-6.638 0-9.17 2.349-2.532 6.147-2.532 8.497 0z"/></svg>'
        icon_bookmark = '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3.5h12a1 1 0 0 1 1 1V21l-7-4.2L5 21V4.5a1 1 0 0 1 1-1z"/></svg>'
        icon_comment = '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>'
        icon_share = '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 3 2 10.5l7.5 3 3 7.5z"/><path d="M22 3 12.5 13.5"/></svg>'
        return f'''
        <div class="cta-wrap">
          <div class="cta-title">{slide.get("title","如果你喜歡這篇文章")}<br><span class="accent">{slide.get("accent","給我們一個讚 or 愛心")}</span></div>
          <div class="cta-icons">{icon_heart}{icon_comment}{icon_share}{icon_bookmark}</div>
        </div>'''

    return '<div class="body"><div class="paragraph">(未支援的 slide type)</div></div>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, help="deck.json 路徑")
    ap.add_argument("--out-dir", required=True, help="輸出資料夾")
    ap.add_argument("--template", required=True, help="company_card.html 路徑")
    args = ap.parse_args()

    deck = json.loads(pathlib.Path(args.deck).read_text(encoding="utf-8"))
    template = pathlib.Path(args.template).read_text(encoding="utf-8")
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    brand_name = deck.get("brand_name", "")
    brand_sub = deck.get("brand_sub", "")
    brand_initial = deck.get("brand_initial", brand_name[:1] if brand_name else "")
    ticker = deck.get("ticker", "")
    src_note = deck.get("src_note", "")
    slides = deck.get("slides", [])
    if not slides:
        print("deck.json 沒有 slides,沒有東西可以渲染", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})

        for idx, slide in enumerate(slides, start=1):
            variant_class = {"cover": "cover", "cta": "cta"}.get(slide.get("type"), "")
            body_html = build_body(slide)
            page_idx = f"{idx:02d} / {len(slides):02d}"

            html = (
                template.replace("{{VARIANT_CLASS}}", variant_class)
                .replace("{{BRAND_INITIAL}}", brand_initial)
                .replace("{{BRAND_NAME}}", brand_name)
                .replace("{{BRAND_SUB}}", brand_sub)
                .replace("{{TICKER}}", ticker)
                .replace("{{BODY}}", body_html)
                .replace("{{PAGE_IDX}}", page_idx)
                .replace("{{SRC_NOTE}}", src_note)
            )

            tmp_html_path = out_dir / "_card_tmp.html"
            tmp_html_path.write_text(html, encoding="utf-8")
            page.goto(f"file://{tmp_html_path.resolve()}")

            out_path = out_dir / f"slide-{idx}.png"
            page.screenshot(path=str(out_path))
            print(f"圖卡已輸出: {out_path}")

        browser.close()

    (out_dir / "_card_tmp.html").unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
