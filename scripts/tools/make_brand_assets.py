"""Генерирует favicon.svg и og-image.png (1200×630) из выбранного логотипа и фото модели.

    .venv/Scripts/python scripts/tools/make_brand_assets.py [--logo volt] [--photo hy-m]
Для og-image нужен установленный Chrome или Edge (headless-скриншот).
"""
from __future__ import annotations

import argparse
import base64
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
)


def load_logos() -> dict:
    namespace: dict = {}
    exec((ROOT / "apps/pages/icons.py").read_text(encoding="utf-8"), namespace)  # noqa: S102 — свой файл
    return namespace["LOGOS"]


def og_html(logo_svg: str, photo: Path) -> str:
    photo_b64 = base64.b64encode(photo.read_bytes()).decode()
    return f"""<!doctype html><meta charset="utf-8"><style>
*{{box-sizing:border-box;margin:0}}body{{width:1200px;height:630px;overflow:hidden;color:#fff;
font-family:Bahnschrift,"Arial Narrow",Impact,sans-serif;background:radial-gradient(60% 90% at 78% 45%,rgba(225,6,0,.55),transparent 70%),#0b0b0c}}
.t{{position:absolute;left:64px;top:110px;width:560px}}.mark{{width:120px;height:120px}}
h1{{font-size:112px;line-height:.95;text-transform:uppercase;margin:22px 0 16px;font-stretch:80%}}h1 b{{color:#ff3b30}}
p{{font-family:"Segoe UI",Arial,sans-serif;font-size:30px;color:#d6d6da}}
.ph{{position:absolute;right:36px;top:120px;width:600px;height:400px;border-radius:28px;
background:#fff;display:grid;place-items:center}}
.ph img{{width:94%;height:88%;object-fit:contain}}.bar{{position:absolute;left:0;right:0;bottom:0;height:12px;background:linear-gradient(90deg,#e10600,transparent 75%)}}
</style><div class="t">{logo_svg.replace('<svg ', '<svg class="mark" ', 1)}<h1>IV<b>&amp;</b>AX<br>MOTO</h1>
<p>Электромотоциклы · Нижнекамск<br>Конфигуратор и цены по курсу ЦБ РФ</p></div>
<div class="ph"><img src="data:image/webp;base64,{photo_b64}"></div><div class="bar"></div>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logo", default="volt")
    parser.add_argument("--photo", default="hy-m")
    args = parser.parse_args()
    logo = load_logos()[args.logo]
    (ROOT / "static/assets/favicon.svg").write_text(logo + "\n", encoding="utf-8")
    (ROOT / "static/assets/logo.svg").write_text(logo + "\n", encoding="utf-8")
    browser = next((b for b in BROWSERS if Path(b).exists()), None) or shutil.which("chromium")
    if not browser:
        raise SystemExit("Нужен Chrome/Edge для og-image.png")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "og.html"
        page.write_text(og_html(logo, ROOT / f"apps/catalog/seed/photos/{args.photo}.webp"), encoding="utf-8")
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1200,630",
                        f"--screenshot={ROOT / 'static/assets/og-image.png'}", page.as_uri()],
                       check=True, capture_output=True)
    print("favicon.svg, logo.svg, og-image.png обновлены")


if __name__ == "__main__":
    main()
