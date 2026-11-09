"""Local Tesseract OCR: provisional candidates only; user must review."""
import re, io
import cv2, numpy as np
from PIL import Image
import pytesseract
import fitz

NUM=r'[-+]?\d{4,7}[.,]\d{1,5}'
LINE=re.compile(rf'^\s*(\d{{1,3}})[\s|;:]+({NUM})[\s|;:]+({NUM})\s*$')
PAIR=re.compile(rf'({NUM})\s+({NUM})')

def pages(file_bytes, suffix):
    if suffix.lower()=='.pdf':
        doc=fitz.open(stream=file_bytes,filetype='pdf')
        if len(doc)>12: raise ValueError('Vienā PDF atļautas līdz 12 lapām')
        for page in doc:
            pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            yield Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    else:
        yield Image.open(io.BytesIO(file_bytes)).convert('RGB')

def read_image(im):
    a=np.asarray(im.convert('RGB'))
    gray=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY)
    gray=cv2.resize(gray,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
    variants=[gray,cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]]
    texts=[pytesseract.image_to_string(v,config='--psm 6') for v in variants]
    best=[]
    for t in texts:
        rows=[]
        for line in t.splitlines():
            line=line.replace('−','-').replace('—','-')
            m=LINE.match(line)
            if m:
                rows.append({'Nr':int(m[1]),'X':m[2],'Y':m[3]})
        if len(rows)>len(best):best=rows
    return best, '\n\n--- OCR alternatīva ---\n\n'.join(texts)
