# TVBox 聚合源

自动聚合 TVBox 影视源，每小时自动更新。

## 使用方法

### 多仓模式（推荐 ⭐）

全部 27 个源独立保留，每个源有自己的 JAR，**上千个播放站点**，可切换仓库：

| 网络 | 多仓地址 |
|------|---------|
| 🌍 通用 | `https://raw.githubusercontent.com/25175/tvyuan/master/tvbox_multi.json` |
| 🇨🇳 国内 | `https://gitee.com/onm-hundred-and-eleven/tvyuan/raw/master/tvbox_multi.json` |

### 单仓模式

仅采集站（type=0/1），不依赖 JAR，播放测速排序：

| 网络 | 单仓地址 |
|------|---------|
| 🌍 通用 | `https://raw.githubusercontent.com/25175/tvyuan/master/tvbox.json` |
| 🇨🇳 国内 | `https://gitee.com/onm-hundred-and-eleven/tvyuan/raw/master/tvbox.json` |

## 说明

- 数据来源：[tvbox.clbug.com](https://tvbox.clbug.com/user.php)
- **多仓**：27 个源，每个独立保留 JAR + 站点，按延迟排序
- **单仓**：采集站播放测速，m3u8→分片下载实测
- 每小时 GitHub Actions 自动更新
