import sharp from 'sharp'; import fs from 'node:fs';
const base='/tmp/claude-0/-home-user-yact-site/2e8ba03d-770d-59f6-9606-81887793c278/scratchpad/rc1';
const mx=JSON.parse(fs.readFileSync(base+'/metrics.json')).pages;
const rows=[];
for(const m of mx){
  const {data,info}=await sharp(`${base}/pages/page-${String(m.n).padStart(2,'0')}.png`).removeAlpha().raw().toBuffer({resolveWithObject:true});
  const W=info.width,H=info.height; const px=(x,y)=>{const i=(y*W+x)*3;return [data[i],data[i+1],data[i+2]]};
  const bg=px(Math.floor(W*0.5),Math.floor(H*0.5)); // not reliable; use paper
  const paper=[251,250,246]; let last=0, first=H;
  const limit=Math.floor(H*0.90), top=Math.floor(H*0.08);
  for(let y=top;y<limit;y++){let ink=0;for(let x=Math.floor(W*0.08);x<W*0.92;x+=2){const p=px(x,y);if(Math.abs(p[0]-paper[0])+Math.abs(p[1]-paper[1])+Math.abs(p[2]-paper[2])>60)ink++;} if(ink>2){last=y;if(y<first)first=y;}}
  rows.push({n:m.n,layout:m.layout+'/'+m.variant,fit_fill:m.fit_fill,ws:m.whitespace_ratio,bottom_pct:Math.round(last/H*100),full:last>=limit-2});
}
console.table(rows);
fs.writeFileSync('/home/user/yact-site/publishing-studio/reviews/evidence/C-content-bottom.json',JSON.stringify(rows,null,1));
