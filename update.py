#!/usr/bin/env python3
"""
TVBox 聚合源自动更新
- tvbox.json: 采集站（播放测速排序，直接可用）
- tvbox_multi.json: 多仓（全部源，每个独立保留JAR）
"""
import json, sys, re, subprocess, os, time
from urllib.parse import urljoin, urlparse

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_SINGLE = os.path.join(WORK_DIR, "tvbox.json")
OUT_MULTI  = os.path.join(WORK_DIR, "tvbox_multi.json")

def curl(url, timeout=10):
    try:
        r = subprocess.run(["curl","-s","-L","--connect-timeout",str(timeout),"--max-time",str(timeout*2),"-A","Mozilla/5.0",url],
                          capture_output=True, timeout=timeout*2+5)
        return r.stdout.decode("utf-8", errors="replace")
    except: return ""

def build_url(base, p):
    return base.rstrip("/") + ("&" if "?" in base else "?") + p

def extract_m3u8(t):
    return re.findall(r'(https?://[^\s"\'<>#\$]+?\.m3u8)', t)

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
            if nxt and not nxt.startswith("#"): urls.append(resolve_url(media_url, nxt))
    return urls

def test_play(api, stype):
    base = re.sub(r'[?&]ac=list.*', '', api.rstrip("/"))
    body = curl(build_url(base, "ac=list"), 10)
    if not body or len(body)<50: return 0,0,0,"列表失败"
    vid = None
    if stype==0:
        m = re.findall(r'<id>(\d+)</id>', body)
        vid = m[0] if m else None
    else:
        try:
            j = json.loads(body, strict=False)
            vid = str(j["list"][0]["vod_id"]) if j.get("list") else None
        except: return 0,0,0,"解析失败"
    if not vid: return 0,0,0,"无ID"
    detail = curl(build_url(base, f"ac=detail&ids={vid}"), 10)
    play = None
    if stype==0:
        u = extract_m3u8(detail); play = u[0] if u else None
    else:
        try:
            dj = json.loads(detail, strict=False)
            vl = dj.get("list",[])
            if vl: u = extract_m3u8(vl[0].get("vod_play_url","")); play = u[0] if u else None
        except: return 0,0,0,"详情失败"
    if not play: return 0,0,0,"无播放URL"
    t0 = time.time()
    master = curl(play, 10)
    ttfb = int((time.time()-t0)*1000)
    if not master: return ttfb,0,0,"主列表空"
    media_url = None
    if "#EXT-X-STREAM-INF" in master:
        lines = master.strip().split("\n")
        for i, line in enumerate(lines):
            if "STREAM-INF" in line and i+1<len(lines):
                sub = lines[i+1].strip()
                if sub and not sub.startswith("#"): media_url = resolve_url(play, sub); break
    elif "#EXTINF" in master: media_url = play
    if not media_url: return ttfb,0,0,"无媒体列表"
    t1 = time.time()
    media = curl(media_url, 10)
    mms = int((time.time()-t1)*1000)
    if "#EXTINF" not in media: return ttfb+mms,0,0,"无分片信息"
    segs = get_segments(media, media_url)
    if not segs: return ttfb+mms,0,0,"无分片"
    tb,tt,ok = 0,0,0
    for s in segs[:3]:
        r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code},%{size_download},%{time_total}","--connect-timeout","5","--max-time","15",s],capture_output=True,timeout=20)
        parts = r.stdout.decode().strip().split(",")
        code = parts[0] if parts else "000"
        sz = int(float(parts[1])) if len(parts)>1 and parts[1] else 0
        dl = float(parts[2]) if len(parts)>2 and parts[2] else 99
        if code.startswith("2") and sz>1000: tb+=sz; tt+=dl; ok+=1
    if ok==0: return ttfb+mms,0,0,"分片失败"
    return ttfb+mms, int((tb/1024)/tt) if tt>0 else 0, ok, "OK"

def parse_json(raw):
    raw = raw.lstrip('﻿'); raw = re.sub(r',(\s*[}\]])', r'\1', raw)
    try: return json.loads(raw, strict=False)
    except:
        s,e = raw.find('{'), raw.rfind('}')
        if s>=0 and e>s:
            try: return json.loads(raw[s:e+1], strict=False)
            except: pass
    return None

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 更新开始")

    # 1. 获取源列表
    html = curl("https://tvbox.clbug.com/user.php", 20)
    src_urls = re.findall(r'data-url="([^"]+)"', html)
    src_names = re.findall(r'<td class="td-name">([^<]+)</td>', html)
    sources = [(n.strip(), u.strip().replace("&amp;","&")) for n,u in zip(src_names,src_urls) if u.strip() and not u.strip().startswith("#")]
    print(f"  源列表: {len(sources)}")

    # 2. 测延迟 + 抓取
    configs = []
    for name, url in sources:
        try:
            t0=time.time()
            r = subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}","--connect-timeout","5","--max-time","10","-L","-A","Mozilla/5.0",url],capture_output=True,timeout=15)
            code = r.stdout.decode().strip()
            lat = int((time.time()-t0)*1000) if code.startswith(("2","3")) else 99999
        except: lat=99999
        if lat>=99999: continue
        data = parse_json(curl(url, 15))
        if data: configs.append((name, url, lat, data))
        sys.stdout.write(f"\r  测试: {len(configs)}/{len(sources)}"); sys.stdout.flush()
    print()
    configs.sort(key=lambda x:x[2])
    print(f"  可用: {len(configs)}")

    # 3. 多仓JSON（全部源，保留各自JAR）
    multi = {"storeHouse": [{"sourceName":f"[{lat}ms] {name}", "sourceUrl":url} for name,url,lat,_ in configs]}
    with open(OUT_MULTI, "w", encoding="utf-8") as f:
        json.dump(multi, f, ensure_ascii=False, indent=2)
    print(f"  多仓: {len(multi['storeHouse'])} 个仓库")

    # 4. 采集站播放测速
    apis = {}
    all_lives, all_parses = [], []
    lk, pk = set(), set()
    for name,url,lat,data in configs:
        for s in (data.get("sites") or []):
            st=s.get("type",-1); api=s.get("api","")
            if st in (0,1) and api.startswith("http") and api not in apis:
                apis[api]=(s.get("name",""),st)
        for l in (data.get("lives") or []):
            u=l.get("url","")
            if u and u not in lk: lk.add(u); all_lives.append(l)
        for p in (data.get("parses") or []):
            u=p.get("url","")
            if u and u not in pk: pk.add(u); all_parses.append(p)

    print(f"  采集站: {len(apis)}，测播放速度...")
    results = []
    for api,(name,st) in apis.items():
        ttfb,speed,segs,status = test_play(api,st)
        results.append((status=="OK",ttfb,speed,segs,name,api,st,status))
        sys.stdout.write(f"\r  {len(results)}/{len(apis)}"); sys.stdout.flush()
    print()

    ok = sorted([(a,b,c,d,e,f,g,h) for a,b,c,d,e,f,g,h in results if a], key=lambda x:(-x[2],x[1]))
    for _,ttfb,speed,segs,name,_,_,_ in ok:
        print(f"    ✅ [{speed}KB/s|{ttfb}ms] {name}")

    sites = []
    for _,ttfb,speed,segs,name,api,st,_ in ok:
        clean = re.sub(r'^\[.*?\]\s*','',name)
        stable = "稳" if speed>500 else "中" if speed>100 else "慢"
        sites.append({"key":clean,"name":f"[{speed}KB/s|{ttfb}ms|{stable}] {clean}","type":st,"api":api,"searchable":1,"quickSearch":1,"filterable":0})

    with open(OUT_SINGLE, "w", encoding="utf-8") as f:
        json.dump({"spider":"","sites":sites,"lives":all_lives,"parses":all_parses}, f, ensure_ascii=False, indent=2)
    print(f"  单仓: {len(sites)} 个采集站")

    with open(os.path.join(WORK_DIR,"sources.txt"), "w") as f:
        f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for name,url,lat,_ in configs: f.write(f"[{lat}ms] {name}\n{url}\n\n")

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 完成!")
    return 0

if __name__=="__main__": sys.exit(main())
