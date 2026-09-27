#!/usr/bin/env python3
"""GalleryForge Exporte je Wochen-Release (dark/light, komplett mit Rand).

Formate:
  monolith    -> releases/<id>/gallery-<theme>.html  (eine Datei, Thumbs
                 base64-eingebettet, Originale als Datei-Links daneben)
  traditional -> releases/<id>/html-<theme>/         (index.html + gallery.css
                 + images/ + thumbnails/, Videos als <video>)
  pdf         -> releases/<id>/Release-<id>-<theme>.pdf (Vorschaubilder +
                 klickbare Links auf Originaldateien, Seite vollflächig im Theme)

Videos werden nie umgewandelt: Vorschau = Standbild-Thumb, Klick/Link öffnet mp4.
"""

import base64
import html as html_lib
import json
import shutil
from pathlib import Path

from core.config_loader import load_config

config = load_config()
RELEASES_DIR = Path(config["paths"]["releases"])

THEMES = {
    "dark": {
        "page": "#070a12", "card": "#101828", "text": "#e8eefc",
        "dim": "#8b98b8", "accent": "#00f0ff", "accent2": "#b537ff",
        "tag": "#1e2a44", "fpdf_bg": (7, 10, 18), "fpdf_text": (232, 238, 252),
        "fpdf_dim": (139, 152, 184), "fpdf_accent": (0, 240, 255),
    },
    "light": {
        "page": "#f4f6fb", "card": "#ffffff", "text": "#16213a",
        "dim": "#5b6b8c", "accent": "#0077cc", "accent2": "#7a2be0",
        "tag": "#e3e9f5", "fpdf_bg": (244, 246, 251), "fpdf_text": (22, 33, 58),
        "fpdf_dim": (91, 107, 140), "fpdf_accent": (0, 119, 204),
    },
}

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}


def _theme(name: str) -> dict:
    return THEMES.get(name, THEMES["dark"])


def _release_data(release_id: str) -> dict:
    f = RELEASES_DIR / release_id / "release.json"
    return json.loads(f.read_text(encoding="utf-8"))


def _is_video(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTS


def _thumb_b64(release_id: str, rel: str) -> str:
    p = RELEASES_DIR / release_id / rel
    if not p.exists():
        return ""
    mime = "image/webp" if p.suffix.lower() == ".webp" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def _css(_t=None) -> str:
    return """*{
  box-sizing:border-box;
}
:root{
  --page:#070a12;--card:#101828;--text:#e8eefc;--dim:#8b98b8;
  --accent:#00f0ff;--tag:#1e2a44;
}
[data-theme="light"]{
  --page:#f4f6fb;--card:#ffffff;--text:#16213a;--dim:#5b6b8c;
  --accent:#0077cc;--tag:#e3e9f5;
}
html{
  background:var(--page);
}
body{
  margin:0;
  padding:28px 20px 60px;
  background:var(--page);
  color:var(--text);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
}
h1{
  text-align:center;
}
.sub{
  text-align:center;color:var(--dim);margin-bottom:24px;
}
.gallery{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:20px;
  max-width:1400px;margin:0 auto;
}
.card{
  background:var(--card);border-radius:12px;overflow:hidden;
  box-shadow:0 4px 18px rgba(0,0,0,.35);
}
.card img,.card video{
  width:100%;display:block;background:#000;
}
.card .tx{
  padding:10px 12px;
}
.card .fn{
  font-weight:700;font-size:13px;word-break:break-all;
}
.card .de{
  font-size:12.5px;color:var(--dim);margin-top:6px;
}
.card .tags{
  margin-top:8px;
}
.tag{
  display:inline-block;background:var(--tag);color:var(--text);
  border-radius:12px;padding:2px 8px;margin:2px 4px 0 0;font-size:11px;
}
a{
  color:var(--accent);
}
.theme-btn{
  position:fixed;top:12px;right:12px;z-index:10;
  border:1px solid var(--dim);background:var(--card);color:var(--text);
  border-radius:99px;padding:8px 14px;font-size:13px;cursor:pointer;
}
@media print{
  body{
    background:var(--page) !important;
    -webkit-print-color-adjust:exact;print-color-adjust:exact;
  }
  .theme-btn{display:none;}
}"""

THEME_JS = """<script>
(function(){
  try{
    var saved=null;
    try{saved=localStorage.getItem("gf-gallery-theme");}catch(e){}
    if(saved)document.documentElement.setAttribute("data-theme",saved);
  }catch(e){}
  document.addEventListener("DOMContentLoaded",function(){
    var b=document.getElementById("themeBtn");
    if(!b)return;
    function sync(){
      b.textContent=document.documentElement.getAttribute("data-theme")==="light"?"dunkel":"hell";
    }
    b.addEventListener("click",function(){
      var cur=document.documentElement.getAttribute("data-theme")==="light"?"dark":"light";
      document.documentElement.setAttribute("data-theme",cur);
      try{localStorage.setItem("gf-gallery-theme",cur);}catch(e){}
      sync();
    });
    sync();
  });
})();
</script>"""


def _card_html(a: dict, thumb_src: str, img_href: str) -> str:
    fn = html_lib.escape(a.get("filename", ""))
    de = html_lib.escape(a.get("description") or "")
    tags = "".join(
        f'<span class="tag">{html_lib.escape(t)}</span>'
        for t in (a.get("tags") or [])
    )
    if _is_video(a.get("filename", "")):
        media = (
            f'<video controls preload="none" poster="{thumb_src}">'
            f'<source src="{img_href}"></video>'
        )
    else:
        media = f'<a href="{img_href}"><img src="{thumb_src}" loading="lazy"></a>'
    return (
        f'<div class="card">{media}<div class="tx">'
        f'<div class="fn">{fn}</div>'
        + (f'<div class="de">{de}</div>' if de else '')
        + (f'<div class="tags">{tags}</div>' if tags else '')
        + "</div></div>"
    )


def _page_html(release_id: str, assets: list, theme: str, thumb_fn, img_fn) -> str:
    cards = "\n".join(
        _card_html(a, thumb_fn(a), img_fn(a)) for a in assets
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"de\" data-theme=\"" + theme + "\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        f"<title>Release {release_id}</title>\n"
        f"<style>\n{_css()}\n</style>\n</head>\n<body>\n"
        "<button class=\"theme-btn\" id=\"themeBtn\" type=\"button\">hell</button>\n"
        f"<h1>Release {release_id}</h1>\n"
        f"<div class=\"sub\">{len(assets)} Medien</div>\n"
        f"<div class=\"gallery\">\n{cards}\n</div>\n{THEME_JS}\n</body>\n</html>"
    )


def export_monolith(release_id: str, theme: str = "dark", progress=None) -> Path:
    """Eine HTML-Datei, Thumbs eingebettet, Originale verlinkt."""
    theme = theme if theme in THEMES else "dark"
    data = _release_data(release_id)
    assets = data.get("assets", [])
    total = max(1, len(assets))

    def thumb_fn(a):
        if progress:
            progress(a)
        return _thumb_b64(release_id, a.get("thumbnail", "")) or a.get("thumbnail", "")

    html = _page_html(
        release_id, assets, theme, thumb_fn,
        lambda a: a.get("image", ""),
    )
    out = RELEASES_DIR / release_id / f"gallery-{theme}.html"
    out.write_text(html, encoding="utf-8")
    return out


def export_traditional(release_id: str, theme: str = "dark", progress=None) -> Path:
    """Ordner: index.html + gallery.css + images/ + thumbnails/."""
    theme = theme if theme in THEMES else "dark"
    t = _theme(theme)
    data = _release_data(release_id)
    assets = data.get("assets", [])
    src_dir = RELEASES_DIR / release_id
    out = src_dir / f"html-{theme}"
    img_d = out / "images"
    th_d = out / "thumbnails"
    img_d.mkdir(parents=True, exist_ok=True)
    th_d.mkdir(parents=True, exist_ok=True)
    for a in assets:
        for key, target in (("image", img_d), ("thumbnail", th_d)):
            src = src_dir / a.get(key, "")
            if src.exists() and src.is_file():
                shutil.copy2(src, target / src.name)
        if progress:
            progress(a)
    (out / "gallery.css").write_text(_css(t), encoding="utf-8")
    page = _page_html(
        release_id, assets, theme,
        lambda a: "thumbnails/" + Path(a.get("thumbnail", "")).name,
        lambda a: "images/" + Path(a.get("image", "")).name,
    ).replace("</title>", "</title>\n<link rel=\"stylesheet\" href=\"gallery.css\">")
    # Inline-<style> raus, externe CSS rein (alles andere bleibt gleich)
    start = page.find("<style>")
    end = page.find("</style>") + len("</style>")
    page = page[:start] + page[end:]
    (out / "index.html").write_text(page, encoding="utf-8")
    return out / "index.html"


def _file_link(src_dir: Path, rel: str) -> str:
    """Klick-Link aufs Original, relativ zum PDF-Ordner (portabel beim
    Kopieren/Verschieben; absolute file:///D:/... funktionieren in vielen
    Readern – v.a. Browser – gar nicht)."""
    from urllib.parse import quote

    name = Path(rel).name
    return "images/" + quote(name, safe="")


def export_pdf(release_id: str, theme: str = "dark", progress=None) -> Path:
    """PDF-Katalog: Vorschaubilder + klickbare Original-Links, Seite im Theme."""
    from fpdf import FPDF

    theme = theme if theme in THEMES else "dark"
    t = _theme(theme)
    data = _release_data(release_id)
    assets = data.get("assets", [])
    src_dir = RELEASES_DIR / release_id
    out = src_dir / f"Release-{release_id}-{theme}.pdf"

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(12, 12, 12)
    for font, fpath in (
        ("dejavu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("dejavub", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ):
        pdf.add_font(font, "", fpath)
    bg, fg, dim, acc = t["fpdf_bg"], t["fpdf_text"], t["fpdf_dim"], t["fpdf_accent"]

    def bg_page():
        pdf.set_fill_color(*bg)
        pdf.rect(0, 0, 210, 297, style="F")

    pdf.add_page()
    bg_page()
    pdf.set_text_color(*fg)
    pdf.set_font("dejavub", "", 20)
    pdf.cell(0, 12, f"Release {release_id}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("dejavu", "", 10)
    pdf.set_text_color(*dim)
    pdf.cell(0, 7, f"{len(assets)} Medien - Theme {theme} - GalleryForge", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    for a in assets:
        if pdf.get_y() > 235:
            pdf.add_page()
            bg_page()
        y0 = pdf.get_y()
        thumb = src_dir / a.get("thumbnail", "")
        orig = src_dir / a.get("image", "")
        link = _file_link(src_dir, a.get("image", "")) if orig.exists() else ""
        x_img, w_img = 12, 70
        if thumb.exists():
            try:
                pdf.image(str(thumb), x=x_img, y=y0, w=w_img, link=link or None)
            except Exception:
                pass
        h_thumb = 52
        pdf.set_xy(x_img + w_img + 6, y0)
        pdf.set_text_color(*fg)
        pdf.set_font("dejavub", "", 11)
        pdf.multi_cell(186 - x_img - w_img, 6, a.get("filename", ""), link=link or None)
        desc = a.get("description") or ""
        if desc:
            pdf.set_x(x_img + w_img + 6)
            pdf.set_text_color(*dim)
            pdf.set_font("dejavu", "", 9)
            pdf.multi_cell(186 - x_img - w_img, 5, desc)
        tags = a.get("tags") or []
        if tags:
            pdf.set_x(x_img + w_img + 6)
            pdf.set_text_color(*acc)
            pdf.set_font("dejavu", "", 9)
            pdf.multi_cell(186 - x_img - w_img, 5, "Tags: " + ", ".join(tags))
        if link:
            pdf.set_x(x_img + w_img + 6)
            pdf.set_text_color(*acc)
            pdf.set_font("dejavu", "", 9)
            pdf.cell(0, 6, "Original oeffnen" + (" (Video)" if _is_video(a.get("filename", "")) else ""),
                     link=link, new_x="LMARGIN", new_y="NEXT")
        y1 = max(pdf.get_y(), y0 + h_thumb) + 4
        pdf.set_y(y1)
        if progress:
            progress(a)

    pdf.output(str(out))
    return out


FORMATS = {
    "monolith": export_monolith,
    "traditional": export_traditional,
    "pdf": export_pdf,
}
