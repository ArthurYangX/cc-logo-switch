# Claude Logo Switch

[English](README.md) · [实现说明](docs/how-it-works.md)

把自己的 PNG 变成 **Claude Code 原生欢迎页里的彩色像素图标**，右侧继续显示版本、模型和工作目录。

实现方式是将图片转换成彩色 `▀` / `▄` 字符，再替换欢迎页组件。它不依赖 Kitty 图片协议，也不会在启动前额外打印一张大图。

| 输入 PNG | VS Code 中的 Claude 实际启动图标 |
| --- | --- |
| <img src="examples/deepseek.png" width="260" alt="输入图"> | <img src="docs/assets/claude-startup-icon.png" width="280" alt="从 VS Code 的 Claude 实际启动页截取的图标"> |

右图直接截自 VS Code 中的 Claude Code 启动页，保留实际终端配色、背景和比例。示例是 AI 生成的 DeepSeek 风格角色，也可以换成你自己的图片。

[原始 RGB 像素网格](docs/assets/pixel-preview.svg)仅用于检查转换数据，不代表安装后的截图。终端的颜色映射、字体尺寸和背景都会影响最终观感。

## 当前支持范围

- **Claude Code 2.1.318 原生版，macOS Apple Silicon。**
- Python 3.9+、Pillow、Node.js（检查注入代码语法）和 macOS `codesign`。
- 已在 VS Code 1.144.1 的终端环境验证；彩色字符方案不要求图片协议。
- 其他版本或不匹配的结构会被拒绝；Claude 自动更新可能覆盖补丁，没有自动重打补丁的钩子。

## 安装工具

如果终端无权访问 `Documents`，可以直接放在下面这个目录：

```bash
mkdir -p ~/.local/share
cd ~/.local/share
git clone https://github.com/ArthurYangX/claude-logo-switch.git
cd claude-logo-switch
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

旧命令 `png-to-claude` 仍可使用；安装记录位置保持兼容，已有备份仍能恢复。

构建和安装时，系统需要能运行 `node`。

## 使用

先预览：

```bash
claude-logo-switch preview ~/Downloads/avatar.png
```

可选 `--width 24` 调整宽度，或 `--svg /tmp/preview.svg` 保存透明矢量预览。默认 28 列，支持 12–32 之间的偶数宽度。每个字符装下上下两个像素，最多 15 个不透明颜色，透明度以 128 为阈值。

建议先构建独立副本试用，不改当前安装：

```bash
claude-logo-switch build ~/Downloads/avatar.png \
  --output ~/.local/share/claude-logo-switch/claude-preview
~/.local/share/claude-logo-switch/claude-preview
```

确认效果后安装：

```bash
claude-logo-switch install ~/Downloads/avatar.png
```

工具会生成候选文件，检查语法、签名和版本，备份当前版本，然后替换安装文件。新开一个 Claude 会话生效；现有会话不会被关闭。默认目标是 `~/.local/bin/claude`，也可用 `--target` 指定其他原生安装。

如果已经安装了图标补丁，请先用原工具恢复；本工具拒绝重复覆盖已打补丁的 header。

恢复安装前的版本：

```bash
claude-logo-switch restore
```

安装记录默认在 `~/.config/png-to-claude-code/installation.json`。安装和恢复均支持 `--state` 指定记录位置。如果 Claude 已升级或被其他工具修改，恢复命令会拒绝覆盖新文件。

## 它会保留什么

保留 header 之外已有的改动，不修改模型、API Key、shell 启动器或启动水牌。原生可执行文件和备份均保留在你自己的电脑上。

图片太高或注入代码超出当前函数的字节预算时，工具会停止构建，请裁剪图片或降低宽度。大图细节会受到终端字符分辨率和颜色数量的限制。

## 验证

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

测试覆盖透明像素、字符编码、补丁修改范围、不支持的架构和版本、备份恢复及并发改动检测。测试使用自建的可执行文件结构样本，不包含 Claude 程序本体。2.1.318 另经过本机真实交互验证，包括彩色显示、输入、窗口缩放和退出。

MIT 许可；参考项目及许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。这是非官方定制工具，与 Anthropic、DeepSeek 无隶属关系。
