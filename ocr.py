"""Table-aware local OCR. All OCR output remains provisional and user-reviewed."""
import io, re
import cv2
import numpy as np
from PIL import Image
import pytesseract
import fitz

NUM = r'\d{5,7}[.,]\d{1,5}'
ROW = re.compile(rf'(?<!\d)(\d{{1,3}})\s+({NUM})\s+({NUM})(?!\d)')


def pages(file_bytes, suffix):
    if suffix.lower() == '.pdf':
        doc = fitz.open(stream=file_bytes, filetype='pdf')
        if len(doc) > 12:
            raise ValueError('Vienā PDF atļautas līdz 12 lapām')
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(3,3), alpha=False)
            yield Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    else:
        yield Image.open(io.BytesIO(file_bytes)).convert('RGB')


def _ocr(img, psm=7, whitelist=False):
    config=f'--oem 3 --psm {psm}'
    if whitelist:
        config += ' -c tessedit_char_whitelist=0123456789.,'
    return pytesseract.image_to_string(img, config=config).strip()


def _positions(mask, axis, min_length):
    projection = np.count_nonzero(mask, axis=axis)
    active = np.flatnonzero(projection >= min_length)
    groups=[]
    for k in active:
        if not groups or k > groups[-1][-1]+1: groups.append([int(k)])
        else: groups[-1].append(int(k))
    return [int(np.median(g)) for g in groups]


def _extract_grid(gray):
    h,w=gray.shape
    binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    horiz=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(max(25,w//9),1)))
    vert=cv2.morphologyEx(binary,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(18,h//18))))
    contours,_=cv2.findContours(cv2.bitwise_or(horiz,vert),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for c in contours:
        x,y,cw,ch=cv2.boundingRect(c)
        if cw < w*.25 or ch < h*.08: continue
        roi_h=horiz[y:y+ch,x:x+cw]; roi_v=vert[y:y+ch,x:x+cw]
        ys=_positions(roi_h,axis=1,min_length=int(cw*.55))
        xs=_positions(roi_v,axis=0,min_length=int(ch*.45))
        if len(ys)>=4 and len(xs)>=4:
            candidates.append((cw*ch, x,y,xs,ys))
    if not candidates: return []
    _,x,y,xs,ys=max(candidates)
    # Usually 3 columns: Nr | X | Y. Some double rules yield extra positions.
    if len(xs)!=4: return []
    rows=[]
    for j in range(len(ys)-1):
        top,bottom=y+ys[j],y+ys[j+1]
        if bottom-top<13: continue
        cells=[]
        for i in range(3):
            left,right=x+xs[i],x+xs[i+1]
            margin_x=max(2,min(5,(right-left)//20))
            margin_y=max(2,min(4,(bottom-top)//8))
            crop=gray[top+margin_y:bottom-margin_y,left+margin_x:right-margin_x]
            if crop.size==0: cells.append('');continue
            crop=cv2.resize(crop,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
            crop=cv2.copyMakeBorder(crop,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
            cells.append(_ocr(crop,7,True).replace(' ','').replace(',','.'))
        if re.fullmatch(r'\d{1,3}',cells[0]) and re.fullmatch(NUM,cells[1]) and re.fullmatch(NUM,cells[2]):
            rows.append({'Nr':int(cells[0]),'X':cells[1],'Y':cells[2]})
    return rows


def _extract_text(gray):
    enlarged=cv2.resize(gray,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
    variants=[enlarged,cv2.threshold(enlarged,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]]
    results=[]; debug=[]
    for variant in variants:
        for psm in (6,11):
            raw=_ocr(variant,psm)
            debug.append(raw)
            rows=[]
            for line in raw.splitlines():
                line=line.replace('|',' ').replace(';',' ').replace('−','-')
                for m in ROW.finditer(line):
                    rows.append({'Nr':int(m[1]),'X':m[2].replace(',','.'),'Y':m[3].replace(',','.')})
            results.append(rows)
    return max(results,key=len,default=[]), '\n\n--- OCR variants ---\n\n'.join(debug)


def read_image(im):
    a=np.asarray(im.convert('RGB'))
    gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
    grid=_extract_grid(gray)
    text_rows,debug=_extract_text(gray)
    # Prefer more rows, but never invent a missing vertex.
    chosen=max((grid,text_rows),key=len)
    unique=[]; seen=set()
    for row in chosen:
        if row['Nr'] not in seen:
            unique.append(row);seen.add(row['Nr'])
    unique.sort(key=lambda r:r['Nr'])
    if unique:
        expected=list(range(1,max(r['Nr'] for r in unique)+1))
        missing=sorted(set(expected)-seen)
        if missing: debug+='\n\nBRĪDINĀJUMS: trūkst virsotņu: '+', '.join(map(str,missing))
    return unique,debug
