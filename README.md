<div align="center">
  
### [🇨🇳 简体中文](README.md) | [🇺🇸 English](README_EN.md)

</div>

# ⚠️ 本仓库仅做个人维护

> **本仓库 Fork 自 [weilin9999/WeiLin-ComfyUI-prompt-all-in-one](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one)**
>
> **原作者已于 2025-03-24 归档仓库，本分支仅做 bug 修复和 tag 库扩增，不添加新功能。**
>
> 如需原版新节点请前往：[WeiLin-Comfyui-Tools](https://github.com/weilin9999/WeiLin-Comfyui-Tools)

---

## 本分支与原版的差异

### Tag 库扩展
- tag 总数从 ~3,600 扩展到 **~5,800+**（新增 ~2,200 个 tag）
- 新增 14 个顶层分类、135+ 子类
- 所有 tag 名遵循 `^[a-z][a-z0-9_]*$` 格式（如果要导入自己tag库，可按指定格式添加）

### Bug 修复
- **PromptUI 值清空 Bug**：多次点击按钮后输入内容被清空的问题已修复（`dispatchEvent(new Event('input', {bubbles: true}))`）
- **Python 3.13 兼容**：嵌入式 Python 3.13 环境下 `pkg_resources.ImpImporter` 崩溃问题已修复（setuptools 升级至 81.0.0）

### 性能优化（2026-10-15）

针对「插件一处慢、整个 ComfyUI 跟着卡」的架构问题做了三层优化（P0 启动 / P1 运行期 / P2 传输），核心思路：同步阻塞调用全部移出事件循环、加缓存、传输加 gzip+ETag。本机实测（ComfyUI 0.40 / RTX 3080）：

| 指标 | 优化前 | 优化后 |
| --- | --- | --- |
| 插件启动导入 | 7.1 秒 | 0.3~0.5 秒（降约 96%） |
| tag 库读取（228 KB） | 每请求重新解析 619 ms | 冷 3.2 ms / 热 0.01 ms |
| 修改一个 tag | 966 ms，同步卡死整个界面 | 47~477 ms，异步不冻结界面 |
| 最大 Lora（2250 MB）哈希 | 全文件 sha256 3.6~7.3 秒 | 采样指纹 7~40 ms，进程内复用 0.2 ms |
| Lora 面板接口（151 个） | 逐个全文件哈希+封面重算 | 137~181 ms；响应 139 KB → gzip 8 KB |
| 前端 JS 包 | 736 KB 明文，每次刷新重传 | gzip 228 KB，复访 HTTP 304 零传输 |
| get_config 接口 | 415 KB | gzip 后 67 KB |
| 补全词库（1.78 MB） | `no-store` 每次强制重下 | ETag + 7 天缓存，复访 304 |
| 151 个 Lora 指纹预热 | 无预热，首次打开反复计算 | 后台预热，首轮后落盘，重启命中仅 0.5 秒 |
| civitai 请求超时 | `timeout=5000`（单位是秒，≈83 分钟） | 10 秒快速失败 |

主要改动：

- **启动**：`import gradio`（约 3 秒，仅为一个类型注解）从导入链移除；requirements 依赖改为后台线程安装；`install.py` 子进程只跑一次并写 `.installed` 标记（删除该文件可强制重装一轮）；启动依赖清单精简为 tqdm，翻译 SDK 改由设置界面按需安装。
- **运行期**：`get_group_tags` 改用 PyYAML（libyaml C 实现）+ 1 秒 TTL 快照缓存，写路径协程化丢线程池并原子替换（`os.replace`）；新增 `script/lora_index.py`，Lora 校验由全文件 sha256 改为 3 MB 采样指纹，带内存 + `lora_userdata/lora_index.sqlite3` 持久缓存（civitai by-hash 仍用精确 sha256）；`get_extra_networks` 去除「线程池里套 asyncio.run」反模式，改真 async 并发，封面缩略图按文件指纹缓存；所有阻塞 IO 移出事件循环。
- **传输**：新增 `sd_webui_prompt_all_in_one_app/web_perf.py` 响应层（`on_response_prepare` 挂 gzip / ETag / Cache-Control），js 打包结果按 mtime 缓存。
- **兼容**：Python 3.13 下 `locale.getdefaultlocale()` 已移除，改为 `getlocale` + Windows API 兜底；`llama_cpp` 探测由子进程改 `importlib.util.find_spec`。
- **注意**：tag 库写回改用 PyYAML dump——如手工在 `group_tags/*.yaml` 中写注释，一次插件内改动后注释会丢失（数据本身无损）；展示字段 `sha256` 在仅有本地元数据时现为采样指纹。

---

## 安装

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/xunying7860/WeiLin-ComfyUI-prompt-all-in-one.git
```

重启 ComfyUI 即可。

---

# 以下为原版 README 内容

# 注意 本节点已不再受理任何反馈和更新！
### 本节点已不再更新，新节点会替代本节点，新节点：[WeiLin-Comfyui-Tools](https://github.com/weilin9999/WeiLin-Comfyui-Tools)，新节点会持续更新且新节点比旧节点的安装方式更便捷更好，新节点不兼容旧节点但是旧节点的Tag数据可以迁移到新节点中，详细情况请前往新节点中查看！

### 本插件已不再更新！请使用全新插件！
新插件链接：[WeiLin-Comfyui-Tools](https://github.com/weilin9999/WeiLin-Comfyui-Tools)

# 特别关注
由于本人时间有限，如果有紧急问题可以加入QQ群：1018231382
有空我会一一回答

本人更新了全新的插件，以后旧插件会逐步被新插件替代，目前还在测试不稳定，请勿直接使用新插件，
如果你想使用请务必进入QQ！需要先了解新插件的使用发放和文件迁移的工具再使用，非常感谢给位的支持！
新插件地址：https://github.com/weilin9999/WeiLin-Comfyui-Tools

# 作者声明

由于个人时间有限，更新插件的频率并不会很高，偶尔有空或许会更新一次，每次更新尽量满足所提出的需求，一般没有大的 BUG 基本上更新频率不高，一个月 2~5 更，感谢你对本插件的使用与支持，有需求可以提交 Issue 或者你可以提交你的 Request 帮助本插件更新。

# 版本更新介绍

> 最新更新：2024-11-26

> 3.6.9.1 版本介绍 （由于本人工作原因空闲时间才有时间更新插件，见谅！在此非常感谢大家对本插件的支持！）
>
> 1. 修复了合并代码中存在的问题：[#15](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/pull/15)中修改了 Lora 加载 API 导致陷入超时状态（对该代码贡献者表示感谢提供了帮助，感谢贡献者对本插件的支持，感谢每一位使用本插件的用户）
> 2. 在输入框底部新增了一件加载全部 Lora 封面功能，后台可查看加载进度，本代码由[#15](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/pull/15)贡献者提供

<details>
<summary>点击查看往期更多更新内容</summary>

> 3.6.9 版本介绍
>
> 1. 修复了已知 BUG：API 设置中的离线翻译模型翻译问题，已修复

> 3.6.8 版本介绍
>
> 1. 新增-全局快捷键（在 ComfyUI 设置中配置 默认为 CTRL+ALT+W 呼唤出全局编辑器）
> 2. 新增-悬浮球隐藏设置
> 3. 修改-设置界面优化适配了新版本的 ComfyUI 的新 UI

> 3.6.5 版本介绍 （需要备份再更新！！！本次更新会移除一些文件，所以你需要备份！）
>
> 1. 修复了 Issue：lora 的信息备注太长 ui 会被拉长看不到右边内容 √
> 2. 修复了 Issue：翻译设置里的 tagcomplete 无法使用，右上角弹出红字，csv 文件是没问题的，在 webui 的时候可以用 √
> 3. 修复了 Issue：AttributeError: module 'ctypes' has no attribute 'windll'（Linux 下语言判断） √
> 4. 修复了功能：更新不会再覆盖添加过的 Tag 信息 √
> 5. 新增了功能：快捷呼出全局窗口
> 6. 新增了功能：全局粘贴板预览

> 3.6.1 版本介绍
>
> 1. 修复了已知 BUG
> 2. 新增-全局模式中可以开启粘贴板模式，此模式下可以点击节点中任意的输入框即可弹出全局模式粘贴板，点击对应的提示词即可替换对的输入框所有文本
> 3. 修复-String 返回字符串的问题

> 3.5.0 版本介绍
>
> 0. 由于之前仓库上传了一些非常大的文件，2024-8-16 仓库进行了清空所以之前的仓库版本都删除了这是为了减小仓库大小
> 1. 修复了已知 BUG
> 2. 修改-恢复了以前旧版本的功能，支持了更多的节点搭配
> 3. 新增-增加了本地 LLM 模型使用，可以帮你续写提示词
> 4. LLM 本地模型（qwen1_5-4b-chat-q2_k.gguf）下载链接：
>    我用夸克网盘分享了「models.zip」，点击链接即可保存。打开「夸克 APP」，无需下载在线播放视频，畅享原画 5 倍速，支持电视投屏。
>    链接：https://pan.quark.cn/s/280a9ff518e3
>    提取码：qFC1

> 3.0.0 版本介绍
>
> 1. 修复了已知 BUG
> 2. 新增-Tag 添加、删除、修改 功能
> 3. 新增-开启窗口模式可以随意拖动窗口右小角可以调节窗口大小方便在 ComfyUI 中使用
> 4. 新增-Lora 查看器，在 Lora 卡片中右上角有个提示按钮点击即可查看 Lora 信息且可以同步 C 站和设置 Lora 封面的功能
> 5. 新增-Lora 的提示词有专属适配 ComfyUI 的模型强度和 CLIP 强度的调节器

> 2.4.0 版本介绍</br>1. 修复了提示词补全的 BUG</br>2. 仅中文新增了 NSFW 提示词库</br>3. 新增了 Lora 提示词自动加载，只需要在 PromptUI 添加 Lora 即可与 WebUI 提示词写法一样</br>4. 在 ComfyUI 设置里面可以修改 PromptUI 的关闭按钮切换到右边

> 2.3.0 版本介绍</br>1. 新增了提示词补全功能

> 2.2.0 版本介绍 </br>1. 修复了已知 BUG</br>2. 更新了新的功能：全局提示词 UI、放大窗口功能

</details>

# Lora 提示词写法提示

<lora:xxxx:0.3:0.4>这种写法解释 0.3 是模型强度 0.4 是 CLIP 强度
如果你是<lora:xxxx:0.4>那么这种写法解释 模型强度和 CLIP 强度都是 0.4

# 概要说明

本项目可以让你在 ComfyUI 中像 WebUI 一样写提示词，从 Prompt-all-in-one 项目修改而来但已做了大部分的修改适配 ComfyUI，新增了许多不一样的功能，以及提示词补全的插件，提示词补全插件是从 ComfyUI-Custom-Scripts 项目修改而来，感谢你对本插件的支持。

如果你对本项目有兴趣赏一个 Star 吧！

# 安装教程，可以直接 git 本项目即可

> https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one.git

# 安装插件详细介绍，手动安装版本

直接下载本项目最新的 Release 然后解压，放到 ComfyUI 直接启动 ComfyUI 即可使用本插件。
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/1.png)

# 节点使用方法

按以下操作使用即可
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/2.png)
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/3.png)
![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/4.png)

# 插件设置预览

![](https://github.com/weilin9999/WeiLin-ComfyUI-prompt-all-in-one/blob/master/step/5.png)

# WeiLin-ComfyUI-Prompt-all-in-one 借鉴项目

WeiLin-ComfyUI-Prompt-all-in-one ComfyUI 版的 prompt-all-in-one，在基于 sd-webui-prompt-all-in-one-app https://github.com/Physton/sd-webui-prompt-all-in-one-app 项目上修改而来的 ComfyUI 版本，只需要在 ComfyUI 中添加本项目的 ComfyUI 节点即可使用可视化的 tag 编辑器 ，提示词补全使用了 https://github.com/pythongosssss/ComfyUI-Custom-Scripts 项目进行修改只用了补全功能并做了修改，项目使用的本地 LLM 大模型借鉴了https://github.com/thisjam/comfyui-sixgod_prompt仓库的代码

如果你喜欢本项目赏一个 star 吧！

# 本项目简要说明

项目初始只是方便编辑 tag，所以自己写了插件，有问题可以提交 issue，不一定会处理哈。
