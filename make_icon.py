# -*- coding: utf-8 -*-
"""生成 app.ico：一块电子纸 + 里面的风景 + 裁切框。"""
import os
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角机身
d.rounded_rectangle([34, 14, 222, 242], radius=22, fill="#ffffff", outline="#b4402a", width=7)
# 屏幕（内缩，留出边框）
d.rounded_rectangle([50, 30, 206, 226], radius=10, fill="#f5f3ee")

# 屏幕里的"照片"：远山 + 太阳
d.ellipse([146, 58, 182, 94], fill="#d9a441")
d.polygon([(50, 186), (104, 110), (150, 176), (178, 140), (206, 186), (206, 226), (50, 226)],
          fill="#6d7f6a")
d.polygon([(50, 200), (92, 152), (134, 200), (50, 200)], fill="#4f6350")

# 裁切框（红框 + 四角）
box = [66, 78, 190, 210]
d.rectangle(box, outline="#b4402a", width=5)
L = 20
for (x, y, dx, dy) in ((66, 78, 1, 1), (190, 78, -1, 1), (66, 210, 1, -1), (190, 210, -1, -1)):
    d.line([(x, y), (x + dx * L, y)], fill="#b4402a", width=9)
    d.line([(x, y), (x, y + dy * L)], fill="#b4402a", width=9)

# 底部翻页键
d.rounded_rectangle([104, 232, 152, 240], radius=4, fill="#b4402a")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("saved", out)
