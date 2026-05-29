#!/usr/bin/env python3
"""
TVBox 聚合源自动更新脚本
- 从 tvbox.clbug.com 获取所有源
- 逐个测速
- 合并为一个 JSON，按延迟排序
- 推送到 Gitee
"""
import json, sys, re, subprocess, os, time

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(WORK_DIR, "tvbox.json")

GITEE_TOKEN = "7d50d453f704e8d7950e5e2f7bb61bd3"
GITEE_REPO = f"https://oauth2:{GITEE_TOKEN}@gitee.com/onm-hundred-and-eleven/tvyuan.git"

# ── 第一步：从网站获取源列表 ──
def fetch_source_list():
    """从 tvbox.clbug.com 获取所有配置 URL 和名称"""
    result = subprocess.run(
        ["curl", "-s", "-L", "--connect-timeout", "10", "--max-time", "20",
         "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
         "https://tvbox.clbug.com/user.php"],
        capture_output=True, timeout=30
    )
    html = result.stdout.decode("utf-8", errors="replace")
    
    # Extract name-url pairs from table rows
    pattern = r'<td class="td-name">(.*?)</td>.*?data-url="(.*?)"'
    rows = re.findall(pattern, html, re.DOTALL)
    if not rows:
        # Fallback: extract data-url only
        urls = re.findall(r'data-url="([^"]+)"', html)
        names = re.findall(r'<td class="td-name">([^<]+)</td>', html)
        rows = list(zip(names, urls))
    
    sources = []
    for name, url in rows:
        url = url.strip().replace("&amp;", "&")
        if url and not url.startswith("#"):
            sources.append((name.strip(), url))
    return sources

# ── 第二步：测速 ──
def test_latency(url, timeout=8):
    """测量 URL 响应延迟(ms)"""
    try:
        start = time.time()
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", str(timeout), "--max-time", str(timeout * 2),
             "-L", "-A", "Mozilla/5.0", url],
            capture_output=True, timeout=timeout * 2 + 5
        )
        elapsed = int((time.time() - start) * 1000)
        code = result.stdout.decode().strip()
        if code.startswith(("2", "3")):
            return elapsed, code
        return 99999, code
    except:
        return 99999, "timeout"

# ── 第三步：抓取并合并 JSON ──
def fetch_url(url):
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--connect-timeout", "8", "--max-time", "15",
             "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", url],
            capture_output=True, timeout=20
        )
        raw = result.stdout
        for enc in ['utf-8', 'gbk', 'latin-1']:
            try:
                return raw.decode(enc)
            except:
                continue
        return raw.decode('utf-8', errors='replace')
    except:
        return ""

def parse_json(raw):
    raw = raw.lstrip('﻿')
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    try:
        return json.loads(raw, strict=False)
    except:
        pass
    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end+1], strict=False)
        except:
            pass
    return None

# ── 主流程 ──
def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始更新 TVBox 聚合源...")
    
    # 1. 获取源列表
    print("步骤1: 从 tvbox.clbug.com 获取源列表...")
    sources = fetch_source_list()
    print(f"  获取到 {len(sources)} 个源")
    
    # 2. 测速
    print("步骤2: 测速...")
    tested = []
    for name, url in sources:
        latency, code = test_latency(url)
        status = "ok" if latency < 99999 else "fail"
        tested.append((name, url, latency, code))
        sys.stdout.write(f"\r  测试中: {len(tested)}/{len(sources)} - {name} -> {latency}ms [{code}]")
        sys.stdout.flush()
    print()
    
    # 过滤可用源并排序
    available = [(n, u, l, c) for n, u, l, c in tested if l < 99999]
    available.sort(key=lambda x: x[2])
    print(f"  可用源: {len(available)}/{len(sources)}")
    
    # 3. 抓取并合并
    print("步骤3: 抓取并合并配置...")
    all_sites = []
    all_lives = []
    all_parses = []
    spider = ""
    site_keys = set()
    live_keys = set()
    parse_keys = set()
    
    for name, url, latency, code in available:
        raw = fetch_url(url)
        if not raw.strip() or raw.strip().startswith("<"):
            continue
        
        data = parse_json(raw)
        if not data:
            continue
        
        if not spider and data.get("spider"):
            spider = data["spider"]
        
        for s in (data.get("sites") or []):
            key = s.get("key", "")
            if not key or key in site_keys:
                continue
            site_keys.add(key)
            s["name"] = f"[{latency}ms] {s.get('name', key)}"
            s["_latency"] = latency
            all_sites.append(s)
        
        for l in (data.get("lives") or []):
            lurl = l.get("url", "")
            if not lurl or lurl in live_keys:
                continue
            live_keys.add(lurl)
            l["name"] = f"[{name}] {l.get('name', '直播')}"
            all_lives.append(l)
        
        for p in (data.get("parses") or []):
            purl = p.get("url", "")
            if not purl or purl in parse_keys:
                continue
            parse_keys.add(purl)
            p["name"] = f"[{name}] {p.get('name', '解析')}"
            all_parses.append(p)
    
    all_sites.sort(key=lambda x: x.get("_latency", 99999))
    for s in all_sites:
        s.pop("_latency", None)
    
    result = {
        "spider": spider,
        "sites": all_sites,
        "lives": all_lives,
        "parses": all_parses
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"  sites: {len(all_sites)}, lives: {len(all_lives)}, parses: {len(all_parses)}")
    
    # 4. 推送到 Gitee
    print("步骤4: 推送到 Gitee...")
    os.chdir(WORK_DIR)
    
    # Configure git
    subprocess.run(["git", "config", "user.email", "bot@tvbox.local"], capture_output=True)
    subprocess.run(["git", "config", "user.name", "TVBox Bot"], capture_output=True)
    
    subprocess.run(["git", "add", "-A"], capture_output=True)
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"auto update: {len(all_sites)} sites, {len(all_lives)} lives, {len(all_parses)} parses [{timestamp}]"
    result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
    
    if "nothing to commit" in result.stdout + result.stderr:
        print("  无变更，跳过推送")
    else:
        push_result = subprocess.run(
            ["git", "push", GITEE_REPO, "HEAD:main"],
            capture_output=True, text=True, timeout=30
        )
        if push_result.returncode == 0:
            # Try master as fallback
            push_result2 = subprocess.run(
                ["git", "push", GITEE_REPO, "HEAD:master"],
                capture_output=True, text=True, timeout=30
            )
        print(f"  推送完成: {msg}")
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 更新完成!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
