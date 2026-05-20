# picker

[![GitHub stars](https://img.shields.io/github/stars/Tyaoo/picker?style=flat-square)](https://github.com/Tyaoo/picker/stargazers)
[![GitHub last commit](https://img.shields.io/github/last-commit/Tyaoo/picker?style=flat-square)](https://github.com/Tyaoo/picker/commits/main)
[![License](https://img.shields.io/github/license/Tyaoo/picker?style=flat-square)](https://github.com/Tyaoo/picker/blob/main/LICENSE)

一个面向安全资讯场景的 RSS 抓取与推送工具。它基于 GitHub Actions 定时拉取订阅源，生成每日信息流、精选内容和评论提醒，适合个人安全信息跟踪或小团队协作分发。

## Table of Contents

- [Why picker](#why-picker)
- [Features](#features)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Subscription Sources](#subscription-sources)
- [Workflow Output](#workflow-output)
- [License](#license)

## Why picker

现有 RSS 工具通常只负责订阅，不处理“筛选、沉淀、协作推送”这条链路。picker 把以下几个动作串在一起：

- 自动抓取多个 RSS / OPML 订阅源
- 按天整理成信息流与精选内容
- 通过 Issue + 标签协作管理内容
- 将精选和评论变更推送到钉钉

## Features

- **每日信息流**: 默认每天早上生成前一天新增文章列表
- **每日精选**: 默认每天下午汇总昨日精选内容
- **Issue 协作**: 支持把信息流中的条目转换为精选 Issue
- **评论通知**: 对精选文章的评论会自动推送到钉钉
- **自定义订阅源**: 支持本地或远程 OPML / RSS 配置
- **标签管理**: 通过 `daily`、`dailypick`、`pick` 等标签做分类运营

## Project Structure

- `bot.py`: 推送与通知逻辑
- `yarb.py`: 采集与内容处理主流程
- `rss/`: 默认订阅源配置
- `config.yml`: RSS 源与推送配置
- `today.md` / `today_pick.md`: 每日输出示例
- `install.sh`: 本地环境安装脚本

## Installation

```bash
git clone https://github.com/Tyaoo/picker.git
cd picker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果需要完整跑通本地推送链路，还可以执行仓库自带脚本：

```bash
bash install.sh
```

## Configuration

在 `config.yml` 中启用或关闭订阅源，并为每个订阅源配置本地文件或远程 URL，例如：

```yaml
rss:
  CustomRSS:
    enabled: true
    filename: CustomRSS.opml
  CyberSecurityRSS:
    enabled: true
    url: https://raw.githubusercontent.com/zer0yu/CyberSecurityRSS/master/CyberSecurityRSS.opml
    filename: CyberSecurityRSS.opml
```

如果你要接入钉钉或其他推送目标，建议把敏感配置放在 GitHub Actions Secrets 或本地环境变量中管理。

## Usage

### 1. 生成每日信息流

仓库会在定时任务中抓取前一天新增文章，并输出到 Issue / Markdown 文件。

### 2. 标记精选内容

在每日信息流中把高质量条目转换为 Issue，或手动新建 Issue，进入精选池。

### 3. 协作打标签

通过 `daily`、`dailypick`、`pick` 等标签区分不同内容阶段，也可以增加细分标签做主题管理。

### 4. 接收评论提醒

对精选文章的评论会触发后续推送，适合团队跟踪高价值讨论。

## Subscription Sources

默认 README 已列出多组安全资讯源，包括：

- CyberSecurityRSS
- Chinese-Security-RSS
- awesome-security-feed
- SecurityRSS
- SecWiki
- wechat2rss

此外也支持导入非安全主题订阅源，例如中文独立博客列表。

## Workflow Output

picker 当前覆盖四类结果：

1. 每日信息流
2. 每日精选
3. 精选推送
4. 精选评论区推送

如果后续补一张简单的流程图，维护者和新用户会更容易理解整条链路。

## License

See [LICENSE](LICENSE).
