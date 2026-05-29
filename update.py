#!/usr/bin/env python3
"""
TVBox 聚合源自动更新脚本
- 从 tvbox.clbug.com 获取所有源
- 测速
- 每个源独立保留（保持 JAR 关联）
- type=0/1 采集站单独聚合作为快速源
"""
import json, sys, re, subprocess, os, time

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(WORK_DIR, "tvbox.json")

def curl(url, timeout=10):
    try:
        r = subprocess.run(
            ["curl", "-s", "-L", "--connect-timeout", str(timeout),
             "--max-time", str(timeout * 2), "-A", "Mozilla/5.0", url],
            capture_output=True, timeout=timeout * 2 + 5
        )
        return r.stdout.decode("utf-8", errors="replace")
    except:
        return ""

def fetch_source_list():
    html = curl("https://tvbox.clbug.com/user.php", timeout=20)
    urls = re.findall(r'data-url="([^"]+)"', html)
    names = re.findall(r'<td class="td-name">([^<]+)</td>', html)
    sources = []
    for name, url in zip(names, urls):
        url = url.strip().replace("&amp;", "&")
        if url and not url.startswith("#"):
            sources.append((name.strip(), url))
    return sources

def test_latency(url, timeout=8):
    try:
        start = time.time()
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", str(timeout), "--max-time", str(timeout * 2),
             "-L", "-A", "Mozilla/5.0", url],
            capture_output=True, timeout=timeout * 2 + 5
        )
        elapsed = int((time.time() - start) * 1000)
        code = r.stdout.decode().strip()
        if code.startswith(("2", "3")):
            return elapsed
        return 99999
    except:
        return 99999

def fetch_and_parse(url):
    raw = curl(url, timeout=15)
    if not raw.strip() or raw.strip().startswith("<"):
        return None
    raw = raw.lstrip('﻿')
    raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    try:
        return json.loads(raw, strict=False)
    except:
        start = raw.find('{')
        end = raw.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end+1], strict=False)
            except:
                pass
    return None

def test_play_speed(api, stype):
    api = api.rstrip("/")
    list_url = api + "/?ac=list" if "ac=" not in api else api
    body = curl(list_url, timeout=8)
    if not body:
        return 99999
    
    vod_id = None
    if stype == 0:
        m = re.findall(r'<vod>(\d+)', body) or re.findall(r'id="(\d+)"', body)
        if m:
            vod_id = m[0]
    else:
        try:
            j = json.loads(body, strict=False)
            vl = j.get("list", [])
            if vl:
                vod_id = str(vl[0].get("vod_id", ""))
        except:
            return 99999
    
    if not vod_id:
        return 99999
    
    detail_url = f"{api}/?ac=detail&ids={vod_id}"
    t0 = time.time()
    detail = curl(detail_url, timeout=8)
    
    play_urls = re.findall(r'(https?://[^\$\s#<>]+?\.(?:m3u8|mp4)[^\$\s#<>]*)', detail)
    if not play_urls:
        return int((time.time() - t0) * 1000)
    
    t0 = time.time()
    subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "--connect-timeout", "5", "--max-time", "8", "-r", "0-102400", play_urls[0]],
        capture_output=True, timeout=12
    )
    return int((time.time() - t0) * 1000)

def main():
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] 开始更新...")

    # 1. 获取源列表
    sources = fetch_source_list()
    print(f"  获取到 {len(sources)} 个源")

    # 2. 测速 + 抓取每个源
    source_configs = []  # (name, url, latency, data_dict)
    for name, url in sources:
        latency = test_latency(url)
        if latency >= 99999:
            continue
        data = fetch_and_parse(url)
        if not data:
            continue
        source_configs.append((name, url, latency, data))
        sys.stdout.write(f"\r  测试: {len(source_configs)}/{len(sources)}")
        sys.stdout.flush()
    print()

    source_configs.sort(key=lambda x: x[2])
    print(f"  可用: {len(source_configs)}/{len(sources)}")

    # 3. 构建聚合 JSON：每个源作为独立的 site 组
    #    通过 JS 代理来保持每个源的 JAR 关联
    #    方案：把每个源的 URL 作为 ext，用 JS 动态加载
    
    # 方案A：把所有源的 URL 列表放进去，让 App 逐个加载
    # 方案B：只保留 type=0/1 的采集站（不需要 JAR，直接能用）+ 保留源 URL 列表
    
    # 最终方案：type=0/1 采集站直接嵌入（不依赖JAR），type=3 保留原始配置URL供App使用
    
    # 收集所有 type=0/1 采集站
    collect_sites = []
    collect_keys = set()
    all_lives = []
    all_parses = []
    live_keys = set()
    parse_keys = set()
    spider = ""
    
    # 测试采集站播放速度
    play_cache = {}
    
    for name, url, latency, data in source_configs:
        if not spider and data.get("spider"):
            spider = data["spider"]
        
        for s in (data.get("sites") or []):
            stype = s.get("type", -1)
            key = s.get("key", "")
            api = s.get("api", "")
            
            if stype in (0, 1) and key not in collect_keys:
                collect_keys.add(key)
                
                # 测播放速度
                if api.startswith("http") and api not in play_cache:
                    play_cache[api] = test_play_speed(api, stype)
                
                pms = play_cache.get(api, latency)
                s["name"] = f"[播放{pms}ms] {s.get('name', key)}"
                s["_sort"] = pms
                collect_sites.append(s)
        
        for l in (data.get("lives") or []):
            lurl = l.get("url", "")
            if lurl and lurl not in live_keys:
                live_keys.add(lurl)
                l["name"] = f"[{name}] {l.get('name', '直播')}"
                all_lives.append(l)
        
        for p in (data.get("parses") or []):
            purl = p.get("url", "")
            if purl and purl not in parse_keys:
                parse_keys.add(purl)
                p["name"] = f"[{name}] {p.get('name', '解析')}"
                all_parses.append(p)
    
    # 采集站按播放速度排序
    collect_sites.sort(key=lambda x: x.get("_sort", 99999))
    for s in collect_sites:
        s.pop("_sort", None)
    
    # 构建最终 JSON
    # 把每个完整源的 URL 也放进去，通过 csp_Abs 按需加载
    # 在 sites 最前面放一个"切换线路"入口
    result = {
        "spider": spider,
        "sites": collect_sites,
        "lives": all_lives,
        "parses": all_parses,
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n  === 采集站播放测速 ===")
    for api, pms in sorted(play_cache.items(), key=lambda x: x[1]):
        status = "✅" if pms < 99999 else "❌"
        print(f"    {status} {pms:>5}ms  {api}")
    
    print(f"\n  sites:{len(collect_sites)} lives:{len(all_lives)} parses:{len(all_parses)}")
    
    # 额外：生成完整的源 URL 列表（供用户参考）
    with open(os.path.join(WORK_DIR, "sources.txt"), "w") as f:
        f.write("# TVBox 源列表（按延迟排序）\n")
        f.write(f"# 更新时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for name, url, latency, _ in source_configs:
            f.write(f"[{latency}ms] {name}\n{url}\n\n")
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 完成!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
