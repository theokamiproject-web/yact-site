"""xlsxのセルに値を直接書き込む（XMLを直接編集して、画像・入力規則・テーブルを壊さない）
要: lxml（無ければ python3 -m pip install lxml）。改行は \n で書く。数値は数値のまま入る。
開いたときに数式を再計算させる（fullCalcOnLoad）。
usage: python3 inject.py in.xlsx out.xlsx spec.json
spec: {"シート名": {"A1": "文字" or 123, ...}, ...}
"""
import sys, json, zipfile, re, shutil
from lxml import etree
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PNS='http://schemas.openxmlformats.org/package/2006/relationships'
src,dst,specp=sys.argv[1:4]
spec=json.load(open(specp,encoding='utf-8'))
z=zipfile.ZipFile(src)
files={n:z.read(n) for n in z.namelist()}
infos={i.filename:i for i in z.infolist()}
wb=etree.fromstring(files['xl/workbook.xml'])
rels=etree.fromstring(files['xl/_rels/workbook.xml.rels'])
rmap={r.get('Id'):r.get('Target') for r in rels}
sheetfile={}
for s in wb.iter('{%s}sheet'%NS):
    t=rmap[s.get('{%s}id'%RNS)]
    sheetfile[s.get('name')]='xl/'+t.lstrip('/').replace('xl/','',1) if not t.startswith('/') else t.lstrip('/')
def colnum(c):
    n=0
    for ch in c: n=n*26+ord(ch)-64
    return n
def split(ref):
    m=re.match(r'([A-Z]+)(\d+)$',ref); return m.group(1),int(m.group(2))
for sname,cells in spec.items():
    if sname not in sheetfile:
        sys.exit('シートがありません: %s\n候補: %s' % (sname, ', '.join(sheetfile)))
    p=sheetfile[sname]
    root=etree.fromstring(files[p])
    sd=root.find('{%s}sheetData'%NS)
    rows={int(r.get('r')):r for r in sd.findall('{%s}row'%NS)}
    for ref,val in cells.items():
        col,rn=split(ref)
        row=rows.get(rn)
        if row is None:
            row=etree.Element('{%s}row'%NS); row.set('r',str(rn))
            after=[k for k in rows if k<rn]
            if after: rows[max(after)].addnext(row)
            else: sd.insert(0,row)
            rows[rn]=row
        c=None
        for cc in row.findall('{%s}c'%NS):
            if cc.get('r')==ref: c=cc;break
        if c is None:
            c=etree.Element('{%s}c'%NS); c.set('r',ref)
            prev=[cc for cc in row.findall('{%s}c'%NS) if colnum(split(cc.get('r'))[0])<colnum(col)]
            if prev: prev[-1].addnext(c)
            else: row.insert(0,c)
        for ch in list(c): c.remove(ch)
        if val is None:
            c.attrib.pop('t',None); continue
        if isinstance(val,(int,float)):
            c.attrib.pop('t',None)
            v=etree.SubElement(c,'{%s}v'%NS); v.text=str(val)
        else:
            c.set('t','inlineStr')
            is_=etree.SubElement(c,'{%s}is'%NS); t=etree.SubElement(is_,'{%s}t'%NS)
            t.text=val; t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    files[p]=etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
# 開いたときに数式を計算し直す
cp=wb.find('{%s}calcPr'%NS)
if cp is not None: cp.set('fullCalcOnLoad','1')
files['xl/workbook.xml']=etree.tostring(wb,xml_declaration=True,encoding='UTF-8',standalone=True)
with zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED) as o:
    for n in z.namelist():
        o.writestr(infos[n],files[n])
print('ok',dst)
