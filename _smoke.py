# -*- coding: utf-8 -*-
"""开发期冒烟测试：起窗口 → 置顶 → 截自身区域 → 退出。不参与打包。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crop_studio as cs
from PIL import ImageGrab

args = [a for a in sys.argv[1:] if not a.startswith("--")]
out = "shot_win.png"

root = cs._BASE_TK()
app = cs.App(root)
if args:
    app._insert_paths(args)
root.attributes("-topmost", True)


def cap():
    root.update_idletasks()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    im = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    im.save(out)
    print("SHOT", out, im.size, "canvas", app.cvw, app.cvh, "out", app.out_size())
    root.destroy()


root.after(1400, cap)
root.mainloop()
