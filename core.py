"""Geometry and export, no network access required."""
import csv, io, zipfile
from decimal import Decimal, InvalidOperation
import shapefile
from shapely.geometry import Polygon, shape, mapping
from shapely.ops import transform
from pyproj import CRS, Transformer

CRS_LV = CRS.from_epsg(3059)
TO_WGS = Transformer.from_crs(3059, 4326, always_xy=True)
# These bounds are a coarse sanity check only, never proof of being inside Latvia.
LV_BBOX = (20.8, 55.6, 28.3, 58.2)

def number(v):
    s = str(v).strip().replace(' ', '').replace('\u00a0','').replace(',', '.')
    try:
        d = Decimal(s)
        if not d.is_finite(): raise ValueError('Nederīgs skaitlis')
        return d
    except (InvalidOperation, ValueError):
        raise ValueError(f'Nederīga koordināta: {v!r}')

def geometry(rows, swap=False):
    coords = []
    for row in rows:
        x, y = number(row['X']), number(row['Y'])
        if swap: x,y=y,x
        coords.append((float(x),float(y)))
    if len(set(coords)) < 3: raise ValueError('Vajadzīgas vismaz 3 atšķirīgas virsotnes')
    if coords[0] == coords[-1]: coords.pop()
    poly = Polygon(coords)
    if not poly.is_valid: raise ValueError('Poligons nav derīgs (iespējama paškrustošanās)')
    if poly.area <= 0: raise ValueError('Poligona platība ir nulle')
    wgs = transform(TO_WGS.transform, poly)
    if not wgs.is_valid: raise ValueError('Koordinātu pārveidošana neizdevās')
    minx,miny,maxx,maxy=wgs.bounds
    plausible = LV_BBOX[0]<=minx and maxx<=LV_BBOX[2] and LV_BBOX[1]<=miny and maxy<=LV_BBOX[3]
    return poly, wgs, plausible

def country_status(wgs, boundary):
    if boundary is None: return 'Nav pārbaudīts: Latvijas robežas dati nav pieejami'
    if boundary.covers(wgs): return 'Pilnībā Latvijas teritorijā'
    if boundary.intersects(wgs): return 'Daļēji Latvijas teritorijā / šķērso robežu'
    return 'Ārpus Latvijas'

def export_zip(rows, poly, filename='Poligons_LKS92'):
    filename=''.join(c for c in filename if c.isalnum() or c in '-_') or 'Poligons_LKS92'
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        mem=io.BytesIO()
        w=shapefile.Writer(shp=io.BytesIO(),shx=io.BytesIO(),dbf=io.BytesIO(),shapeType=shapefile.POLYGON)
        w.field('ID','N',size=8)
        w.field('Plat_ha','F',size=18,decimal=6)
        w.poly([list(poly.exterior.coords)])
        w.record(1,round(poly.area/10000,6))
        w.close()
        for ext,stream in [('shp',w.shp),('shx',w.shx),('dbf',w.dbf)]:
            z.writestr(f'{filename}.{ext}',stream.getvalue())
        z.writestr(f'{filename}.prj',CRS_LV.to_wkt(version='WKT1_ESRI'))
        z.writestr(f'{filename}.cpg','UTF-8')
        csvbuf=io.StringIO(newline='')
        cw=csv.writer(csvbuf,delimiter=';')
        cw.writerow(['Virsotne','X','Y'])
        for i,r in enumerate(rows,1): cw.writerow([i,str(r['X']),str(r['Y'])])
        z.writestr(f'{filename}_virsotnes.csv', '\ufeff'+csvbuf.getvalue())
    return buf.getvalue()
