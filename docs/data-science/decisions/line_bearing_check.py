import json, math, subprocess, sys
sys.path.insert(0, "backend"); import config
URL = "https://gis.elpasotexas.gov/dev/rest/services/source_HIFLD_Open/MapServer/7/query"
def fetch(lat, lon, r_km):
    dlat = r_km/111.0; dlon = r_km/(111.0*math.cos(math.radians(lat)))
    out = subprocess.run(["curl","-s","-m","90","-G",URL,"--data-urlencode","where=VOLTAGE=345","--data-urlencode",
      f"geometry={lon-dlon},{lat-dlat},{lon+dlon},{lat+dlat}","--data-urlencode","geometryType=esriGeometryEnvelope",
      "--data-urlencode","inSR=4326","--data-urlencode","outSR=4326","--data-urlencode","outFields=ID,OWNER,SUB_1,SUB_2,STATUS",
      "--data-urlencode","f=geojson"],capture_output=True,text=True).stdout
    return json.loads(out)["features"]
def segs(f):
    g=f["geometry"]; parts=[g["coordinates"]] if g["type"]=="LineString" else g["coordinates"]
    for c in parts:
        for (x1,y1,*_),(x2,y2,*_) in zip(c, c[1:]): yield x1,y1,x2,y2
def bearing(lat, x1,y1,x2,y2):
    dx=(x2-x1)*math.cos(math.radians(lat)); dy=(y2-y1)
    return (math.degrees(math.atan2(dx,dy)))%180, math.hypot(dx,dy)*111.0
res={}
for city,(lat,lon) in config.CITY_COORDINATES.items():
    for r in (15,30,60):
        feats=fetch(lat,lon,r)
        sw=cw=tot=0; hist=[0]*8; names=set()
        for f in feats:
            names.add((f["properties"]["SUB_1"],f["properties"]["SUB_2"]))
            for s in segs(f):
                mx=(s[0]+s[2])/2; my=(s[1]+s[3])/2
                if math.hypot((mx-lon)*math.cos(math.radians(lat)),my-lat)*111.0>r: continue
                b,l=bearing(lat,*s); a=math.radians(2*b)
                sw+=l*math.sin(a); cw+=l*math.cos(a); tot+=l; hist[int(((b+11.25)%180)//22.5)]+=l
        mean=(math.degrees(math.atan2(sw,cw))/2)%180 if tot else None
        R=math.hypot(sw,cw)/tot if tot else 0
        print(f"{city} r={r}km lines={len(feats)} km={tot:.0f} dominant_axis={mean}deg R={R:.2f} hist(22.5deg bins from 0)={[round(h) for h in hist]}")
        if r==30: print("   ", sorted(names)[:12])
