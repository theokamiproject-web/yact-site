/**
 * 【テンプレート】舞台写真・グッズ 通販フォーム（既存の舞台写真フォームを拡張する Apps Script）
 * ★印の定数・品目・質問名は案件ごとに書き換える。銀行口座・連絡先はここに直書きせず、案件の実データを貼る。
 *
 * ■使い方（この順番で）
 *  1. 今の舞台写真フォームの Apps Script を開き、コードを全部消して、このコードを貼る → 保存
 *     （同じプロジェクトに貼るので、フォームのURL・回答シート・申込時の自動処理はそのまま使われます）
 *  2. 公演Tシャツのサイズ、ステッカーのデザイン名を確認する
 *     在庫数はあとからでOK（stock が null の品目は「在庫管理なし」で受け付けます）
 *  3. 関数 addGoodsToForm を選んで1回だけ実行 → 権限を承認
 *     ・フォームにグッズのページが入る ・回答シートに「在庫」シートができる
 *     ・12/15(火)23:59に受付を自動で終了する予約が入る
 *  4. 自分でテスト申込をして、確認メールの金額を確かめる（テスト分は在庫シートで数を戻す）
 *
 * ■在庫について
 *  ・在庫数が決まったら「在庫」シートのD列に数を入れて、refreshGoodsChoices を実行してください。
 *    D列が空欄の品目は在庫管理なし（売り切れ表示にならない）で受け付けます。
 *  ・数を入れた品目は、申込があるたびに数が減り、0になるとフォームで選べなくなります。
 *  ・入金がなくキャンセルになった分は、「在庫」シートの数を手で戻してから refreshGoodsChoices を実行。
 */

var CONTACT_MAIL = '★問い合わせ先メール';
var PRICE_SET = 1000;         // キャストセット 1種
var PRICE_BARA_PAIR = 500;    // バラ売り 2枚
var SHIP_NORMAL = 500;        // 送料：Tシャツを含まない注文
var SHIP_TEE = 800;           // 送料：Tシャツを含む注文
var PAY_DAYS = 7;             // 入金期限(申込から日数)
var MAX_PER_ITEM = 3;         // 1品目あたり1回の申込で選べる最大数
var CLOSE_AT = new Date('★2026-12-15T23:59:59+09:00');  // 受付終了日時
var CLOSE_STR = '★12月15日(火) 23:59';
var BANK_INFO = '★銀行名 支店名（店番）\n★種別 口座番号\n口座名義：★名義';
var FORM_TITLE = '★『作品名』 舞台写真・グッズ 通販申込フォーム';

// ★品目は実例。案件の品目・価格に差し替える。在庫数（null＝在庫管理なし。あとで「在庫」シートのD列に入れてもよい）
var GOODS = [
  { key: 't20_L',   title: '20周年記念Tシャツ（黒） Lサイズ（4,000円）',   price: 4000, tee: true, stock: null },
  { key: 't20_XL',  title: '20周年記念Tシャツ（黒） XLサイズ（4,000円）',  price: 4000, tee: true, stock: null },
  { key: 't20_XXL', title: '20周年記念Tシャツ（黒） XXLサイズ（4,000円）', price: 4000, tee: true, stock: null },
  // 公演Tシャツはサイズ名を実物に合わせて直す
  { key: 'tk_M',    title: '公演Tシャツ Mサイズ（3,000円）',  price: 3000, tee: true, stock: null },
  { key: 'tk_L',    title: '公演Tシャツ Lサイズ（3,000円）',  price: 3000, tee: true, stock: null },
  { key: 'tk_XL',   title: '公演Tシャツ XLサイズ（3,000円）', price: 3000, tee: true, stock: null },
  { key: 'pamph',   title: '20周年記念パンフレット（2,000円）', price: 2000, stock: null },
  { key: 'script',  title: '上演台本（2,000円）',               price: 2000, stock: null },
  { key: 'band',    title: '20周年記念リストバンド（2,500円）', price: 2500, stock: null },
  { key: 'key',     title: '20周年記念キーホルダー（1,000円）', price: 1000, stock: null },
  // DVDは予約販売（送料込み・12月上旬に別便で発送）。在庫上限なしなら 999 のまま
  { key: 'dvd',     title: '公演DVD（4,000円・送料込み／12月上旬発送）', price: 4000, dvd: true, stock: 999 }
];
// ステッカー：2種セット500円。全4種から2種を選ぶ（1回の申込で1セットまで）
var STICKER_TITLE = '20周年記念ステッカー 2種セット（500円）';
var STICKER_PRICE = 500;
var STICKERS = [  // ★デザイン名を入れる（在庫は null＝管理なし）
  { key: 'stk_1', name: 'デザイン1', stock: null },
  { key: 'stk_2', name: 'デザイン2', stock: null },
  { key: 'stk_3', name: 'デザイン3', stock: null },
  { key: 'stk_4', name: 'デザイン4', stock: null }
];

// 既存フォームの質問名（変更しない）
var Q = {
  day: '観劇された日',
  name: 'お名前(受取人)',
  resName: '観劇時のお名前(ご予約名)',
  resMail: 'ご予約時のメールアドレス',
  mail: '連絡先メールアドレス',
  set: 'キャストセット(1,000円/種)',
  bara: 'バラ売り 写真番号(2枚500円)',
  zip: '郵便番号',
  addr: 'ご住所',
  tel: '電話番号',
  agree: '確認事項'
};
var STOCK_SHEET = '在庫';

/** 1回だけ実行：フォームにグッズのページを足し、在庫シートと受付終了の予約を作る */
function addGoodsToForm() {
  var props = PropertiesService.getScriptProperties();
  if (props.getProperty('GOODS_ITEMS')) throw new Error('グッズのページは追加済みです。2回目は実行しないでください。');
  var form = FormApp.openById(props.getProperty('FORM_ID'));

  form.setTitle(FORM_TITLE);
  form.setDescription(descText_());
  applySetting_('確認メッセージ', function () {
    form.setConfirmationMessage(
      'お申込みありがとうございました。\n金額と振込先を記載したメールをお送りしました。' + PAY_DAYS + '日以内にお振込みください。\n' +
      'メールが届かない場合は、迷惑メールフォルダをご確認のうえ、' + CONTACT_MAIL + ' までご連絡ください。');
  });

  // グッズの質問を作る（いったん末尾にでき、あとで「お届け先」の前へ移す）
  var created = [];
  var page = form.addPageBreakItem().setTitle('グッズ')
    .setHelpText('ご希望の品目の数を選んでください（不要なものは0のまま）。完売した品目は選べません。\n' +
      '送料：Tシャツを含むご注文 ' + SHIP_TEE + '円／含まないご注文 ' + SHIP_NORMAL + '円。公演DVDは送料込みで、12月上旬に別便でお送りします。');
  created.push(page);
  var ids = {};
  GOODS.forEach(function (g) {
    var it = form.addListItem().setTitle(g.title).setRequired(false);
    created.push(it);
    ids[g.key] = it.getId();
  });
  var stk = form.addCheckboxItem().setTitle(STICKER_TITLE)
    .setHelpText('ご希望の場合のみ、2種を選んでください（1回のお申込みで1セットまで）。')
    .setRequired(false);
  created.push(stk);
  ids.sticker = stk.getId();

  var items = form.getItems();
  var target = -1;
  for (var i = 0; i < items.length; i++) {
    if (items[i].getType() === FormApp.ItemType.PAGE_BREAK && items[i].getTitle() === 'お届け先') { target = i; break; }
  }
  if (target < 0) throw new Error('「お届け先」のページが見つかりません');
  created.forEach(function (it, k) { form.moveItem(it.getIndex(), target + k); });
  props.setProperty('GOODS_ITEMS', JSON.stringify(ids));

  // 在庫シート
  var ss = SpreadsheetApp.openById(form.getDestinationId());
  var sh = ss.getSheetByName(STOCK_SHEET) || ss.insertSheet(STOCK_SHEET);
  sh.clear();
  var rows = [['キー', '品目', '単価', '在庫']];
  GOODS.forEach(function (g) { rows.push([g.key, g.title, g.price, g.stock === null ? '' : g.stock]); });
  STICKERS.forEach(function (s) { rows.push([s.key, 'ステッカー ' + s.name, '', s.stock === null ? '' : s.stock]); });
  sh.getRange(1, 1, rows.length, 4).setValues(rows);
  sh.setFrozenRows(1);

  // 12/15 23:59 に受付終了
  ScriptApp.newTrigger('closePhotoOrderForm').timeBased().at(CLOSE_AT).create();

  refreshGoodsChoices();
  Logger.log('完了。フォームの公開URLは今までと同じです: ' + form.getPublishedUrl());
}

/** 在庫シートの数に合わせて、フォームの選択肢を作り直す（在庫を手で直したあとに実行） */
function refreshGoodsChoices() {
  var props = PropertiesService.getScriptProperties();
  var ids = JSON.parse(props.getProperty('GOODS_ITEMS') || '{}');
  var form = FormApp.openById(props.getProperty('FORM_ID'));
  var stock = readStock_(form);

  GOODS.forEach(function (g) {
    var item = form.getItemById(ids[g.key]);
    if (!item) return;
    var li = item.asListItem();
    var n = Math.max(0, Math.min(MAX_PER_ITEM, stock[g.key] === undefined ? Infinity : stock[g.key]));
    if (n === 0) {
      li.setTitle('【完売】' + g.title).setChoiceValues(['0']);
    } else {
      var ch = [];
      for (var c = 0; c <= n; c++) ch.push(String(c));
      li.setTitle(g.title).setChoiceValues(ch);
    }
  });

  var sItem = form.getItemById(ids.sticker);
  if (sItem) {
    var cb = sItem.asCheckboxItem();
    var left = STICKERS.filter(function (s) { return stock[s.key] === undefined || stock[s.key] > 0; }).map(function (s) { return s.name; });
    if (left.length >= 2) {
      cb.setTitle(STICKER_TITLE).setChoiceValues(left)
        .setValidation(FormApp.createCheckboxValidation().requireSelectExactly(2).build());
    } else {
      cb.setTitle('【完売】' + STICKER_TITLE).setChoiceValues(['完売']).clearValidation();
    }
  }
}

/** 申込時：金額計算 → 在庫を減らす → 申込者へ自動返信 + 運営へ通知（既存のトリガーがこの関数を呼びます） */
function onPhotoOrder(e) {
  var r = {};
  e.response.getItemResponses().forEach(function (ir) {
    r[ir.getItem().getTitle().replace(/^【完売】/, '')] = ir.getResponse();
  });

  // 写真
  var sets = r[Q.set] || [];
  var baraNums = r[Q.bara] || [];
  var baraOdd = baraNums.length % 2 === 1;
  var baraPrice = Math.floor(baraNums.length / 2) * PRICE_BARA_PAIR;
  var photoTotal = sets.length * PRICE_SET + baraPrice;

  // グッズ
  var lines = [], goodsTotal = 0, hasTee = false, hasDvd = false, hasOther = false, use = {};
  GOODS.forEach(function (g) {
    var q = parseInt(r[g.title], 10) || 0;
    if (q <= 0) return;
    use[g.key] = q;
    goodsTotal += q * g.price;
    if (g.tee) hasTee = true;
    if (g.dvd) hasDvd = true; else hasOther = true;
    lines.push(g.title.replace(/（[^（]*円[^）]*）$/, '') + ' × ' + q + ' = ' + (q * g.price) + '円');
  });
  var stickers = (r[STICKER_TITLE] || []).filter(function (n) { return n !== '完売'; });
  if (stickers.length) {
    goodsTotal += STICKER_PRICE;
    hasOther = true;
    lines.push('ステッカー 2種セット（' + stickers.join('、') + '）= ' + STICKER_PRICE + '円');
    STICKERS.forEach(function (s) { if (stickers.indexOf(s.name) >= 0) use[s.key] = 1; });
  }

  // 送料：Tシャツあり800円／それ以外の品物（写真含む）があれば500円／DVDだけなら0円
  if (photoTotal > 0) hasOther = true;
  var ship = hasTee ? SHIP_TEE : (hasOther ? SHIP_NORMAL : 0);
  var total = photoTotal + goodsTotal + ship;

  // 在庫を減らす
  var short = decreaseStock_(use);
  try { refreshGoodsChoices(); } catch (err) { Logger.log('選択肢の更新に失敗: ' + err); }

  var deadline = new Date(new Date().getTime() + PAY_DAYS * 86400000);
  var deadlineStr = Utilities.formatDate(deadline, 'Asia/Tokyo', 'M月d日(E)');

  var body = [
    r[Q.name] + ' 様',
    '',
    '★『作品名』 舞台写真・グッズのお申込みありがとうございます。内容は下記のとおりです。',
    ''
  ];
  if (baraOdd) body.push('※バラ売りの枚数が奇数のため、運営より確認のご連絡をします。');
  if (short.length) body.push('※在庫が不足している品目があるため、運営より確認のご連絡をします。');
  body.push('■ご注文');
  if (sets.length) body.push('キャストセット: ' + sets.join('、') + '(' + sets.length + '種 × ' + PRICE_SET + '円 = ' + (sets.length * PRICE_SET) + '円)');
  if (baraNums.length) body.push('バラ売り: ' + baraNums.join(', ') + '(' + baraNums.length + '枚 = ' + baraPrice + '円)');
  body = body.concat(lines);
  if (!sets.length && !baraNums.length && !lines.length) body.push('（選択された品目がありません。運営より確認のご連絡をします）');
  body.push('送料: ' + ship + '円' + (hasTee ? '（Tシャツを含むため）' : (ship === 0 ? '（公演DVDのみ・送料込み）' : '')));
  body.push('', '■お支払い金額: ' + total + '円', '', '■お振込先', BANK_INFO,
    'お支払い期限: ' + deadlineStr + '(振込手数料はご負担ください)', '');
  body.push('■発送: ご入金確認後1週間以内' + (hasDvd ? '\n※公演DVDは12月上旬に別便でお送りします（追加の送料はかかりません）' : ''));
  body.push('', 'ノアノオモチャバコ');

  MailApp.sendEmail({
    to: r[Q.mail],
    replyTo: CONTACT_MAIL,
    name: 'ノアノオモチャバコ',
    subject: '【ノアノオモチャバコ】舞台写真・グッズのお申込み確認とお振込みのご案内',
    body: body.join('\n')
  });

  var flags = (baraOdd ? ' (バラ奇数・要確認)' : '') + (short.length ? ' (在庫不足: ' + short.join('、') + ')' : '') + (hasDvd ? ' (DVDあり)' : '');
  MailApp.sendEmail({
    to: CONTACT_MAIL,
    subject: '[写真・グッズ通販] 新規申込 ' + r[Q.name] + ' / ' + total + '円' + flags,
    body: body.join('\n') + '\n\n--- 運営メモ ---\n観劇日: ' + (r[Q.day] || '-') +
      '\n予約名: ' + (r[Q.resName] || '-') + '\n予約メール: ' + (r[Q.resMail] || '-') +
      '\n住所: ' + r[Q.zip] + ' ' + r[Q.addr] + '\n電話: ' + r[Q.tel]
  });
}

/** 12/15 23:59 に自動実行（手動でも可） */
function closePhotoOrderForm() {
  var id = PropertiesService.getScriptProperties().getProperty('FORM_ID');
  if (!id) return;
  var form = FormApp.openById(id);
  form.setAcceptingResponses(false);
  form.setCustomClosedFormMessage('舞台写真・グッズの通販申込は終了しました。たくさんのお申込みありがとうございました。');
}

function descText_() {
  return '舞台写真とグッズの通販申込フォームです。受付は' + CLOSE_STR + 'までです。\n\n' +
    '【舞台写真】\n・キャストセット 1,000円/種（ソロ写真＋シーン写真。各キャスト1種、全13種）\n' +
    '・バラ売り 2枚500円（B01〜B09から2枚単位でお選びください）\n\n' +
    '【グッズ】\n・20周年記念Tシャツ 4,000円／公演Tシャツ 3,000円／20周年記念パンフレット 2,000円／上演台本 2,000円\n' +
    '・20周年記念リストバンド 2,500円／20周年記念キーホルダー 1,000円／ステッカー2種セット 500円\n' +
    '・公演DVD 4,000円（送料込み・12月上旬発送）\n・在庫がなくなり次第終了です。\n\n' +
    '【送料】\n・Tシャツを含むご注文 ' + SHIP_TEE + '円／含まないご注文 ' + SHIP_NORMAL + '円\n' +
    '・公演DVDのみのご注文は送料無料（送料込みの価格です）\n\n' +
    '【お支払い・発送】\n・銀行振込のみ。申込後に届くメールの口座へ、申込から' + PAY_DAYS + '日以内にお振込みください。振込手数料はご負担ください。\n' +
    '・ご入金確認後1週間以内に発送します（公演DVDは12月上旬に別便）。\n' +
    '・確認メールは自動送信です。届かない場合は迷惑メールフォルダをご確認ください。';
}

function readStock_(form) {
  var ss = SpreadsheetApp.openById(form.getDestinationId());
  var sh = ss.getSheetByName(STOCK_SHEET);
  var v = sh.getDataRange().getValues();
  var m = {};
  for (var i = 1; i < v.length; i++) m[v[i][0]] = (v[i][3] === '' || v[i][3] === null) ? Infinity : (Number(v[i][3]) || 0);
  return m;
}

/** 在庫を減らす。足りなかった品目名を返す */
function decreaseStock_(use) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var form = FormApp.openById(PropertiesService.getScriptProperties().getProperty('FORM_ID'));
    var sh = SpreadsheetApp.openById(form.getDestinationId()).getSheetByName(STOCK_SHEET);
    var v = sh.getDataRange().getValues();
    var short = [];
    for (var i = 1; i < v.length; i++) {
      var q = use[v[i][0]];
      if (!q || v[i][3] === '' || v[i][3] === null) continue;  // 空欄＝在庫管理なし
      var left = (Number(v[i][3]) || 0) - q;
      if (left < 0) short.push(v[i][1]);
      sh.getRange(i + 1, 4).setValue(left);
    }
    return short;
  } finally {
    lock.releaseLock();
  }
}

function applySetting_(name, fn) {
  try { fn(); } catch (err) { Logger.log('設定をスキップ: ' + name + ' / ' + err); }
}
