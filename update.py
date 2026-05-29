#!/usr/bin/env python3
"""TVBox 聚合源 - 全流程播放测速，按持续速度排序"""
import json, sys, re, subprocess, os, time
from urllib.parse import urljoin, urlparse

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(WORK_DIR, "tvbox.json")

def fetch(url, timeout=10):
    try:
        r = subprocess.run(["curl", "-s", "-L", "--connect-timeout", str(timeout),
                           "--max-time", str(timeout*2), "-A", "Mozilla/5.0", url],
                          capture_output=True, timeout=timeout*2+5)
        return r.stdout.decode("utf-8", errors="replace")
    except:
        return ""

def build_url(base, params):
    sep = "&" if "?" in base else "?"
    return base.rstrip("/") + sep + params

def extract_m3u8(text):
    return re.findall(r'(https?://[^\s"\'<>#\$]+?\.m3u8)', text)

def resolve_url(base, path):
    if path.startswith("http"): return path
    if path.startswith("/"): return f"{urlparse(base).scheme}://{urlparse(base).netloc}{path}"
    return urljoin(base, path)

def get_segments(media, media_url):
    urls = []
    lines = media.strip().split("\n")
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and i+1 < len(lines):
            nxt = lines[i+1].strip()
            if nxt and not nxt.startswith("#"):
                urls.append(resolve_url(media_url, nxt))
    return urls

def test_play(api, stype):
    base = re.sub(r'[?&]ac=list.*', '', api.rstrip("/"))
    body = fetch(build_url(base, "ac=list"), timeout=10)
    if not body or len(body) < 50: return 0, 0, 0, "列表失败"
    vod_id = None
    if stype == 0:
        m = re.findall(r'<id>(\d+)</id>', body)
        vod_id = m[0] if m else None
    else:
        try:
            j = json.loads(body, strict=False)
            vod_id = str(j["list"][0]["vod_id"]) if j.get("list") else None
        except: return 0, 0, 0, "解析失败"
    if not vod_id: return 0, 0, 0, "无ID"
    detail = fetch(build_url(base, f"ac=detail&ids={vod_id}"), timeout=10)
    play_url = None
    if stype == 0:
        urls = extract_m3u8(detail)
        play_url = urls[0] if urls else None
    else:
        try:
            dj = json.loads(detail, strict=False)
            vl = dj.get("list", [])
            if vl: play_url = extract_m3u8(vl[0].get("vod_play_url", ""))[0]
        except: return 0, 0, 0, "详情失败"
    if not play_url: return 0, 0, 0, "无播放URL"
    t0 = time.time()
    master = fetch(play_url, timeout=10)
    ttfb = int((time.time() - t0) * 1000)
    if not master: return ttfb, 0, 0, "主列表空"
    media_url = None
    if "#EXT-X-STREAM-INF" in master:
        lines = master.strip().split("\n")
        for i, line in enumerate(lines):
            if "STREAM-INF" in line and i+1 < len(lines):
                sub = lines[i+1].strip()
                if sub and not sub.startswith("#"):
                    media_url = resolve_url(play_url, sub); break
    elif "#EXTINF" in master: media_url = play_url
    if not media_url: return ttfb, 0, 0, "无媒体列表"
    t1 = time.time()
    media = fetch(media_url, timeout=10)
    media_ms = int((time.time() - t1) * 1000)
    if "#EXTINF" not in media: return ttfb+media_ms, 0, 0, "无分片信息"
    segs = get_segments(media, media_url)
    if not segs: return ttfb+media_ms, 0, 0, "无分片"
    total_b, total_t, ok = 0, 0, 0
    for s in segs[:3]:
        r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code},%{size_download},%{time_total}",
                           "--connect-timeout","5","--max-time","15",s], capture_output=True, timeout=20)
        parts = r.stdout.decode().strip().split(",")
        code = parts[0] if parts else "000"
        size = int(float(parts[1])) if len(parts)>1 and parts[1] else 0
        dl = float(parts[2]) if len(parts)>2 and parts[2] else 99
        if code.startswith("2") and size > 1000: total_b += size; total_t += dl; ok += 1
    if ok == 0: return ttfb+media_ms, 0, 0, "分片下载失败"
    speed = int((total_b/1024)/total_t) if total_t > 0 else 0
    return ttfb+media_ms, speed, ok, "OK"

def fetch_source_list():
    html = fetch("https://tvbox.clbug.com/user.php", timeout=20)
    urls = re.findall(r'data-url="([^"]+)"', html)
    names = re.findall(r'<td class="td-name">([^<]+)</td>', html)
    return [(n.strip(), u.strip().replace("&amp;","&")) for n,u in zip(names,urls) if u.strip() and not u.strip().startswith("#")]

def fetch_and_parse(url):
    raw = fetch(url, timeout=15)
    if not raw.strip() or raw.strip().startswith("<"): return None
    raw = raw.lstrip('﻿'); raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    try: return json.loads(raw, strict=False)
    except:
        s,e = raw.find('{'), raw.rfind('}')
        if s>=0 and e>s:
            try: return json.loads(raw[s:e+1], strict=False)
            except: pass
    return None

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始更新...")
    sources = fetch_source_list()
    print(f"  获取到 {len(sources)} 个源")
    
    configs = []
    for name, url in sources:
        try:
            start = time.time()
            r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}","--connect-timeout","8","--max-time","15","-L","-A","Mozilla/5.0",url], capture_output=True, timeout=20)
            code = r.stdout.decode().strip()
            lat = int((time.time()-start)*1000) if code.startswith(("2","3")) else 99999
        except: lat = 99999
        if lat >= 99999: continue
        data = fetch_and_parse(url)
        if data: configs.append((name, url, lat, data))
        sys.stdout.write(f"\r  测试: {len(configs)}/{len(sources)}"); sys.stdout.flush()
    print()
    
    # 收集采集站
    apis = {}
    all_lives, all_parses = [], []
    live_keys, parse_keys = set(), set()
    for name, url, lat, data in configs:
        for s in (data.get("sites") or []):
            st = s.get("type",-1); api = s.get("api","")
            if st in (0,1) and api.startswith("http") and api not in apis:
                apis[api] = (s.get("name",""), st)
        for l in (data.get("lives") or []):
            u = l.get("url","")
            if u and u not in live_keys: live_keys.add(u); all_lives.append(l)
        for p in (data.get("parses") or []):
            u = p.get("url","")
            if u and u not in parse_keys: parse_keys.add(u); all_parses.append(p)
    
    print(f"  采集站: {len(apis)} 个，开始播放测速...")
    results = []
    for api, (name, st) in apis.items():
        ttfb, speed, segs, status = test_play(api, st)
        ok = status == "OK"
        results.append((ok, ttfb, speed, segs, name, api, st, status))
        mark = "ok" if ok else "fail"
        sys.stdout.write(f"\r  测速: {len(results)}/{len(apis)} [{mark}]"); sys.stdout.flush()
    print()
    
    ok_list = sorted([(a,b,c,d,e,f,g,h) for a,b,c,d,e,f,g,h in results if a], key=lambda x:(-x[2],x[1]))
    for _, ttfb, speed, segs, name, _, _, _ in ok_list:
        print(f"    ✅ [{speed}KB/s|{ttfb}ms|{segs}片] {name}")
    
    sites = []
    for _, ttfb, speed, segs, name, api, st, _ in ok_list:
        clean = re.sub(r'^\[.*?\]\s*', '', name)
        stable = "稳" if speed > 500 else "中" if speed > 100 else "慢"
        sites.append({"key":clean, "name":f"[{speed}KB/s|{ttfb}ms|{stable}] {clean}",
                      "type":st, "api":api, "searchable":1, "quickSearch":1, "filterable":0})
    
    result = {"spider":"", "sites":sites, "lives":all_lives, "parses":all_parses}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(WORK_DIR,"sources.txt"), "w") as f:
        f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for name,url,lat,_ in configs: f.write(f"[{lat}ms] {name}\n{url}\n\n")
    print(f"\n  sites:{len(sites)} lives:{len(all_lives)} parses:{len(all_parses)}")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 完成!")
    return 0

if __name__ == "__main__": sys.exit(main())
