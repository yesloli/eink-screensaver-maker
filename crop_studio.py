# -*- coding: utf-8 -*-
"""
墨水屏阅读器屏保制作 · 桌面版

把 legacy/crop-tool.html（最早的单页网页版）的能力固化成单文件 EXE：
  · 每张图单独定位、缩放，状态各自记住
  · 预览画布严格按所选机型的像素比例显示
  · 内置掌阅 iReader 机型分辨率库（见 models.py 的来源说明）
  · 导出按机型原生分辨率渲染的 8 位灰度 PNG

依赖：Pillow；拖放可选 tkinterdnd2（没有则自动退化为按钮选文件）。

命令行：
  --selftest [报告文件]   无界面跑一遍完整渲染链，写报告并按成败给退出码
  --version              打印版本号
"""

import os
import sys
import json
import math
import shutil
import tempfile
import traceback

try:  # Windows 高 DPI：不做这一步，缩放 125%/150% 的机器上整个界面是糊的
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps

try:  # 可选：装了 pillow-heif 才能读 iPhone / 相机直出的 .heic
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

try:
    from models import MODELS, short_ppi
except Exception:  # 单文件打包时 models 会被一起并进来，这里只是兜底
    MODELS = []
    def short_ppi(x):
        return 0.0

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _BASE_TK = TkinterDnD.Tk
    _HAS_DND = True
except Exception:
    _BASE_TK = tk.Tk
    _HAS_DND = False
    DND_FILES = None

# ───────────────────────── 配色 & 字体 ─────────────────────────
PAPER = "#f5f3ee"
CARD = "#ffffff"
INK = "#1b1b19"
INK2 = "#4a4a44"
INK3 = "#8b867a"
LINE = "#e3ded2"
LINE2 = "#d3cdbe"
ACCENT = "#b4402a"
ACCENT_HOVER = "#9d3623"
ACCENT_BG = "#f7e8e3"
STAGE = "#e9e6de"

FONT = "Microsoft YaHei UI"

IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic", ".heif", ".jfif")
TH = 62                  # 图片条缩略图边长
MAX_BASE = 2600          # 预览用底图的最长边：够 5 倍放大看细节，又不吃内存
APP_NAME = "墨水屏阅读器屏保制作"
VER = "1.0.0"


# ───────────────────────── 工具函数 ─────────────────────────
def cover_scale(iw, ih, ow, oh):
    return max(ow / iw, oh / ih)


def clamp_pos(it, ow, oh):
    s = cover_scale(it.iw, it.ih, ow, oh) * it.zoom
    w, h = it.iw * s, it.ih * s
    it.tx = min(0.0, max(ow - w, it.tx))
    it.ty = min(0.0, max(oh - h, it.ty))


def center(it, ow, oh):
    s = cover_scale(it.iw, it.ih, ow, oh) * it.zoom
    it.tx = (ow - it.iw * s) / 2.0
    it.ty = (oh - it.ih * s) / 2.0
    clamp_pos(it, ow, oh)


def tone_lut(gamma=0.96, contrast=1.06, brightness=0.01):
    """复刻 ffmpeg 的 eq=contrast=1.06:gamma=0.96:brightness=0.01。"""
    lut = []
    for v in range(256):
        x = (v / 255.0) ** gamma * 255.0
        x = (x - 128.0) * contrast + 128.0 + brightness * 255.0
        lut.append(max(0, min(255, int(round(x)))))
    return lut


TONE_LUT = tone_lut()


def build_lut(lo, hi, expand, tone):
    """把「扩展黑白点」+「轻微提对比」合成一张 256 项查找表。

    扩展黑白点 = 把这张图的实际黑/白点线性铺到 0–255，让面板那 16 级灰阶
    全部用上；强度 s 只是在原图和拉满之间做插值，所以 0 就是完全不动。
    两个参数都是中性时返回 None，调用方据此跳过 point()。
    """
    s = max(0, min(100, int(expand))) / 100.0
    if s <= 0 and not tone:
        return None
    span = float(hi - lo)
    lut = []
    for v in range(256):
        x = float(v)
        if s > 0 and span >= 8:
            t = (x - lo) * 255.0 / span
            t = 0.0 if t < 0.0 else (255.0 if t > 255.0 else t)
            x += (t - x) * s
        if tone:
            y = (x / 255.0) ** 0.96 * 255.0
            y = (y - 128.0) * 1.06 + 128.0 + 2.55
            x = y
        lut.append(max(0, min(255, int(round(x)))))
    return lut


def render_crop(path, iw, ih, ow, oh, zoom, tx, ty, lut, gray=True):
    """按「构图 + 目标尺寸 + 查找表」渲染一张成品。

    纯函数，不碰界面状态：App._render 与 --selftest 共用同一条渲染链，
    这样自检跑通就等于界面点导出跑通。
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        s = cover_scale(iw, ih, ow, oh) * zoom
        # 构图坐标是浮点算出来的：当 iw*s 正好等于 ow 时，tx 可能落在 ±1e-16 上，
        # box 起点因此变成 -1e-16，Pillow 直接抛 "box offset can't be negative"。
        # GUI 侧靠 clamp_pos 恰好挡住了，但导出链不该依赖那个巧合——这里自己夹一次。
        x0 = min(max(-tx / s, 0.0), float(iw))
        y0 = min(max(-ty / s, 0.0), float(ih))
        x1 = min(max((ow - tx) / s, x0), float(iw))
        y1 = min(max((oh - ty) / s, y0), float(ih))
        if x1 - x0 < 1.0 or y1 - y0 < 1.0:      # 构图被推到图外，退化成 1px 避免除零
            x1, y1 = min(iw, x0 + 1.0), min(ih, y0 + 1.0)
        out = im.resize((ow, oh), Image.LANCZOS, box=(x0, y0, x1, y1))
    if gray:
        out = out.convert("L")
        if lut is not None:
            out = out.point(lut)
    elif lut is not None:
        out = out.point(lut * 3)
    return out


def cfg_path():
    try:
        base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
        if os.access(base, os.W_OK):
            return os.path.join(base, "screen-maker.json")
    except Exception:
        pass
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "EinkScreenMaker")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return os.path.join(d, "settings.json")


def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ───────────────────────── 图片项 ─────────────────────────
def level_points(im, clip=0.005):
    """按直方图找黑点 / 白点（各裁掉 clip 比例的极值），用于"扩展黑白点"。"""
    hist = im.convert("L").histogram()
    total = float(sum(hist)) or 1.0
    lo, hi = 0, 255
    acc = 0
    for v in range(256):
        acc += hist[v]
        if acc / total >= clip:
            lo = v
            break
    acc = 0
    for v in range(255, -1, -1):
        acc += hist[v]
        if acc / total >= clip:
            hi = v
            break
    if hi - lo < 8:          # 已经跑满（或几乎纯色），别动
        return 0, 255
    return lo, hi


class Item(object):
    __slots__ = ("path", "name", "iw", "ih", "base", "f", "zoom", "tx", "ty",
                 "done", "thumb", "lo", "hi", "_lut", "_lutkey")

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.zoom = 1.0
        self.tx = 0.0
        self.ty = 0.0
        self.done = False
        self.thumb = None
        self._lut = None
        self._lutkey = None
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            self.iw, self.ih = im.size
            self.f = 1.0
            if max(self.iw, self.ih) > MAX_BASE:
                self.f = MAX_BASE / float(max(self.iw, self.ih))
            bw, bh = max(1, int(round(self.iw * self.f))), max(1, int(round(self.ih * self.f)))
            self.base = im.convert("RGB").resize((bw, bh), Image.LANCZOS)
        self.lo, self.hi = level_points(self.base)


# ───────────────────────── 主窗口 ─────────────────────────
class App(object):
    def __init__(self, root):
        self.root = root
        self.items = []
        self.cur = -1
        self._pending = False
        self._photo = None
        self._fit_job = None
        self._loading = False
        self._busy = False                # 批量导出进行中，挡住重入

        self.cfg = self._load_cfg()
        self.custom_size = None            # (w, h) 或 None
        self.model_name = None
        self.out_dir = self.cfg.get("out_dir", "")
        self._model_iid = {}
        self._syncing = False
        self._drag = None

        root.title(APP_NAME)
        root.configure(bg=PAPER)
        root.minsize(1020, 700)
        root.geometry(self.cfg.get("geometry", "1320x930"))
        try:
            ico = resource_path("app.ico")
            if os.path.exists(ico):
                root.iconbitmap(ico)
        except Exception:
            pass

        self._build_style()
        self._build_menu()
        self._build_ui()
        self._restore_state()
        self._load_models(self.cfg.get("filter", ""), first=True)
        self._bind_keys()
        self._bind_dnd()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(60, self._initial_fit)
        # 命令行带路径 = 直接载入（把图片拖到 exe 图标上也能用）
        args = [a for a in sys.argv[1:] if os.path.exists(a)]
        if args:
            self.root.after(120, lambda: self._insert_paths(args))

    # ---------- 配置 ----------
    def _load_cfg(self):
        try:
            with open(cfg_path(), "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _save_cfg(self):
        try:
            geo = self.root.geometry()
            if self.root.state() == "zoomed":
                # 最大化时记下还原后的尺寸，别把最大化状态存进去（下次启动会开成全屏）
                geo = self.cfg.get("geometry", "1320x930")
            self.cfg.update({
                "geometry": geo,
                "model": self.model_name,
                "orient": self.var_orient.get(),
                "custom": list(self.custom_size) if self.custom_size else None,
                "gray": bool(self.var_gray.get()),
                "tone": bool(self.var_tone.get()),
                "expand": int(self.var_expand.get()),
                "fmt": self.var_fmt.get(),
                "out_dir": self.out_dir,
                "filter": self.var_filter.get(),
            })
            with open(cfg_path(), "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # ---------- 样式 ----------
    def _build_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("M.Treeview", background=CARD, fieldbackground=CARD, foreground=INK2,
                     borderwidth=0, relief="flat", rowheight=22, font=(FONT, 9))
        st.configure("M.Treeview.Heading", background="#fbfaf7", foreground=INK3,
                     relief="flat", font=(FONT, 8, "bold"), padding=(2, 4))
        st.map("M.Treeview",
               background=[("selected", ACCENT_BG)],
               foreground=[("selected", ACCENT)])
        st.layout("M.Treeview", [("M.Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Bar.Horizontal.TProgressbar", background=ACCENT, troughcolor="#f1eee7",
                     borderwidth=0, thickness=6)
        st.configure("M.TCombobox", fieldbackground="#fbfaf7", background="#fbfaf7",
                     foreground=INK, arrowcolor=INK2, bordercolor=LINE2, padding=3)
        # 滑块：clam 主题下手柄颜色取自 background，必须显式给 accent，否则白手柄落在白底上
        st.configure("Z.Horizontal.TScale", background=ACCENT, troughcolor="#eae6dd",
                     borderwidth=0, lightcolor=ACCENT, darkcolor="#8e3121",
                     bordercolor=CARD, sliderlength=22, sliderthickness=13)
        st.map("Z.Horizontal.TScale",
               background=[("active", ACCENT_HOVER)],
               lightcolor=[("active", ACCENT_HOVER)])
        st.configure("M.Vertical.TScrollbar", background="#efebe2", troughcolor=CARD,
                     bordercolor=CARD, arrowcolor=INK3, lightcolor="#efebe2",
                     darkcolor="#efebe2", gripcount=0, arrowsize=9, width=9)
        st.map("M.Vertical.TScrollbar", background=[("active", "#e2ddd0")])

    # ---------- 菜单 ----------
    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0, bg=CARD, fg=INK, activebackground=ACCENT_BG,
                    activeforeground=ACCENT, bd=0)
        f = tk.Menu(m, tearoff=0, bg=CARD, fg=INK, activebackground=ACCENT_BG, activeforeground=ACCENT)
        f.add_command(label="添加图片…", accelerator="Ctrl+O", command=self.add_files)
        f.add_command(label="添加文件夹…", command=self.add_folder)
        f.add_separator()
        f.add_command(label="设置输出目录…", command=self.choose_out_dir)
        f.add_separator()
        f.add_command(label="退出", command=self.on_close)
        m.add_cascade(label="文件", menu=f)

        h = tk.Menu(m, tearoff=0, bg=CARD, fg=INK, activebackground=ACCENT_BG, activeforeground=ACCENT)
        h.add_command(label="扩展黑白点说明", command=self.show_expand_help)
        h.add_command(label="机型库说明", command=self.show_about)
        h.add_command(label="快捷键", command=self.show_keys)
        m.add_cascade(label="帮助", menu=h)
        self.root.config(menu=m)

    # ---------- 界面 ----------
    def _build_ui(self):
        outer = tk.Frame(self.root, bg=PAPER)
        outer.pack(fill="both", expand=True, padx=14, pady=12)

        left = tk.Frame(outer, bg=PAPER)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(outer, bg=PAPER, width=336)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        # ---- 左：预览舞台 ----
        head = tk.Frame(left, bg=PAPER)
        head.pack(fill="x")
        tk.Label(head, text=APP_NAME, bg=PAPER, fg=INK, font=(FONT, 14, "bold")).pack(side="left")
        tk.Label(head, text="框内即成品 · 全程本地 · 不上传", bg=PAPER, fg=INK3,
                 font=(FONT, 9)).pack(side="left", padx=(10, 0), pady=(3, 0))

        holder = tk.Frame(left, bg=STAGE)
        holder.pack(fill="both", expand=True, pady=(8, 6))
        self.holder = holder
        self.canvas = tk.Canvas(holder, bg=STAGE, highlightthickness=0, bd=0, cursor="fleur")
        self.canvas.pack(expand=True)
        self.cvw, self.cvh = 800, 600
        self.canvas.config(width=self.cvw, height=self.cvh)
        holder.bind("<Configure>", self._on_holder_resize)

        # ---- 左：图片条（缩略图横排） ----
        bar = tk.Frame(left, bg=PAPER)
        bar.pack(fill="x", pady=(0, 5))
        self._flat_btn(bar, "＋ 添加图片", self.add_files, primary=True).pack(side="left")
        self._flat_btn(bar, "添加文件夹", self.add_folder).pack(side="left", padx=(6, 0))
        self._flat_btn(bar, "移除这张", self.remove_cur).pack(side="left", padx=(6, 0))
        self.lbl_count = tk.Label(bar, text="", bg=PAPER, fg=INK3, font=(FONT, 8))
        self.lbl_count.pack(side="right")

        strip_wrap = tk.Frame(left, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        strip_wrap.pack(fill="x")
        self.strip = tk.Canvas(strip_wrap, height=TH + 12, bg=CARD, highlightthickness=0, bd=0)
        self.strip.pack(fill="x", padx=4, pady=4)
        self.strip.bind("<Button-1>", self._on_strip_click)
        self.strip.bind("<MouseWheel>", self._on_strip_wheel)

        foot = tk.Frame(left, bg=PAPER)
        foot.pack(fill="x", pady=(5, 0))
        self.lbl_info = tk.Label(foot, text="未载入图片", bg=PAPER, fg=INK3, font=(FONT, 9), anchor="w")
        self.lbl_info.pack(side="left")
        self.lbl_pos = tk.Label(foot, text="—", bg=PAPER, fg=INK3, font=(FONT, 9), anchor="e")
        self.lbl_pos.pack(side="right")

        # ---- 右：面板（顺序即优先级：窗口太矮时最后一块被裁，所以核心控件放前面）----
        self._build_model_box(right)
        self._build_crop_box(right)
        self._build_out_box(right)
        self._build_tip_box(right)

    def _card(self, parent, title, expand=False):
        f = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        f.pack(fill="both" if expand else "x", expand=expand, pady=(0, 8))
        tk.Label(f, text=title, bg=CARD, fg=INK3, font=(FONT, 8, "bold"), anchor="w").pack(
            fill="x", padx=12, pady=(8, 3))
        body = tk.Frame(f, bg=CARD)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 9))
        return body

    def _flat_btn(self, parent, text, cmd, primary=False, width=None):
        b = tk.Button(parent, text=text, command=cmd,
                      bg=ACCENT if primary else "#fbfaf7",
                      fg="#ffffff" if primary else INK,
                      activebackground=ACCENT_HOVER if primary else "#f2efe8",
                      activeforeground="#ffffff" if primary else INK,
                      font=(FONT, 9, "bold" if primary else "normal"),
                      relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                      highlightthickness=1,
                      highlightbackground=ACCENT if primary else LINE2,
                      highlightcolor=ACCENT if primary else LINE2)
        if width:
            b.config(width=width)
        return b

    # ---------- 机型卡片 ----------
    def _build_model_box(self, parent):
        body = self._card(parent, "机型与输出尺寸")

        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="筛选", bg=CARD, fg=INK3, font=(FONT, 9)).pack(side="left")
        self.var_filter = tk.StringVar(value=self.cfg.get("filter", ""))
        e = tk.Entry(row, textvariable=self.var_filter, bg="#fbfaf7", fg=INK, relief="flat",
                     font=(FONT, 9), insertbackground=INK, highlightthickness=1,
                     highlightbackground=LINE2, highlightcolor=ACCENT, width=12)
        e.pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=3)
        self.var_filter.trace_add("write", lambda *a: self._load_models(self.var_filter.get()))

        tv_wrap = tk.Frame(body, bg=CARD)
        tv_wrap.pack(fill="x", pady=(7, 0))
        self.model_tv = ttk.Treeview(tv_wrap, columns=("name", "res"), show="headings",
                                     height=6, style="M.Treeview", selectmode="browse")
        self.model_tv.heading("name", text="机型", anchor="w")
        self.model_tv.heading("res", text="分辨率", anchor="e")
        self.model_tv.column("name", width=196, anchor="w", stretch=True)
        self.model_tv.column("res", width=86, anchor="e", stretch=False)
        sb = ttk.Scrollbar(tv_wrap, orient="vertical", command=self.model_tv.yview,
                           style="M.Vertical.TScrollbar")
        self.model_tv.configure(yscrollcommand=sb.set)
        self.model_tv.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.model_tv.bind("<<TreeviewSelect>>", self._on_model_pick)

        orow = tk.Frame(body, bg=CARD)
        orow.pack(fill="x", pady=(9, 0))
        self.var_orient = tk.StringVar(value=self.cfg.get("orient", "portrait"))
        for txt, val in (("竖屏", "portrait"), ("横屏", "landscape")):
            rb = tk.Radiobutton(orow, text=txt, value=val, variable=self.var_orient,
                                bg=CARD, fg=INK2, selectcolor=CARD, activebackground=CARD,
                                activeforeground=INK, font=(FONT, 9), bd=0,
                                highlightthickness=0, command=self._on_orient_change)
            rb.pack(side="left", padx=(0, 12))

        self.lbl_size = tk.Label(body, text="—", bg=CARD, fg=ACCENT, font=(FONT, 10, "bold"), anchor="w")
        self.lbl_size.pack(fill="x", pady=(6, 0))
        self.lbl_size_sub = tk.Label(body, text="", bg=CARD, fg=INK3, font=(FONT, 8), anchor="w")
        self.lbl_size_sub.pack(fill="x")

        crow = tk.Frame(body, bg=CARD)
        crow.pack(fill="x", pady=(8, 0))
        tk.Label(crow, text="自定义", bg=CARD, fg=INK3, font=(FONT, 9)).pack(side="left")
        self.var_custom = tk.StringVar(value="")
        ce = tk.Entry(crow, textvariable=self.var_custom, bg="#fbfaf7", fg=INK, relief="flat",
                      font=(FONT, 9), insertbackground=INK, highlightbackground=LINE2,
                      highlightcolor=ACCENT, highlightthickness=1, width=9)
        ce.pack(side="left", padx=(6, 6), ipady=3)
        ce.bind("<Return>", lambda e: self._apply_custom())
        self._flat_btn(crow, "应用", self._apply_custom).pack(side="left")

    # ---------- 图片条 ----------
    def _thumb(self, it):
        bw, bh = it.base.size
        s = max(TH / float(bw), TH / float(bh))
        nw, nh = max(TH, int(round(bw * s))), max(TH, int(round(bh * s)))
        im = it.base.resize((nw, nh), Image.BILINEAR)
        l, t = (nw - TH) // 2, (nh - TH) // 2
        return im.crop((l, t, l + TH, t + TH))

    def _rebuild_strip(self):
        c = self.strip
        c.delete("all")
        if not self.items:
            c.create_text(14, (TH + 12) / 2, anchor="w", fill=INK3, font=(FONT, 9),
                          text="还没有图片 · 把图片拖进窗口，或点左上「添加图片」")
            c.configure(scrollregion=(0, 0, 1, TH + 12))
            self.lbl_count.config(text="")
            return
        for i, it in enumerate(self.items):
            x, y = i * (TH + 10) + 4, 4
            on = (i == self.cur)
            if it.thumb is None:
                it.thumb = ImageTk.PhotoImage(self._thumb(it))
            c.create_rectangle(x - 2, y - 2, x + TH + 2, y + TH + 2,
                               outline=ACCENT if on else LINE2, width=2 if on else 1,
                               fill="#ffffff")
            c.create_image(x + TH / 2, y + TH / 2, image=it.thumb)
            if it.done:
                c.create_oval(x + TH - 13, y + TH - 13, x + TH - 1, y + TH - 1,
                              fill="#2b7355", outline="#ffffff", width=2)
        total = len(self.items) * (TH + 10) + 6
        c.configure(scrollregion=(0, 0, max(total, c.winfo_width()), TH + 12))
        self.lbl_count.config(text="共 %d 张 · 已导出 %d 张" %
                              (len(self.items), sum(1 for i in self.items if i.done)))
        self._see_strip(self.cur)

    def _see_strip(self, i):
        if i < 0:
            return
        c = self.strip
        total = max(1, len(self.items) * (TH + 10) + 6)
        left = c.canvasx(0)
        right = left + max(1, c.winfo_width())
        x = i * (TH + 10)
        if x - 4 < left:
            c.xview_moveto(max(0.0, (x - 4) / float(total)))
        elif x + TH + 12 > right:
            c.xview_moveto(max(0.0, (x + TH + 12 - right + left) / float(total)))

    def _on_strip_click(self, e):
        if not self.items:
            return
        idx = int(self.strip.canvasx(e.x) // (TH + 10))
        if 0 <= idx < len(self.items) and idx != self.cur:
            self.cur = idx
            self._sync_zoom_ui()
            self._rebuild_strip()
            self.request_draw()

    def _on_strip_wheel(self, e):
        self.strip.xview_scroll(-1 if e.delta > 0 else 1, "units")

    # ---------- 裁切 ----------
    def _build_crop_box(self, parent):
        body = self._card(parent, "裁切")
        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="缩放", bg=CARD, fg=INK3, font=(FONT, 9)).pack(side="left")
        self.var_zoom = tk.IntVar(value=100)
        self.scale = ttk.Scale(row, from_=100, to=500, orient="horizontal",
                               variable=self.var_zoom, command=self._on_zoom_slider,
                               style="Z.Horizontal.TScale")
        self.scale.pack(side="left", fill="x", expand=True, padx=(8, 6))
        self.lbl_zoom = tk.Label(row, text="100%", bg=CARD, fg=INK2, font=(FONT, 9),
                                 width=5, anchor="e")
        self.lbl_zoom.pack(side="right")

        row2 = tk.Frame(body, bg=CARD)
        row2.pack(fill="x", pady=(8, 0))
        self._flat_btn(row2, "铺满", self.do_fit).pack(side="left")
        self._flat_btn(row2, "重置", self.do_reset).pack(side="left", padx=(6, 0))
        self._flat_btn(row2, "构图套用全部", self.apply_to_all).pack(side="right")

    # ---------- 说明 ----------
    def _build_tip_box(self, parent):
        body = self._card(parent, "扩展黑白点 · 建议值")
        tbl = tk.Frame(body, bg=CARD)
        tbl.pack(fill="x")
        tbl.columnconfigure(0, weight=1)
        recs = (("Carta 1.0 及以前", "80"),
                ("Carta 1.2", "60–70"),
                ("Carta 1000", "50–60"),
                ("Carta 1200", "30–40"),
                ("Carta 1300", "10–20"),
                ("彩色 Kaleido 3", "40–60"))
        for i, (name, val) in enumerate(recs):
            tk.Label(tbl, text=name, bg=CARD, fg=INK3, font=(FONT, 8), pady=0,
                     anchor="w").grid(row=i, column=0, sticky="w")
            tk.Label(tbl, text=val, bg=CARD, fg=INK2, font=(FONT, 8), pady=0,
                     anchor="e").grid(row=i, column=1, sticky="e", padx=(10, 0))
        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x", pady=(7, 0))
        self._flat_btn(row, "这是什么", self.show_expand_help).pack(side="left")
        self._flat_btn(row, "快捷键", self.show_keys).pack(side="left", padx=(6, 0))

    # ---------- 输出 ----------
    def _build_out_box(self, parent):
        body = self._card(parent, "输出")

        # 扩展黑白点：独立滑块，不跟机型绑定
        self.var_expand = tk.IntVar(value=max(0, min(100, int(self.cfg.get("expand", 40)))))
        row0 = tk.Frame(body, bg=CARD)
        row0.pack(fill="x")
        tk.Label(row0, text="扩展黑白点", bg=CARD, fg=INK3, font=(FONT, 9)).pack(side="left")
        ttk.Scale(row0, from_=0, to=100, orient="horizontal", variable=self.var_expand,
                  command=self._on_expand, style="Z.Horizontal.TScale").pack(
            side="left", fill="x", expand=True, padx=(8, 6))
        self.lbl_expand = tk.Label(row0, text="%d" % self.var_expand.get(), bg=CARD, fg=INK2,
                                   font=(FONT, 9), width=4, anchor="e")
        self.lbl_expand.pack(side="right")

        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self.var_gray = tk.BooleanVar(value=self.cfg.get("gray", True))
        self.var_tone = tk.BooleanVar(value=self.cfg.get("tone", True))
        for txt, var in (("转 8 位灰度", self.var_gray), ("轻微提对比", self.var_tone)):
            cb = tk.Checkbutton(row, text=txt, variable=var, bg=CARD, fg=INK2, selectcolor=CARD,
                                activebackground=CARD, activeforeground=INK, font=(FONT, 9),
                                bd=0, highlightthickness=0, command=self._on_toggle)
            cb.pack(side="left", padx=(0, 10))
        self.var_fmt = tk.StringVar(value=self.cfg.get("fmt", "png"))
        cbx = ttk.Combobox(row, textvariable=self.var_fmt, values=("png", "jpg"), width=5,
                           state="readonly", style="M.TCombobox", font=(FONT, 8))
        cbx.pack(side="right")
        tk.Label(row, text="格式", bg=CARD, fg=INK3, font=(FONT, 8)).pack(side="right", padx=(0, 4))

        row3 = tk.Frame(body, bg=CARD)
        row3.pack(fill="x", pady=(9, 0))
        self._flat_btn(row3, "保存这张", self.save_one, primary=True).pack(side="left", fill="x", expand=True)
        self._flat_btn(row3, "保存全部", self.save_all).pack(side="left", padx=(6, 0), fill="x", expand=True)

        self.lbl_out = tk.Label(body, text="", bg=CARD, fg=INK3, font=(FONT, 8), anchor="w",
                                wraplength=280, justify="left")
        self.lbl_out.pack(fill="x", pady=(6, 0))

    # ───────────── 机型库 ─────────────
    def _load_models(self, kw="", first=False):
        kw = (kw or "").strip().lower()
        rows = []
        for m in MODELS:
            hay = (m["name"] + " %dx%d %s %s" % (m["w"], m["h"], m["ppi"], m["kind"])).lower()
            if kw and kw not in hay:
                continue
            p = short_ppi(m["ppi"])
            d = ((m["w"] / p) ** 2 + (m["h"] / p) ** 2) ** 0.5 if p else 0
            rows.append((m, "%.1f\"" % d if d else "—"))
        self.model_tv.delete(*self.model_tv.get_children())
        self._model_iid = {}
        rows.sort(key=lambda r: (r[0]["kind"] != "黑白", -short_ppi(r[0]["ppi"]),
                                 r[0]["h"] * r[0]["w"]))
        for m, size in rows:
            iid = self.model_tv.insert("", "end", values=(m["name"], "%d×%d" % (m["w"], m["h"])))
            self._model_iid[iid] = m
        self._resolve_selection(first)

    def _resolve_selection(self, first=False):
        if self.custom_size:
            self._refresh_size_label()
            return
        for iid, m in self._model_iid.items():
            if m["name"] == self.model_name:
                self.model_tv.selection_set(iid)
                self.model_tv.see(iid)
                self._refresh_size_label()
                return
        # 当前机型被筛掉了：不动输出尺寸，只把选中态清掉
        if not first:
            self._refresh_size_label()
            return
        kids = self.model_tv.get_children()
        if not kids:
            return
        target = kids[0]
        for iid in kids:
            if self._model_iid[iid]["name"] == "Ocean 3 Plus":
                target = iid
                break
        self.model_tv.selection_set(target)
        self.model_tv.see(target)
        self.model_name = self._model_iid[target]["name"]
        self._refresh_size_label()

    def _restore_state(self):
        self.model_name = self.cfg.get("model") or "Ocean 3 Plus"
        cs = self.cfg.get("custom")
        if cs and isinstance(cs, list) and len(cs) == 2:
            try:
                self.custom_size = (int(cs[0]), int(cs[1]))
                self.var_custom.set("%dx%d" % self.custom_size)
            except Exception:
                self.custom_size = None

    def model(self):
        for m in MODELS:
            if m["name"] == self.model_name:
                return m
        return MODELS[0] if MODELS else dict(name="自定义", w=1680, h=1264, ppi="300", kind="黑白")

    def out_size(self):
        if self.custom_size:
            return self.custom_size
        m = self.model()
        return (m["w"], m["h"]) if self.var_orient.get() == "portrait" else (m["h"], m["w"])

    def _refresh_size_label(self):
        ow, oh = self.out_size()
        r = ow / float(oh)
        if self.custom_size:
            self.lbl_size.config(text="%d × %d  自定义" % (ow, oh))
            self.lbl_size_sub.config(text="比例 %.3f : 1" % r)
        else:
            m = self.model()
            d = ((m["w"] / short_ppi(m["ppi"])) ** 2 + (m["h"] / short_ppi(m["ppi"])) ** 2) ** 0.5 \
                if short_ppi(m["ppi"]) else 0
            self.lbl_size.config(text="%d × %d  %s" % (ow, oh, m["kind"]))
            sub = ("%.1f 寸 · %s PPI · %s 上市" % (d, m["ppi"], m["year"])) if d else m["ppi"]
            self.lbl_size_sub.config(text=sub + " · 比例 %.3f : 1" % r)
        # 只有自定义尺寸才需要提醒：机型库里的 758×1024（Light 系列）是真实分辨率，
        # 拿 1024×768 当门槛会把它一起误报成「分辨率偏小」。
        if self.custom_size and ow * oh < 600 * 800:
            self.lbl_out.config(text="提示：该分辨率偏小，屏保会被放大，建议先确认设备实际像素。")
        else:
            self.lbl_out.config(text="")

    def _on_model_pick(self, _evt=None):
        sel = self.model_tv.selection()
        if not sel:
            return
        m = self._model_iid.get(sel[0])
        if not m:
            return
        old = self.out_size()
        self.custom_size = None
        self.var_custom.set("")
        self.model_name = m["name"]
        self._after_size_change(old)

    def _on_orient_change(self):
        old = self.out_size()
        self._after_size_change(old)

    def _apply_custom(self):
        txt = self.var_custom.get().strip().lower().replace("×", "x").replace("*", "x")
        try:
            a, b = txt.split("x")
            w, h = int(a), int(b)
            if not (100 <= w <= 8000 and 100 <= h <= 8000):
                raise ValueError
        except Exception:
            messagebox.showwarning(APP_NAME, "自定义尺寸请写成「宽x高」，例如 1264x1680，范围 100–8000。")
            return
        old = self.out_size()
        self.custom_size = (w, h)
        self._after_size_change(old)

    def _after_size_change(self, old):
        new = self.out_size()
        if old != new:
            for it in self.items:
                so = cover_scale(it.iw, it.ih, old[0], old[1]) * it.zoom
                ncx = (old[0] / 2.0 - it.tx) / (it.iw * so)
                ncy = (old[1] / 2.0 - it.ty) / (it.ih * so)
                sn = cover_scale(it.iw, it.ih, new[0], new[1]) * it.zoom
                it.tx = new[0] / 2.0 - ncx * it.iw * sn
                it.ty = new[1] / 2.0 - ncy * it.ih * sn
                clamp_pos(it, new[0], new[1])
        self._refresh_size_label()
        self._fit_canvas()
        self.request_draw()

    # ───────────── 画布尺寸 ─────────────
    def _initial_fit(self):
        self._fit_canvas()
        self._rebuild_strip()
        self.draw()

    def _on_holder_resize(self, _evt=None):
        if self._fit_job:
            self.root.after_cancel(self._fit_job)
        self._fit_job = self.root.after(80, self._fit_canvas)

    def _fit_canvas(self):
        self._fit_job = None
        if self.holder.winfo_width() < 60 or self.holder.winfo_height() < 60:
            return  # 还没完成布局，等 <Configure>
        ow, oh = self.out_size()
        aw = max(160, self.holder.winfo_width() - 28)
        ah = max(120, self.holder.winfo_height() - 28)
        r = ow / float(oh)
        if aw / float(ah) > r:
            h = ah
            w = h * r
        else:
            w = aw
            h = w / r
        self.cvw, self.cvh = max(120, int(w)), max(90, int(h))
        self.canvas.config(width=self.cvw, height=self.cvh)
        self.canvas.pack(expand=True)
        self.request_draw()   # 画布尺寸变了必须重画，否则会留着一张旧尺寸的小图

    # ───────────── 绘制 ─────────────
    def current(self):
        if 0 <= self.cur < len(self.items):
            return self.items[self.cur]
        return None

    def request_draw(self):
        if self._pending:
            return
        self._pending = True
        self.root.after(10, self._do_draw)

    def _do_draw(self):
        self._pending = False
        try:
            self.draw()
        except Exception:
            traceback.print_exc()

    def _lut_for(self, it):
        """按（强度, 提对比）缓存 build_lut 的结果，避免每次重绘重算 256 项。"""
        key = (int(self.var_expand.get()), bool(self.var_tone.get()))
        if it._lutkey == key:
            return it._lut
        it._lut = build_lut(it.lo, it.hi, key[0], key[1])
        it._lutkey = key
        return it._lut

    def draw(self):
        cv = self.canvas
        cv.delete("all")
        it = self.current()
        if it is None:
            cv.create_text(self.cvw / 2, self.cvh / 2, text="把图片拖进来，或用右侧「添加图片」",
                           fill=INK3, font=(FONT, 11))
            self.lbl_info.config(text="未载入图片")
            self.lbl_pos.config(text="—")
            return
        ow, oh = self.out_size()
        s = cover_scale(it.iw, it.ih, ow, oh) * it.zoom
        x0 = max(0.0, -it.tx / s)
        y0 = max(0.0, -it.ty / s)
        x1 = min(float(it.iw), (ow - it.tx) / s)
        y1 = min(float(it.ih), (oh - it.ty) / s)
        if x1 - x0 < 1 or y1 - y0 < 1:
            return
        # 底图做过缩放（f），原图坐标乘回 f 后可能比底图大一个零头；
        # 与 render_crop 一样夹一次，Pillow 对越界 box 是直接抛异常的。
        bx, by = it.base.size
        box = (min(max(x0 * it.f, 0.0), bx), min(max(y0 * it.f, 0.0), by),
               min(max(x1 * it.f, 0.0), bx), min(max(y1 * it.f, 0.0), by))
        if box[2] - box[0] < 1 or box[3] - box[1] < 1:
            return
        img = it.base.resize((self.cvw, self.cvh), Image.BILINEAR, box=box)
        lut = self._lut_for(it)
        if self.var_gray.get():
            img = img.convert("L")
            if lut is not None:
                img = img.point(lut)
        elif lut is not None:
            img = img.point(lut * 3)
        self._photo = ImageTk.PhotoImage(img)
        cv.create_image(0, 0, image=self._photo, anchor="nw")

        self.lbl_info.config(text="原图 %d×%d · %s" % (it.iw, it.ih, it.name))
        self.lbl_pos.config(text="%d / %d · 缩放 %d%%" % (self.cur + 1, len(self.items),
                                                          round(it.zoom * 100)))

    # ───────────── 交互 ─────────────
    def _canvas_to_out(self, px, py):
        ow, oh = self.out_size()
        return px * (ow / float(self.cvw)), py * (oh / float(self.cvh))

    def _bind_keys(self):
        r = self.root
        r.bind("<Control-o>", lambda e: self.add_files())
        r.bind("<Key-Left>", lambda e: self.nudge(-1, 0, e))
        r.bind("<Key-Right>", lambda e: self.nudge(1, 0, e))
        r.bind("<Key-Up>", lambda e: self.nudge(0, -1, e))
        r.bind("<Key-Down>", lambda e: self.nudge(0, 1, e))
        r.bind("<Key-a>", lambda e: self.step(-1))
        r.bind("<Key-d>", lambda e: self.step(1))
        r.bind("<Key-Delete>", lambda e: self.remove_cur())
        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

    def _is_typing(self):
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, ttk.Combobox, tk.Text))

    def nudge(self, dx, dy, evt=None):
        if self._is_typing():
            return
        it = self.current()
        if not it:
            return
        step = 10 if (evt and (evt.state & 0x1)) else 1
        ow, oh = self.out_size()
        it.tx += dx * step
        it.ty += dy * step
        clamp_pos(it, ow, oh)
        self.request_draw()

    def step(self, d):
        if self._is_typing() or not self.items:
            return
        self.cur = (self.cur + d) % len(self.items)
        self._rebuild_strip()
        self._sync_zoom_ui()
        self.request_draw()

    def _drag_start(self, e):
        # 点画布即把键盘焦点交给画布，方向键微调才有作用。
        # 不再用 <Motion> 抢焦点——鼠标一扫过画布就把焦点从输入框抢走，边打字边挪鼠标会丢焦点。
        self.canvas.focus_set()
        if not self.current():
            return
        self._drag = (e.x, e.y)
        self.canvas.configure(cursor="fleur")

    def _drag_move(self, e):
        it = self.current()
        if not it or not getattr(self, "_drag", None):
            return
        lx, ly = self._drag
        dx, dy = self._canvas_to_out(e.x - lx, e.y - ly)
        self._drag = (e.x, e.y)
        ow, oh = self.out_size()
        it.tx += dx
        it.ty += dy
        clamp_pos(it, ow, oh)
        self.request_draw()

    def _on_wheel(self, e):
        it = self.current()
        if not it:
            return
        ow, oh = self.out_size()
        k = ow / float(self.cvw)
        px, py = e.x * k, e.y * k
        old = it.zoom
        nxt = min(5.0, max(1.0, old * (1.1 if e.delta > 0 else 1 / 1.1)))
        if abs(nxt - old) < 1e-6:
            return
        ratio = nxt / old
        it.tx = px - (px - it.tx) * ratio
        it.ty = py - (py - it.ty) * ratio
        it.zoom = nxt
        clamp_pos(it, ow, oh)
        self._sync_zoom_ui()
        self.request_draw()

    def _on_zoom_slider(self, _v=None):
        if self._syncing:
            return
        it = self.current()
        if not it:
            return
        ow, oh = self.out_size()
        nxt = max(1.0, min(5.0, self.var_zoom.get() / 100.0))
        ratio = nxt / it.zoom
        cx, cy = ow / 2.0, oh / 2.0
        it.tx = cx - (cx - it.tx) * ratio
        it.ty = cy - (cy - it.ty) * ratio
        it.zoom = nxt
        clamp_pos(it, ow, oh)
        self.lbl_zoom.config(text="%d%%" % round(it.zoom * 100))
        self.request_draw()

    def _sync_zoom_ui(self):
        it = self.current()
        if not it:
            return
        self._syncing = True
        self.var_zoom.set(int(round(it.zoom * 100)))
        self.lbl_zoom.config(text="%d%%" % round(it.zoom * 100))
        self._syncing = False

    def do_fit(self):
        it = self.current()
        if not it:
            return
        it.zoom = 1.0
        ow, oh = self.out_size()
        center(it, ow, oh)
        self._sync_zoom_ui()
        self.request_draw()

    def do_reset(self):
        it = self.current()
        if not it:
            return
        it.done = False
        self.do_fit()
        self._refresh_list_row(self.cur)

    def apply_to_all(self):
        src = self.current()
        if not src or len(self.items) < 2:
            return
        ow, oh = self.out_size()
        s = cover_scale(src.iw, src.ih, ow, oh) * src.zoom
        ncx = (ow / 2.0 - src.tx) / (src.iw * s)
        ncy = (oh / 2.0 - src.ty) / (src.ih * s)
        for it in self.items:
            if it is src:
                continue
            it.zoom = src.zoom
            sn = cover_scale(it.iw, it.ih, ow, oh) * it.zoom
            it.tx = ow / 2.0 - ncx * it.iw * sn
            it.ty = oh / 2.0 - ncy * it.ih * sn
            clamp_pos(it, ow, oh)
        self.request_draw()
        messagebox.showinfo(APP_NAME, "已把当前这张的缩放与构图中心套用到全部 %d 张。" % len(self.items))

    def _on_toggle(self):
        self.request_draw()

    def _on_expand(self, _v=None):
        lbl = getattr(self, "lbl_expand", None)
        if lbl is not None:
            try:
                lbl.config(text="%d" % int(round(float(self.var_expand.get()))))
            except Exception:
                pass
        self.request_draw()

    # ───────────── 图片增删 ─────────────
    def _insert_paths(self, paths):
        paths = [p for p in paths if p.lower().endswith(IMG_EXTS)]
        if not paths:
            return
        added = 0
        failed = []
        # 同一个文件用不同写法（反斜杠 / 正斜杠、大小写）拖两次不该进来两条
        seen = set(os.path.normcase(os.path.abspath(it.path)) for it in self.items)
        for p in paths:
            key = os.path.normcase(os.path.abspath(p))
            if key in seen:
                continue
            try:
                it = Item(p)
            except Exception as ex:
                failed.append("%s (%s)" % (os.path.basename(p), ex))
                continue
            seen.add(key)
            ow, oh = self.out_size()
            center(it, ow, oh)
            self.items.append(it)
            added += 1
        if added:
            if self.cur < 0:
                self.cur = 0
            self._rebuild_strip()
            self._sync_zoom_ui()
            self.request_draw()
        if failed:
            messagebox.showwarning(APP_NAME, "以下文件打不开：\n" + "\n".join(failed[:8]))

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片", " ".join("*" + e for e in IMG_EXTS)), ("所有文件", "*.*")])
        if paths:
            self._insert_paths(list(paths))

    def add_folder(self):
        d = filedialog.askdirectory(title="选择文件夹（只取这一层）")
        if not d:
            return
        try:
            names = sorted(os.listdir(d))
        except Exception as ex:
            messagebox.showerror(APP_NAME, "读取目录失败：%s" % ex)
            return
        self._insert_paths([os.path.join(d, n) for n in names])

    def _refresh_list_row(self, idx):
        self._rebuild_strip()

    def _sync_list_sel(self):
        self._see_strip(self.cur)

    def remove_cur(self):
        # Delete 是绑在 root 上的全局快捷键，焦点在输入框时必须放手，
        # 否则在筛选框里按 Delete 删一个字符，会顺带删掉一张图。
        if self._is_typing():
            return
        if not (0 <= self.cur < len(self.items)):
            return
        self.items.pop(self.cur)
        if self.cur >= len(self.items):
            self.cur = len(self.items) - 1
        self._rebuild_strip()
        self._sync_zoom_ui()
        self.request_draw()

    # ───────────── 导出 ─────────────
    def _render(self, it, ow, oh):
        return render_crop(it.path, it.iw, it.ih, ow, oh, it.zoom, it.tx, it.ty,
                           self._lut_for(it), bool(self.var_gray.get()))

    def _render_to(self, it, path, ow, oh):
        """渲染并落盘，写成功才标记 done。单张保存与批量导出共用这一条链。"""
        self._save_img(self._render(it, ow, oh), path)
        it.done = True

    def _ext(self):
        return ".jpg" if self.var_fmt.get() == "jpg" else ".png"

    def _save_img(self, img, path):
        if path.lower().endswith((".jpg", ".jpeg")):
            img.convert("RGB").save(path, "JPEG", quality=93, subsampling=0)
        else:
            img.save(path, "PNG", optimize=True)

    def _default_dir(self):
        if self.out_dir and os.path.isdir(self.out_dir):
            return self.out_dir
        it = self.current()
        return os.path.dirname(it.path) if it else os.path.expanduser("~")

    def choose_out_dir(self):
        d = filedialog.askdirectory(title="选择输出目录", initialdir=self._default_dir())
        if d:
            self.out_dir = d
            self._save_cfg()

    def save_one(self):
        it = self.current()
        if not it:
            messagebox.showinfo(APP_NAME, "先载入一张图片。")
            return
        ow, oh = self.out_size()
        stem = os.path.splitext(it.name)[0]
        init = os.path.join(self._default_dir(), "%s_%dx%d%s" % (stem, ow, oh, self._ext()))
        path = filedialog.asksaveasfilename(
            title="保存屏保", initialdir=os.path.dirname(init), initialfile=os.path.basename(init),
            defaultextension=self._ext(),
            filetypes=[("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg")])
        if not path:
            return
        try:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            self._render_to(it, path, ow, oh)
            self._refresh_list_row(self.cur)
            self.root.config(cursor="")
        except Exception as ex:
            self.root.config(cursor="")
            messagebox.showerror(APP_NAME, "保存失败：%s" % ex)
            return
        self._toast("已保存 %d×%d · %s" % (ow, oh, os.path.basename(path)))
        self.step(1)

    def save_all(self):
        if self._busy:
            return
        if not self.items:
            messagebox.showinfo(APP_NAME, "还没有图片。")
            return
        d = filedialog.askdirectory(title="选择输出目录", initialdir=self._default_dir())
        if not d:
            return
        self.out_dir = d
        ow, oh = self.out_size()
        ext = self._ext()
        # 导出途中界面仍在刷新（update()），用户可能删图、切图甚至再点一次导出。
        # 用快照遍历，循环就不会被中途变动的列表带偏。
        items = list(self.items)
        self._busy = True
        win = None
        ok = fail = 0
        errors = []
        used = set()          # 同一批里的重名（不同目录下都叫 cover.jpg）不能互相覆盖
        try:
            win, bar, lbl = self._progress_win("导出中", len(items))
            for i, it in enumerate(items):
                lbl.config(text="%d / %d  %s" % (i + 1, len(items), it.name))
                bar["value"] = i
                self.root.update()
                head = "%s_%dx%d" % (os.path.splitext(it.name)[0], ow, oh)
                name, n = head + ext, 2
                while name.lower() in used:
                    name, n = "%s_%d%s" % (head, n, ext), n + 1
                used.add(name.lower())
                try:
                    self._render_to(it, os.path.join(d, name), ow, oh)
                    ok += 1
                except Exception as ex:
                    fail += 1
                    errors.append("%s: %s" % (it.name, ex))
            bar["value"] = len(items)
        except Exception as ex:
            errors.append("导出中断：%s" % ex)
            fail = max(fail, len(items) - ok)
        finally:
            self._busy = False
            if win is not None:
                win.destroy()
        self._rebuild_strip()          # 一次重建就够，不必每张都刷一遍图片条
        msg = "完成：成功 %d 张，失败 %d 张。\n输出目录：%s" % (ok, fail, d)
        if errors:
            msg += "\n\n失败明细：\n" + "\n".join(errors[:6])
        messagebox.showinfo(APP_NAME, msg)

    def _progress_win(self, title, total):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PAPER)
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text=title, bg=PAPER, fg=INK, font=(FONT, 10, "bold")).pack(
            padx=22, pady=(16, 6), anchor="w")
        lbl = tk.Label(win, text="准备中…", bg=PAPER, fg=INK3, font=(FONT, 9))
        lbl.pack(padx=22, anchor="w")
        bar = ttk.Progressbar(win, maximum=max(1, total), style="Bar.Horizontal.TProgressbar",
                              length=320)
        bar.pack(padx=22, pady=(8, 18))
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry("+%d+%d" % (x, y))
        return win, bar, lbl

    def _toast(self, text):
        self.lbl_out.config(text=text)

    # ───────────── 拖放 ─────────────
    def _bind_dnd(self):
        if not _HAS_DND:
            return
        for w in (self.root, self.canvas, self.holder):
            try:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
            except Exception:
                pass

    def _on_drop(self, e):
        try:
            paths = list(self.root.tk.splitlist(e.data))
        except Exception:
            paths = [e.data]
        files = []
        for p in paths:
            p = p.strip("{}")
            if os.path.isdir(p):
                files += [os.path.join(p, n) for n in sorted(os.listdir(p))]
            else:
                files.append(p)
        self._insert_paths(files)

    # ───────────── 说明 ─────────────
    def show_expand_help(self):
        messagebox.showinfo("扩展黑白点 · 说明", (
            "【它做什么】\n"
            "相机直出、扫描件、网图，像素其实大多没跑满 0–255：暗部停在 20 上下，\n"
            "高光只到 235 左右。墨水屏的 16 级灰阶是固定铺在 0–255 上的，图只占了\n"
            "中间一段，等于把 16 级用成了 13 级。\n\n"
            "这个滑块把每张图自己的黑点 / 白点线性拉到 0 和 255。强度 0 = 完全不动，\n"
            "100 = 拉满，中间值是插值，所以它调的是「渐变程度」而不是开关。\n"
            "黑点白点是每张图各自按直方图算的（各裁掉两端 0.5% 的极端像素），\n"
            "不是全局统一参数。\n\n"
            "【各代面板建议值】\n"
            "Carta 1.0 及以前（Pearl / 早期，10–15:1）　　80\n"
            "Carta 1.2（15:1，2016–2021 主力）　　　　　60–70\n"
            "Carta 1000　　　　　　　　　　　　　　　　 50–60\n"
            "Carta 1200（≈17:1，2021–2024 主力）　　　 30–40\n"
            "Carta 1300（≈20:1，2023 至今）　　　　　　10–20\n"
            "彩色 Kaleido 3（彩膜拉低反射率）　　　　　40–60\n\n"
            "老屏要拉得更狠，是因为面板对比度低、白态本来就发灰，16 级之间已经很挤，\n"
            "图再浪费一截就真糊成一片。新屏（1300）自带余量，轻推一点就够，\n"
            "拉过头反而削掉高光。\n\n"
            "【两个提醒】\n"
            "· 拉得越狠，16 级之间每级跳变越大。设备 256 级抖动如果是关着的，\n"
            "  会出现更明显的色带——别盲拉，看着预览调。\n"
            "· 它不会凭空增加对比度，只是把图里已有的范围铺开。已经调过对比的图，\n"
            "  拉满也几乎看不出变化。"))

    def show_about(self):
        messagebox.showinfo(APP_NAME + " · 机型库", (
            "机型库覆盖掌阅 iReader 历代阅读器与手写本，共 %d 条。\n\n"
            "数据来源优先级：\n"
            "1. 掌阅官方新闻稿 / 官方参数（Ocean 3 Plus、Smart Xs、\n"
            "   Smart 2、Ocean 6 系列等）\n"
            "2. readwithpro.com 的 iReader 品牌档案（逐台标注面板与分辨率，\n"
            "   并区分「官方标注」与「按 PPI 推算」）\n"
            "3. 太平洋电脑网 / 中关村在线 —— 仅作交叉验证\n\n"
            "中关村与太平洋的参数偶有笔误（例如把 6 寸的 C6 写成\n"
            "1872×1404、把 Smart 3 写成 1404×872），凡与 PPI 数学\n"
            "不自洽的数值一律未采用。\n\n"
            "电子纸面板物理上是竖屏，厂商标称常写作横向（如 7 寸标\n"
            "1680×1264）。所以工具里每台机器都提供竖屏 / 横屏两种输\n"
            "出，按你设备的实际显示方向选。\n\n"
            "找不到你的机型时，用「自定义」直接填像素尺寸。" % max(1, len(MODELS))))

    def show_keys(self):
        messagebox.showinfo(APP_NAME + " · 快捷键", (
            "拖动画面        移动构图\n"
            "滚轮            以指针为中心缩放\n"
            "方向键          微调 1px（按住 Shift 为 10px）\n"
            "A / D           上一张 / 下一张\n"
            "Ctrl + O        添加图片\n"
            "Delete          从列表移除当前图\n\n"
            "每张图的缩放与位置各自记住，切来切去不会丢。\n"
            "「构图套用全部」把当前这张的构图中心与缩放复制给所有图，\n"
            "适合同一个系列（比如同一套漫画封面）批量出图。"))

    # ───────────── 关闭 ─────────────
    def on_close(self):
        if self._busy:
            # 批量导出跑在界面线程里，这时候关窗会把写了一半的图留下
            if not messagebox.askyesno(APP_NAME, "正在批量导出，现在退出会中断。确定退出吗？"):
                return
        self._save_cfg()
        self.root.destroy()


def _say(s):
    """windowed 打包后 sys.stdout 可能是 None，print 会炸——自检里一律走这里。"""
    try:
        if sys.stdout is not None:
            print(s)
    except Exception:
        pass


# ───────────────────────── 自检 ─────────────────────────
PANEL_INCHES = (6.0, 6.13, 6.8, 7.0, 8.0, 8.2, 10.3, 10.65)


def selftest(out_path="selftest.txt"):
    """无界面跑一遍完整渲染链，返回退出码（0 正常）。

    覆盖 cover 构图 → LANCZOS 重采样 → 8 位灰度 → 查找表 → PNG 落盘 → 回读比对，
    外加机型库的分辨率/PPI 自洽性。CI 打包后必跑，过不了就不发 Release。
    """
    lines, fails = [], []

    def ok(cond, msg):
        lines.append(("PASS  " if cond else "FAIL  ") + msg)
        if not cond:
            fails.append(msg)
        return cond

    lines.append("%s %s · selftest" % (APP_NAME, VER))
    lines.append("python %s" % sys.version.split()[0])
    lines.append("机型库 %d 条" % len(MODELS))

    # 打包完整性：图标必须能从 _MEIPASS 取到，否则冻结后窗口是默认白纸图标
    ico = resource_path("app.ico")
    ok(os.path.exists(ico) and os.path.getsize(ico) > 2000,
       "图标资源可读（%s）" % (("%d 字节" % os.path.getsize(ico)) if os.path.exists(ico) else "缺失"))

    # 拖放只是个便利功能，缺了不影响出图：这里只报告状态，不计入失败
    dnd = "未安装 tkinterdnd2（自动退化为按钮选图）"
    if _HAS_DND:
        try:
            r = _BASE_TK()
            r.withdraw()
            r.destroy()
            dnd = "可用"
        except Exception as ex:
            dnd = "Tk 启动失败：%s" % ex
    lines.append("拖放支持：%s（仅提示，不计失败）" % dnd)
    lines.append("")

    tmp = None
    try:
        tmp = tempfile.mkdtemp(prefix="crop-selftest-")
        # 灰阶均匀分布的测试图：level_points 能算出接近 13/242 的黑白点
        made = []
        for name, w, h in (("tall_4x3.png", 1200, 1600),
                           ("banner_16x5.png", 1920, 400),
                           ("long_1x6.png", 600, 4000)):
            p = os.path.join(tmp, name)
            g = Image.linear_gradient("L").resize((w, h), Image.BILINEAR)
            g = g.point(lambda v: 12 + v * 231 // 255)
            Image.merge("RGB", (g, g, g)).save(p)
            made.append((name, p))

        targets = ((1440, 1920, "8 寸竖屏"), (1264, 1680, "7 寸竖屏"), (1680, 1264, "7 寸横屏"))

        for name, p in made:
            with Image.open(p) as im0:
                iw, ih = ImageOps.exif_transpose(im0).size
            with Image.open(p) as im1:
                lo, hi = level_points(ImageOps.exif_transpose(im1).convert("RGB"))
            ok(lo < 40 and hi > 210, "%s 黑白点识别 lo=%d hi=%d" % (name, lo, hi))

            for ow, oh, tag in targets:
                s = cover_scale(iw, ih, ow, oh)
                tx, ty = (ow - iw * s) / 2.0, (oh - ih * s) / 2.0
                label = "%s → %dx%d %s" % (name, ow, oh, tag)

                plain = render_crop(p, iw, ih, ow, oh, 1.0, tx, ty, None, True)
                if not ok(plain.size == (ow, oh), label + " 尺寸精确"):
                    continue
                ok(plain.mode == "L", label + " 输出为 8 位灰度")

                # cover 必须铺满：四边不能留黑（否则等于图没盖住画布）
                edges = [plain.crop((0, 0, ow, 1)).tobytes(),
                         plain.crop((0, oh - 1, ow, oh)).tobytes(),
                         plain.crop((0, 0, 1, oh)).tobytes(),
                         plain.crop((ow - 1, 0, ow, oh)).tobytes()]
                edge_min = min(min(e) for e in edges)
                ok(edge_min > 0, label + " 四边铺满无黑边（最暗 %d）" % edge_min)

                # 扩展黑白点拉满后，动态范围只能变大不能变小
                wide = render_crop(p, iw, ih, ow, oh, 1.0, tx, ty,
                                   build_lut(lo, hi, 100, True), True)
                a, b = plain.getextrema(), wide.getextrema()
                ok(b[1] - b[0] >= a[1] - a[0],
                   label + " 扩展黑白点后动态范围 %d→%d" % (a[1] - a[0], b[1] - b[0]))

                # 落盘再回读，确认 PNG 链路无损
                f = os.path.join(tmp, "out_%d.png" % len(fails))
                wide.save(f, "PNG", optimize=True)
                with Image.open(f) as back:
                    same = (back.size == wide.size and back.mode == wide.mode
                            and back.tobytes() == wide.tobytes())
                ok(same, label + " PNG 落盘回读一致")

            # 同一输入两次渲染必须逐像素相同（幂等）
            s = cover_scale(iw, ih, 1264, 1680)
            tx, ty = (1264 - iw * s) / 2.0, (1680 - ih * s) / 2.0
            r1 = render_crop(p, iw, ih, 1264, 1680, 1.0, tx, ty, build_lut(lo, hi, 40, True), True)
            r2 = render_crop(p, iw, ih, 1264, 1680, 1.0, tx, ty, build_lut(lo, hi, 40, True), True)
            ok(r1.tobytes() == r2.tobytes(), name + " 重复渲染幂等")

        # 机型库：分辨率 ÷ PPI 反算的对角尺寸必须落在真实面板档位上
        seen, dup, bad = set(), [], []
        for m in MODELS:
            if m["name"] in seen:
                dup.append(m["name"])
            seen.add(m["name"])
            ppi = short_ppi(m["ppi"])
            if ppi <= 0:
                bad.append("%s PPI 无法解析" % m["name"])
                continue
            if m["w"] >= m["h"]:
                bad.append("%s 宽 %d 不小于高 %d（库内约定 w 为短边）" % (m["name"], m["w"], m["h"]))
            d = math.hypot(m["w"], m["h"]) / ppi
            gap = min(abs(d - x) for x in PANEL_INCHES)
            if gap > 0.15:
                bad.append("%s 反算 %.2f 寸，对不上任何面板档位" % (m["name"], d))
        ok(not dup, "机型名无重复" + ("" if not dup else "：" + "、".join(dup[:5])))
        ok(not bad, "机型参数自洽" + ("" if not bad else "：" + "；".join(bad[:6])))

    except Exception:
        fails.append("自检抛出异常")
        lines.append("FAIL  异常：\n" + traceback.format_exc())
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    lines.append("")
    lines.append("结果：%s（%d 项失败）" % ("通过" if not fails else "失败", len(fails)))
    report = "\n".join(lines)
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    except Exception:
        _say("报告写入失败：" + out_path)
    _say(report)
    return 0 if not fails else 1


def _make_root():
    """优先用它带拖放的主窗口；tcl 包在别人机器上加载失败时静默退回普通 Tk。"""
    global _HAS_DND
    if _HAS_DND:
        try:
            return _BASE_TK()
        except Exception:
            _HAS_DND = False
    return tk.Tk()


def main():
    argv = sys.argv[1:]
    if "--version" in argv or "-V" in argv:
        _say("%s %s" % (APP_NAME, VER))
        return 0
    if "--selftest" in argv:
        i = argv.index("--selftest")
        out = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") else "selftest.txt"
        return selftest(out)

    root = _make_root()
    try:
        App(root)
        root.mainloop()
    except Exception:
        tb = traceback.format_exc()
        try:
            messagebox.showerror(APP_NAME, "程序出错了：\n\n" + tb[-1500:])
        except Exception:
            pass
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
