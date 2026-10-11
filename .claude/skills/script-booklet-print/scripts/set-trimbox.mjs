import {PDFDocument} from 'pdf-lib';
import fs from 'fs';
const d=await PDFDocument.load(fs.readFileSync(process.argv[2]));
const m=3*72/25.4;
for(const p of d.getPages()){const {width:w,height:h}=p.getSize();p.setTrimBox(m,m,w-2*m,h-2*m);p.setBleedBox(0,0,w,h);}
fs.writeFileSync(process.argv[3],await d.save());
