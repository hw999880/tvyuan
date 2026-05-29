#!/usr/bin/env python3
"""
TVBox 聚合源自动更新
- tvbox.json: 全量合并（采集站+爬虫站，按延迟排序）
- tvbox_multi.json: 多仓（全部源独立保留）
"""
import json, sys, re, subprocess, os, time
from urllib.parse import urlparse

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_SINGLE = os.path.join(WORK_DIR, "tvbox.json")
OUT_MULTI  = os.path.join(WORK_DIR, "tvbox_multi.json")

def curl(url, timeout=10):
    try:
        r = subprocess.run(["curl","-s","-L","--connect-timeout",str(timeout),"--max-time",str(timeout*2),"-A","Mozilla/5.0",url],
                          capture_output=True, timeout=timeout*2+5)
        return r.stdout.decode("utf-8", errors="replace")
    except: return ""

def parse_json(raw):
    raw = raw.lstrip('﻿'); raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    try: return json.loads(raw, strict=False)
    except:
        s,e = raw.find('{'), raw.rfind('}')
        if s>=0 and e>s:
            try: return json.loads(raw[s:e+1], strict=False)
            except: pass
    return None

def resolve_spider(spider, source_url):
    if not spider: return ""
    if spider.startswith("http"): return spider
    if spider.startswith("./"):
        p = urlparse(source_url)
        return f"{p.scheme}://{p.netloc}{spider[1:]}"
    return spider

def main():
    # 5. 单仓（仅采集站，播放测速排序）
    print(f"  测采集站播放速度...")
    collect_apis = {}
    for s in all_sites:
        if s.get("type") in (0,1) and s.get("api","").startswith("http"):
            api = s["api"]
            if api not in collect_apis: collect_apis[api] = s.get("type",1)
    
    collect_ok = []
    for api, st in collect_apis.items():
        from urllib.parse import urljoin as _urljoin, urlparse as _urlparse
        base = re.sub(r'[?&]ac=list.*', '', api.rstrip("/"))
        body = curl(build_url(base, "ac=list"), 10) if False else curl(base + ("&" if "?" in base else "?") + "ac=list", 10)
        # 简单测HTTP延迟即可
        try:
            t0=time.time()
            r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}","--connect-timeout","5","--max-time","10",base],capture_output=True,timeout=15)
            lat = int((time.time()-t0)*1000) if r.stdout.decode().strip().startswith(("2","3")) else 99999
        except: lat=99999
        if lat < 99999:
            for s in all_sites:
                if s.get("api") == api:
                    collect_ok.append({"key":s.get("key",""),"name":s.get("name",""),"type":st,"api":api,"searchable":1,"quickSearch":1,"filterable":0})
                    break
    
    collect_json = {"spider":"","sites":collect_ok,"lives":[],"parses":[]}
    with open(os.path.join(WORK_DIR, "tvbox_collect.json"), "w", encoding="utf-8") as f:
        json.dump(collect_json, f, ensure_ascii=False, indent=2)
    print(f"  单仓: {len(collect_ok)} 个采集站")
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始更新...")

    # 1. 获取源列表
    html = curl("https://tvbox.clbug.com/user.php", 20)
    src_urls = re.findall(r'data-url="([^"]+)"', html)
    src_names = re.findall(r'<td class="td-name">([^<]+)</td>', html)
    sources = [(n.strip(), u.strip().replace("&amp;","&")) for n,u in zip(src_names,src_urls) if u.strip() and not u.strip().startswith("#")]
    print(f"  源列表: {len(sources)}")

    # 2. 测延迟
    available = []
    for name, url in sources:
        try:
            t0=time.time()
            r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}","--connect-timeout","5","--max-time","10","-L","-A","Mozilla/5.0",url],capture_output=True,timeout=15)
            code = r.stdout.decode().strip()
            lat = int((time.time()-t0)*1000) if code.startswith(("2","3")) else 99999
        except: lat=99999
        if lat<99999: available.append((name,url,lat))
        sys.stdout.write(f"\r  测速: {len(available)}/{len(sources)}"); sys.stdout.flush()
    print()
    available.sort(key=lambda x:x[2])
    print(f"  可用: {len(available)}")

    # 3. 多仓JSON
    multi = {"storeHouse": [{"sourceName":f"[{lat}ms] {name}","sourceUrl":url} for name,url,lat in available]}
    with open(OUT_MULTI, "w", encoding="utf-8") as f:
        json.dump(multi, f, ensure_ascii=False, indent=2)
    print(f"  多仓: {len(multi['storeHouse'])} 个")

    # 4. 全量合并
    all_sites, all_lives, all_parses = [], [], []
    site_keys, live_keys, parse_keys = set(), set(), set()
    spider_jars = {}

    for name, url, lat in available:
        sys.stdout.write(f"\r  合并: {name} ({lat}ms)"); sys.stdout.flush()
        data = parse_json(curl(url, 15))
        if not data: continue
        
        spider = data.get("spider", "")
        if spider:
            abs_spider = resolve_spider(spider, url)
            spider_jars[abs_spider] = spider_jars.get(abs_spider, 0) + 1
        
        for s in (data.get("sites") or []):
            key = s.get("key", "")
            if not key or key in site_keys: continue
            site_keys.add(key)
            s["name"] = f"[{lat}ms|{name}] {s.get('name', key)}"
            s["_lat"] = lat
            all_sites.append(s)
        
        for l in (data.get("lives") or []):
            u = l.get("url","")
            if u and u not in live_keys: live_keys.add(u); all_lives.append(l)
        
        for p in (data.get("parses") or []):
            u = p.get("url","")
            if u and u not in parse_keys: parse_keys.add(u); all_parses.append(p)
    print()

    # 选最常用spider
    best_spider = max(spider_jars, key=spider_jars.get) if spider_jars else ""

    # 按延迟排序
    all_sites.sort(key=lambda x: x.get("_lat", 99999))
    for s in all_sites: s.pop("_lat", None)

    result = {"spider": best_spider, "sites": all_sites, "lives": all_lives, "parses": all_parses}
    with open(OUT_SINGLE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 源列表
    with open(os.path.join(WORK_DIR, "sources.txt"), "w") as f:
        f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for name,url,lat in available: f.write(f"[{lat}ms] {name}\n{url}\n\n")

    types = {}
    for s in all_sites:
        t = s.get("type", -1)
        types[t] = types.get(t, 0) + 1

    print(f"  sites: {len(all_sites)} (采集:{types.get(0,0)+types.get(1,0)} 爬虫:{types.get(3,0)})")
    print(f"  lives: {len(all_lives)} parses: {len(all_parses)}")
    # 5. 单仓（仅采集站，播放测速排序）
    print(f"  测采集站播放速度...")
    collect_apis = {}
    for s in all_sites:
        if s.get("type") in (0,1) and s.get("api","").startswith("http"):
            api = s["api"]
            if api not in collect_apis: collect_apis[api] = s.get("type",1)
    
    collect_ok = []
    for api, st in collect_apis.items():
        from urllib.parse import urljoin as _urljoin, urlparse as _urlparse
        base = re.sub(r'[?&]ac=list.*', '', api.rstrip("/"))
        body = curl(build_url(base, "ac=list"), 10) if False else curl(base + ("&" if "?" in base else "?") + "ac=list", 10)
        # 简单测HTTP延迟即可
        try:
            t0=time.time()
            r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}","--connect-timeout","5","--max-time","10",base],capture_output=True,timeout=15)
            lat = int((time.time()-t0)*1000) if r.stdout.decode().strip().startswith(("2","3")) else 99999
        except: lat=99999
        if lat < 99999:
            for s in all_sites:
                if s.get("api") == api:
                    collect_ok.append({"key":s.get("key",""),"name":s.get("name",""),"type":st,"api":api,"searchable":1,"quickSearch":1,"filterable":0})
                    break
    
    collect_json = {"spider":"","sites":collect_ok,"lives":[],"parses":[]}
    with open(os.path.join(WORK_DIR, "tvbox_collect.json"), "w", encoding="utf-8") as f:
        json.dump(collect_json, f, ensure_ascii=False, indent=2)
    print(f"  单仓: {len(collect_ok)} 个采集站")
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 完成!")
    return 0

if __name__ == "__main__": sys.exit(main())
