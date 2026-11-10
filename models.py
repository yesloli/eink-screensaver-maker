# -*- coding: utf-8 -*-
"""
掌阅 iReader 机型库（分辨率）

数据来源与可信度：
  1) 掌阅官方新闻稿 / 官方参数页（Ocean 3 Plus、Smart Xs、Smart 2、Ocean 6 系列等）
     —— 第一手，最高可信度。
  2) readwithpro.com 的 iReader 品牌档案页（62 台可比较机型，逐台标注面板/分辨率/PPI，
     并区分「官方标注」与「按分辨率推算」）—— 二手汇总，用来覆盖官方稿没提到的老机型。
  3) 太平洋电脑网 / 中关村在线参数库 —— 仅作交叉验证。
     这两家的参数偶有明显笔误（如把 6 寸 C6 写成 1872×1404、把 Smart 3 写成 1404×872），
     凡与 PPI 数学不自洽的数值一律不采用。

字段说明：
  name  机型名
  w,h   屏幕的竖屏分辨率（w 为短边 / 横向像素，h 为长边 / 纵向像素）
  ppi   像素密度；彩色机为 "黑白/彩色"
  kind  '黑白' | '彩色'
  year  上市年月
  src   数据依据

注意：电子纸面板物理上是竖屏（如 7 寸为 1264×1680）。厂商标称常写作 1680×1264，
      所以同一台机器在工具里会同时提供「竖屏 1264×1680」和「横屏 1680×1264」两种输出。
"""

MODELS = [
    # ---------------- 6 寸 1024×758（212 PPI，入门 Light 线） ----------------
    dict(name="Light 青春版 (2017)", w=758, h=1024, ppi="212", kind="黑白", year="2017-06", src="readwithpro"),
    dict(name="Light 2", w=758, h=1024, ppi="212", kind="黑白", year="2021-05", src="readwithpro"),
    dict(name="Light 3 / 3 Turbo", w=758, h=1024, ppi="212", kind="黑白", year="2023-10", src="readwithpro"),
    dict(name="Light 4 长续航 / 4 Turbo", w=758, h=1024, ppi="212", kind="黑白", year="2025-04", src="readwithpro"),

    # ---------------- 6 寸 1072×1448（300 PPI） ----------------
    dict(name="Light 悦享版 (2017)", w=1072, h=1448, ppi="300", kind="黑白", year="2017-06", src="readwithpro"),
    dict(name="T6", w=1072, h=1448, ppi="300", kind="黑白", year="2018-04", src="readwithpro"),
    dict(name="A6", w=1072, h=1448, ppi="300", kind="黑白", year="2019-04", src="readwithpro"),
    dict(name="Light2 Pro", w=1072, h=1448, ppi="300", kind="黑白", year="2021-10", src="readwithpro"),
    dict(name="Neo 2", w=1072, h=1448, ppi="300", kind="黑白", year="2024-02", src="readwithpro"),
    dict(name="Neo 2 Pro", w=1072, h=1448, ppi="300", kind="黑白", year="2024-04", src="readwithpro"),
    dict(name="Neo 3", w=1072, h=1448, ppi="300", kind="黑白", year="2025-07", src="readwithpro"),
    dict(name="Neo 3 Pro", w=1072, h=1448, ppi="300", kind="黑白", year="2025-09", src="readwithpro"),
    dict(name="Neo 3 Ultra", w=1072, h=1448, ppi="300", kind="黑白", year="2026-03", src="readwithpro"),

    # ---------------- 6.8 寸 1080×1440（265 PPI，早期产品） ----------------
    dict(name="iReader 初代", w=1080, h=1440, ppi="265", kind="黑白", year="2015-08", src="readwithpro"),
    dict(name="iReader Plus", w=1080, h=1440, ppi="265", kind="黑白", year="2016-05", src="readwithpro"),
    dict(name="Ocean (2017)", w=1080, h=1440, ppi="265", kind="黑白", year="2017-11", src="readwithpro"),

    # ---------------- 6.13 寸 824×1648（300 PPI，Tango 手机型 2:1） ----------------
    dict(name="Tango", w=824, h=1648, ppi="300", kind="黑白", year="2025-05", src="readwithpro"),
    dict(name="Tango 2", w=824, h=1648, ppi="300", kind="黑白", year="2025-10", src="readwithpro"),
    dict(name="Tango 2 Pro", w=824, h=1648, ppi="300", kind="黑白", year="2026-03", src="readwithpro"),

    # ---------------- 7 寸 1264×1680（300 PPI，Ocean 主力线） ----------------
    dict(name="Ocean 2", w=1264, h=1680, ppi="300", kind="黑白", year="2022-04", src="readwithpro"),
    dict(name="Ocean 3", w=1264, h=1680, ppi="300", kind="黑白", year="2023-03", src="readwithpro"),
    dict(name="Ocean 4 长续航 / 4 Turbo (2024)", w=1264, h=1680, ppi="300", kind="黑白", year="2024-07", src="readwithpro"),
    dict(name="Ocean 4 Turbo 2025", w=1264, h=1680, ppi="300", kind="黑白", year="2025-03", src="readwithpro"),
    dict(name="Ocean 4 长续航 2025", w=1264, h=1680, ppi="300", kind="黑白", year="2025-04", src="readwithpro"),
    dict(name="Ocean 5 / 5 长续航 / 5 Pro", w=1264, h=1680, ppi="300", kind="黑白", year="2025-10", src="官方+readwithpro"),
    dict(name="Ocean 6 Pro", w=1264, h=1680, ppi="300", kind="黑白", year="2026-10", src="官方新闻稿"),
    dict(name="Ocean 6 Turbo", w=1264, h=1680, ppi="300", kind="黑白", year="2026-10", src="官方新闻稿"),

    # ---------------- 8 寸 1440×1920（300 PPI） ----------------
    dict(name="Ocean 3 Plus", w=1440, h=1920, ppi="300", kind="黑白", year="2023-08", src="官方新闻稿"),
    dict(name="Ocean 4 Plus 典藏版", w=1440, h=1920, ppi="300", kind="黑白", year="2024-10", src="readwithpro"),
    dict(name="Smart Xs", w=1440, h=1920, ppi="300", kind="黑白", year="2021-05", src="官方新闻稿"),
    dict(name="Smart Xs Pro", w=1440, h=1920, ppi="300", kind="黑白", year="2021-05", src="readwithpro"),
    dict(name="Smart Air", w=1440, h=1920, ppi="300", kind="黑白", year="2022-12", src="readwithpro"),
    dict(name="Smart Air Pro", w=1440, h=1920, ppi="300", kind="黑白", year="2022-12", src="readwithpro"),

    # ---------------- 8.2 寸 1440×1920（约 293 PPI，Air 3 Pro） ----------------
    dict(name="Air 3 Pro 泊渊 / 默白", w=1440, h=1920, ppi="293", kind="黑白", year="2026-08", src="readwithpro"),

    # ---------------- 10.3 寸 1404×1872（227 PPI，手写本） ----------------
    dict(name="Smart (2018)", w=1404, h=1872, ppi="227", kind="黑白", year="2018-08", src="readwithpro"),
    dict(name="Smart X", w=1404, h=1872, ppi="227", kind="黑白", year="2019-10", src="readwithpro"),
    dict(name="Smart 2", w=1404, h=1872, ppi="227", kind="黑白", year="2020-10", src="官方新闻稿"),
    dict(name="Smart X2", w=1404, h=1872, ppi="227", kind="黑白", year="2021-10", src="readwithpro"),
    dict(name="Smart 3", w=1404, h=1872, ppi="227", kind="黑白", year="2022-04", src="readwithpro"),
    dict(name="Smart 4 / 4 Pro", w=1404, h=1872, ppi="227", kind="黑白", year="2023-04", src="readwithpro"),
    dict(name="Smart 5", w=1404, h=1874, ppi="227", kind="黑白", year="2024-04", src="readwithpro"),

    # ---------------- 10.3 寸 1860×2480（300 PPI，新一代） ----------------
    dict(name="Smart 5 Pro", w=1860, h=2480, ppi="300", kind="黑白", year="2024-07", src="readwithpro"),
    dict(name="Smart 6 Pro", w=1860, h=2480, ppi="300", kind="黑白", year="2026-04", src="readwithpro"),

    # ---------------- 10.65 寸 1920×2560（300 PPI） ----------------
    dict(name="Smart X3", w=1920, h=2560, ppi="300", kind="黑白", year="2023-10", src="readwithpro"),
    dict(name="Smart X3 Pro", w=1920, h=2560, ppi="300", kind="黑白", year="2024-04", src="readwithpro"),
    dict(name="Smart X5 Ultra", w=1920, h=2560, ppi="300", kind="黑白", year="2025-06", src="readwithpro"),

    # ---------------- 彩色（Kaleido 3 / Print-Color） ----------------
    dict(name="C6", w=1072, h=1448, ppi="300 / 100", kind="彩色", year="2020-03", src="readwithpro"),
    dict(name="C6 Pro", w=1072, h=1448, ppi="300 / 100", kind="彩色", year="2021-09", src="readwithpro"),
    dict(name="Color7", w=1264, h=1680, ppi="300", kind="彩色", year="2023-12", src="readwithpro"),
    dict(name="Light 4C", w=1072, h=1448, ppi="300 / 150", kind="彩色", year="2025-04", src="readwithpro"),
    dict(name="Ocean 4C", w=1264, h=1680, ppi="300 / 150", kind="彩色", year="2025-01", src="readwithpro"),
    dict(name="Ocean 5C", w=1264, h=1680, ppi="300 / 150", kind="彩色", year="2025-10", src="readwithpro"),
    dict(name="Smart 5C", w=1860, h=2480, ppi="300 / 150", kind="彩色", year="2024-09", src="readwithpro"),
    dict(name="Smart 6C Pro", w=1860, h=2480, ppi="300 / 150", kind="彩色", year="2026-04", src="readwithpro"),
]


def diagonal_inch(w, h, ppi):
    """按分辨率与 PPI 反算对角英寸，用于标称尺寸校验。"""
    try:
        return ((w / ppi) ** 2 + (h / ppi) ** 2) ** 0.5
    except Exception:
        return 0.0


def short_ppi(ppi_text):
    """取 PPI 文本里的黑白 PPI 数值。"""
    try:
        return float(str(ppi_text).split("/")[0].strip())
    except Exception:
        return 0.0


def label_for(m, orientation="portrait"):
    w, h = m["w"], m["h"]
    if orientation == "landscape":
        w, h = h, w
    d = diagonal_inch(m["w"], m["h"], short_ppi(m["ppi"]))
    size = ("%.1f\"" % d) if d else "—"
    return "%s  ·  %d×%d  ·  %s  ·  %s" % (m["name"], w, h, size, m["ppi"])
