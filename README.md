# TJ_Vector - ComfyUI Custom Node

ラインアート画像から中心線を抽出し、SVGパスとして出力するComfyUIカスタムノード

## ノード

### 1. Line Region Detector
ラインアート画像から線領域を検出

**入力:**
- `image`: 入力画像
- `background_mode`: 背景検出モード (auto/white/black)
- `line_detection_method`: 線検出方法 (edge/morphology/hybrid)
- その他のパラメータ

**出力:**
- `line_mask`: 線領域のマスク
- `fill_mask`: 塗り領域のマスク
- `preview_image`: プレビュー画像
- `color_info`: 色情報 (JSON)

### 2. Centerline to SVG
線マスクから中心線を抽出してSVGパスを生成

**入力:**
- `line_mask`: 線領域のマスク
- `algorithm`: 中心線抽出アルゴリズム (ridge/skeleton/medial_axis)
- `smoothing`: パス平滑化レベル
- その他のパラメータ

**出力:**
- `svg_string`: SVG形式の文字列
- `centerline_image`: 中心線プレビュー
- `statistics`: 統計情報 (JSON)

## インストール

1. このフォルダを `ComfyUI/custom_nodes/` にコピー
2. 依存関係をインストール:
```bash
pip install -r requirements.txt
```

## 使い方

1. ComfyUIを起動
2. ノードメニューから `TJ_Vector` カテゴリを選択
3. `Line Region Detector` ノードで線を検出
4. `Centerline to SVG` ノードでSVGを生成

## ライセンス

MIT License

## バージョン

v1.0 - 初期リリース
