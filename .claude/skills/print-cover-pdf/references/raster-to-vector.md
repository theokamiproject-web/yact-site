# ラスター混在ロゴ・素材をK単色ベクターにする
1. `pdftocairo -svg` でSVG化 → `<image>` と、それを参照する `<mask>`/`<g mask="url(#...)">` を確認。
2. 画像部分（例: 結び目の線画）は、該当領域を `pdftoppm -r 1200 -x -y -W -H -gray` で切り出し→2値化→ **potracer**（`pip install potracer`）で輪郭化。**落とし穴**: `potrace.Bitmap(mask)` は黒白が反転することがある → 結果が反転していたら `Bitmap(~mask)`。画像はRGB読み込みになりがち → `.convert('L')`。
3. 元の `<g mask=...>`（空マスクの黒い四角が残る）は削除。残すとPDFに小さな画像が残り `check_pdf` の画像>0になる。
4. `fill="rgb(a%,b%,c%)"` は輝度でグレー化。暗い値(<90)は #000 に丸める（色味付き黒の除去）。
5. 余白に切り出しの余裕を取る（下端のセリフが切れる事故が起きた）。
