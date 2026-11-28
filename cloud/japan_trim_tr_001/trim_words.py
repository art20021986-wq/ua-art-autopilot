"""JAPAN-TRIM-TR-001: the trim of a Japan lot in Latin letters, as the Korea lots show theirs («Base», «Gran Sport Coupe»).

A small dictionary of the usual trim words (katakana and kanji), longest match first; Latin letters and digits stay.
A trim that still has a Japanese word the dictionary does not know, or says «grade unknown», gives '' and the card does
not show the row (no foreign script for the client). No network, no outside translation service.
"""
import re
import unicodedata

UNKNOWN = ('グレード不明', '不明')
WORDS = {
    'ベースグレード': 'Base', 'ベース': 'Base', 'グレード': 'Grade', 'スタンダード': 'Standard', 'ハイグレード': 'High Grade',
    'グランスポーツ': 'Gran Sport', 'グランツーリスモ': 'Gran Turismo', 'グランド': 'Grand', 'グラン': 'Gran',
    'スポーツ': 'Sport', 'クーペ': 'Coupe', 'カブリオレ': 'Cabriolet', 'コンバーチブル': 'Convertible',
    'ロードスター': 'Roadster', 'スパイダー': 'Spider', 'タルガ': 'Targa', 'セダン': 'Sedan', 'ワゴン': 'Wagon',
    'ツーリング': 'Touring', 'ハッチバック': 'Hatchback', 'リミテッド': 'Limited', 'エディション': 'Edition',
    'プレミアム': 'Premium', 'ラグジュアリー': 'Luxury', 'エクスクルーシブ': 'Exclusive', 'パッケージ': 'Package',
    'ハイブリッド': 'Hybrid', 'ターボ': 'Turbo', 'ディーゼル': 'Diesel', 'ロングホイールベース': 'Long Wheelbase',
    'ロング': 'Long', 'ショート': 'Short', 'ホイールベース': 'Wheelbase', 'カスタム': 'Custom', 'スペシャル': 'Special',
    'シグネチャー': 'Signature', 'アーバン': 'Urban', 'クロス': 'Cross', 'アドベンチャー': 'Adventure',
    'ローンチ': 'Launch', 'ファースト': 'First', 'モデル': 'Model', 'レザー': 'Leather', 'サンルーフ': 'Sunroof',
    'ブラック': 'Black', 'ホワイト': 'White', 'ナイト': 'Night', 'ライン': 'Line', 'コンペティション': 'Competition',
    'パフォーマンス': 'Performance', 'エレガンス': 'Elegance', 'アバンギャルド': 'Avantgarde', 'デザイン': 'Design',
    'クラシック': 'Classic', 'ヘリテージ': 'Heritage', 'アニバーサリー': 'Anniversary', 'ベーシック': 'Basic',
    'コンフォート': 'Comfort', 'ダイナミック': 'Dynamic', 'インディビジュアル': 'Individual', 'プラス': 'Plus',
    'エクストラ': 'Extra', 'ルビコン': 'Rubicon', 'サハラ': 'Sahara', 'アンリミテッド': 'Unlimited',
    'オーバーランド': 'Overland', 'トレイルホーク': 'Trailhawk', 'ラレード': 'Laredo', 'サミット': 'Summit',
    'ディーラー': 'Dealer', 'ドア': 'Door',
    '特別仕様車': 'Special Edition', '限定車': 'Limited', '限定': 'Limited', '仕様': 'Spec', '左ハンドル': 'LHD',
    '右ハンドル': 'RHD', '四駆': '4WD', '二駆': '2WD', '後期': 'Late', '前期': 'Early', '型': 'Type',
}
JAPANESE = re.compile(r'[぀-ヿㇰ-ㇿ㐀-鿿]')
KEYS = sorted(WORDS, key=len, reverse=True)
SEPARATORS = {'・': ' ', '／': '/', '　': ' '}


def latin(trim):
    """The trim in Latin letters, or '' when it says nothing the client can read."""
    text = unicodedata.normalize('NFKC', trim or '').strip()
    if not text or text in UNKNOWN:
        return ''
    for mark, plain in SEPARATORS.items():
        text = text.replace(mark, plain)
    out, i = [], 0
    while i < len(text):
        word = next((k for k in KEYS if text.startswith(k, i)), None)
        if word:
            out.append(' ' + WORDS[word] + ' ')
            i += len(word)
        else:
            out.append(text[i])
            i += 1
    result = re.sub(r'\s+', ' ', ''.join(out)).strip()
    return '' if JAPANESE.search(result) else result
