# TVBox 聚合源

自动聚合 TVBox 影视源，每小时 GitHub Actions 自动更新。

## 使用方法

### 📺 一键配置（推荐）

直接复制地址到 TVBox/影视仓/丰米 客户端，采集站播放测速排序在前，开箱即用：

```
https://tv.cc0cd.cc.cd
```

### 📺 简洁版

仅采集站（固定前10个最快），不依赖 JAR，**真实播放测速排序**（m3u8→分片下载）：

| 渠道 | 地址 |
|------|------|
| 🔗 直链 | `https://tv.cc0cd.cc.cd/jj` |
| 🌍 GitHub | `https://raw.githubusercontent.com/25175/tvyuan/master/tvbox.json` |
| 🇨🇳 Gitee | `https://gitee.com/onm-hundred-and-eleven/tvyuan/raw/main/tvbox.json` |

### 🗄️ 全量版

全部站点合并，采集站播放测速排名在前，爬虫站延迟排名在后，带 spider JAR：

| 渠道 | 地址 |
|------|------|
| 🔗 直链 | `https://tv.cc0cd.cc.cd` |
| 🌍 GitHub | `https://raw.githubusercontent.com/25175/tvyuan/master/tvbox_full.json` |
| 🇨🇳 Gitee | `https://gitee.com/onm-hundred-and-eleven/tvyuan/raw/main/tvbox_full.json`（⚠️ Gitee 审查拦截，可能不可用） |

### 📦 多仓版

多个仓库独立保留，每个源有自己的 JAR 和站点，可切换仓库（丰米/影视仓）：

| 渠道 | 地址 |
|------|------|
| 🔗 直链 | `https://tv.cc0cd.cc.cd/multi` |
| 🇨🇳 Gitee | `https://gitee.com/onm-hundred-and-eleven/tvyuan/raw/main/tvbox_multi.json` |
| 🌍 GitHub | `https://raw.githubusercontent.com/25175/tvyuan/master/tvbox_multi.json` |

## 客户端下载

| 客户端 | 多仓 | 仓库地址 |
|--------|:----:|---------|
| TVBox 原版 | ❌ | [GitHub Releases](https://github.com/o0HalfLife0o/TVBoxOSC/releases) |
| 影视仓 | ✅ | [GitHub 仓库](https://github.com/q215613905/TVBoxOSC) |
| FongMi（丰米）| ✅ | [GitHub 仓库](https://github.com/FongMi/Release) |
| TVBox 合集下载 | - | [网盘下载](https://pan.wpcoder.cn/?dir=tvbox) |

**多仓配置方式：**
- 影视仓：首页 → 配置 → 多仓地址
- FongMi：设置 → 配置 → 多仓

## 说明

- 数据来源：[tvbox.clbug.com](https://tvbox.clbug.com/user.php)
- 每小时自动更新：测速 → 抓取 → 合并 → 推送
- 播放测速流程：获取视频 → 下载 m3u8 主列表 → 解析媒体列表 → 下载 ts 分片 → 计算持续速度
- **置顶规则**：索尼、360 固定排在前两位，其他按播放速度/延迟排序
- GitHub Actions 通过 CF Tunnel + 本地代理（国内IP）测速，突破采集站 IP 封锁
- 不可用源自动清洗，恢复后自动加回

## 更新频率

每小时整点（UTC `0 * * * *`），GitHub Actions 自动执行。
