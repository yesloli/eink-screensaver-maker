# 怎么推到 GitHub

这个文件夹**已经 `git init` 过**，分支是 `main`，`.gitignore` 也配好了，还没有任何提交。
CI（`.github/workflows/build.yml`）已就位：推送跑自检，打 tag 自动打包并发 Release，
所以**不需要**手动把 EXE 拖到网页上。

## 1. 填提交身份（只需一次）

```bash
git config user.name "yesloli"
git config user.email "yesloli@users.noreply.github.com"
```

> 想全局生效就加 `--global`。邮箱用 GitHub 的 noreply 地址，避免把真实邮箱写进提交历史。

## 2. 第一次提交

```bash
git add .
git commit -m "墨水屏阅读器屏保制作：按机型原生分辨率批量出屏保，含 54 台掌阅机型库与扩展黑白点"
```

提交前确认 `git status` 里没有 `build/`、`dist/`、`selftest*.txt`——`.gitignore` 已经挡住了，
`crop_studio.spec` 则**必须**在提交里（它是打包配置，不是自动生成的）。

## 3. 建远程仓库

GitHub 网页新建一个空仓库，**不要**勾选 README / .gitignore / license（不然会有冲突）。
仓库名 `eink-screensaver-maker`，与已有的 `eink-manga-resize` 保持一致的命名风格。
创建后把仓库描述填上：

> 电子墨水屏阅读器屏保批量裁切：按机型原生分辨率出图，54 台掌阅机型，扩展黑白点让 16 级灰阶全部用上

## 4. 关联并推送

```bash
git remote add origin git@github.com:yesloli/eink-screensaver-maker.git
git push -u origin main
```

用 HTTPS 的话地址换 `https://github.com/yesloli/eink-screensaver-maker.git`，
密码位置填 Personal Access Token（Settings → Developer settings → Tokens (classic)，勾 `repo`）。

推送后 Actions 会自动跑 `check`（语法 + 自检），一两分钟出结果。

## 5. 发版：打个 tag 就行

```bash
git tag -a v1.0.0 -m "v1.0.0 首个版本"
git push origin v1.0.0
```

CI 会打包 EXE、用打好的 EXE 自己跑一遍 `--selftest`、通过后才把它作为附件发到 Release。
附件名是纯 ASCII 的 `eink-screensaver-maker-v1.0.0-windows-x64.exe`。

> **为什么附件要 ASCII 名**：GitHub Release 处理非 ASCII 附件名时会丢掉原名。
> 上一个项目实测中文名变成了 `default.exe`——页面上靠 label 仍显示中文，
> 但下载存盘就是 `default.exe`。CI 里已经另存了 ASCII 副本，别再手动改回中文。

发版还要同步改三处：

| 文件 | 改什么 |
|---|---|
| `crop_studio.py` | `VER = "1.0.0"` |
| `CHANGELOG.md` | 顶部加新条目 |
| `.github/release-notes.md` | 「本版本要点」整段换掉（`body_path` 读的就是它） |

## 如果 4 步之后就后悔了

```bash
git remote -v                         # 看当前关联
git remote set-url origin <新地址>     # 换地址
git remote remove origin              # 删掉关联重来
```

## 注意

- 这个目录里的 `.git` 是从打包机带过来的，只有配置、没有任何提交记录，
  不会带那台机器的历史或身份。
- 二进制不进货仓。EXE 只在 CI 的 Release 附件里，仓库里没有。
