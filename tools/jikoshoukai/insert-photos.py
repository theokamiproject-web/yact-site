#!/usr/bin/env python3
"""夢授業 自己紹介スライドの写真枠に、写真を流し込む。

使い方:
    photos/ に写真を置き、下の MAPPING を書き換えて
    python3 insert-photos.py 夢授業_自己紹介_v4.pptx 夢授業_自己紹介_v5.pptx

やっていること:
  - 写真を枠と同じ 1600x837（4.3in x 2.25in）に整えてから埋める。
    枠と比率が同じなので、写真がつぶれたり左右の揃いが崩れたりしない。
  - 横長の写真は cover（はみ出す分を切る／focus で切る位置を上下に寄せる）。
    縦長・極端に横長の写真は contain（全体を残し、余白は枠と同じ色で埋める）。
  - 写真を入れた枠は、破線の枠線を実線にし、「写真：〇〇」の文字を消す。
写真を入れなかった枠は、破線と文言がそのまま残る。
"""
import io, re, sys, zipfile
from PIL import Image, ImageOps

W, H = 1600, 837                    # 写真枠 3931920 x 2057400 EMU と同じ比率
WARM, COOL = (0xEC, 0xE2, 0xD0), (0xE4, 0xED, 0xF0)   # 左＝真坂 / 右＝寺戸の枠色

# スライド番号 -> 'L'（左・真坂）/ 'R'（右・寺戸）
#   -> (写真, cover|contain, 上下の寄せ, 回転角, 先に切り取る範囲 or None)
MAPPING = {
    2: {'L': ('photos/butai.jpg',      'cover',   0.52,   0, None),
        'R': ('photos/keikoba.jpg',    'cover',   0.42,   0, (0.02, 0.02, 0.78, 0.80))},
    # 真坂Q2は父と赤ちゃんの両方の顔を入れる。枠が横長なので、元画像の横幅いっぱいを
    # 使わないと縦が足りない（＝プリントのふちと壁が左右に写る）
    3: {'L': ('photos/akachan_m.jpg',  'cover',   0.33,   0, None),
        'R': ('photos/akachan_t.jpg',  'cover',   0.445, -90, None)},
    4: {'L': ('photos/kouen.jpg',      'cover',   0.57,   0, None),
        'R': ('photos/gekidan.jpg',    'cover',   0.40,   0, None)},
    5: {'L': ('photos/washitsu.jpg',   'cover',   0.65,   0, None),
        'R': ('photos/gekijou.jpg',    'contain', 0.50,   0, None)},
}

FRAME = {'L': ('457200', '1463040'), 'R': ('4754880', '1463040')}
CAP   = {'L': ('640080', '2212848'), 'R': ('4937760', '2212848')}
BLIP  = ('<a:blipFill rotWithShape="1"><a:blip r:embed="%s"/>'
         '<a:srcRect/><a:stretch><a:fillRect/></a:stretch></a:blipFill>')


def render(path, mode, focus, rot, box, bg):
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    if rot:
        im = im.rotate(rot, expand=True)
    if box:                                           # 割合指定で先に切り取る
        l, t, r, b = box
        im = im.crop((int(l * im.width), int(t * im.height),
                      int(r * im.width), int(b * im.height)))
    if mode == 'contain':
        out = Image.new('RGB', (W, H), bg)
        k = min(W / im.width, H / im.height)   # thumbnail は縮小しかしないので倍率を自前で出す
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        out.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
        return out
    if im.width / im.height > W / H:                  # 横に長い → 左右を切る
        nw = int(im.height * W / H)
        im = im.crop(((im.width - nw) // 2, 0, (im.width - nw) // 2 + nw, im.height))
    else:                                             # 縦に長い → 上下を切る
        nh = int(im.width * H / W)
        y0 = max(0, min(im.height - nh, int(im.height * focus) - nh // 2))
        im = im.crop((0, y0, im.width, y0 + nh))
    return im.resize((W, H), Image.LANCZOS)


def sp_at(xml, x, y):
    """指定座標に置かれた <p:sp> の範囲を返す。"""
    i = xml.index('<a:off x="%s" y="%s"/>' % (x, y))
    return xml.rindex('<p:sp>', 0, i), xml.index('</p:sp>', i) + len('</p:sp>')


def main(src, out):
    zin = zipfile.ZipFile(src)
    names = zin.namelist()
    parts = {n: zin.read(n) for n in names}
    zin.close()

    media = []
    for n, sides in MAPPING.items():
        key, rels_key = 'ppt/slides/slide%d.xml' % n, 'ppt/slides/_rels/slide%d.xml.rels' % n
        xml, rels = parts[key].decode('utf-8'), parts[rels_key].decode('utf-8')

        for side, (path, mode, focus, rot, box) in sorted(sides.items()):
            rid, target = 'rIdPhoto%s' % side, 'photo%d%s.jpg' % (n, side)
            buf = io.BytesIO()
            render(path, mode, focus, rot, box, WARM if side == 'L' else COOL).save(
                buf, 'JPEG', quality=88, optimize=True)
            media.append((target, buf.getvalue()))

            s, e = sp_at(xml, *FRAME[side])
            sp = xml[s:e]
            fill = re.search(r'<a:solidFill><a:srgbClr val="(?:ECE2D0|E4EDF0)"/></a:solidFill>', sp)
            sp = sp.replace(fill.group(0), BLIP % rid, 1).replace('<a:prstDash val="dash"/>', '', 1)
            xml = xml[:s] + sp + xml[e:]

            cs, ce = sp_at(xml, *CAP[side])         # 「写真：〇〇」の文字を消す
            assert '写真：' in xml[cs:ce]
            xml = xml[:cs] + xml[ce:]

            rels = rels.replace('</Relationships>',
                '<Relationship Id="%s" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/image" Target="../media/%s"/>'
                '</Relationships>' % (rid, target))

        parts[key], parts[rels_key] = xml.encode('utf-8'), rels.encode('utf-8')

    ct = parts['[Content_Types].xml'].decode('utf-8')
    if 'Extension="jpg"' not in ct:
        ct = ct.replace('<Default ContentType="application/xml" Extension="xml"/>',
                        '<Default ContentType="application/xml" Extension="xml"/>'
                        '<Default ContentType="image/jpeg" Extension="jpg"/>', 1)
    parts['[Content_Types].xml'] = ct.encode('utf-8')

    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, parts[n])
        for target, blob in media:
            z.writestr('ppt/media/' + target, blob)
    print('%s に %d 枚入れました' % (out, len(media)))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
