# TJ_Vector - ComfyUI Custom Node

ラインアート画像から中心線を抽出し、SVGパスとして出力するComfyUIカスタムノード

## 機能概要

ラインアート画像 → 線領域検出 → 中心線抽出 → SVGパス出力 → ラスター画像化までの完全なベクトル変換パイプラインを提供します。

## ノード一覧

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

### 3. Mask Line Cleanup
マスク内の重複線や近接線を除去・統合

**入力:**
- `mask`: 線マスク
- `mode`: クリーンアップモード (merge_close_lines/remove_duplicates/thin_only/distance_based)

**出力:**
- `cleaned_mask`: クリーンアップ後のマスク

### 4. SVG Path Cleanup
SVGパスの後処理（重複削除・簡略化・近接頂点マージ）

**入力:**
- `svg_string`: SVGパス文字列
- `min_path_length`: 最小パス長（これより短いパスを削除）
- `simplify_tolerance`: 簡略化許容誤差
- `near_duplicate_distance`: 近接重複判定距離

**出力:**
- `cleaned_svg`: クリーンアップ後のSVG
- `cleanup_stats`: 削除統計 (JSON)

### 5. SVG File Saver / SVG Batch Saver
SVGファイルとメタデータJSONを保存

**入力:**
- `svg_string`: 保存するSVG
- `output_dir`: 出力ディレクトリ
- `filename_prefix`: ファイル名プレフィックス

**出力:**
- `saved_path`: 保存先パス

### 6. SVG To Image
SVG文字列をラスター画像(PNG)に変換

**入力:**
- `svg_string`: SVG文字列
- `width` / `height`: 出力サイズ (0=自動)
- `scale`: スケール係数
- `background`: 背景色モード (transparent/white/black/custom)
- `dpi`: レンダリングDPI

**出力:**
- `image`: ラスター画像 (ComfyUI IMAGE tensor)
- `meta`: レンダリング情報 (JSON)

### 7. Python Runtime Info (診断用)
ComfyUIのPython実行環境とパッケージ情報を出力

**出力:**
- `info`: 環境情報 (JSON形式)

## インストール

### 基本インストール
1. このフォルダを `ComfyUI/custom_nodes/` にコピー
2. ComfyUIを再起動（通常は自動的に依存関係がインストールされます）

すべての依存関係は標準的なライブラリのみで、追加セットアップ不要です。

### SVG To Image ノードについて

`SVG To Image` ノードは**基本的なSVGパスレンダリング**を提供します:
- ✅ **追加依存不要**: Pillow単体で動作（既にComfyUIに含まれています）
- ✅ **Windows完全対応**: ネイティブDLL不要
- ⚠️ **制限事項**: 複雑なSVG機能（グラデーション、フィルター、高度なパス）は未サポート

**サポート範囲:**
- 基本パスコマンド（M, L, H, V, C, Z）
- stroke/fill 色指定
- 単純なライン・ポリゴン描画

**高品質レンダリングが必要な場合:**
- `SVG File Saver` で保存後、Inkscape/Illustrator/ブラウザで画像化を推奨
- Linux/macOS環境ではCairoSVGなど高機能レンダラーの利用も検討可

### 手動インストール（自動インストールが動作しない場合）

#### 依存パッケージの手動インストール

自動インストールが動作しない場合、以下を実行:

1. ComfyUI内で `Python Runtime Info` ノードを実行し、`sys_executable` のパスを確認
2. そのPythonパスを使ってインストール:

```powershell
# PowerShellの例（パスは環境に合わせて変更）
& "C:\path\to\ComfyUI\venv\Scripts\python.exe" -m pip install -r requirements.txt
```

**トラブルシュート:**
- `アクセスが拒否されました` エラー → ComfyUIを一時停止してから実行
- 複数Python環境がある場合 → 必ずComfyUIが使用している実行ファイルで `pip install` すること

## 使い方

1. ComfyUIを起動
2. ノードメニューから `TJ_Vector` カテゴリを選択
3. `Line Region Detector` ノードで線を検出
4. `Centerline to SVG` ノードでSVGを生成

## ライセンス

MIT License

## バージョン

v1.0 - 初期リリース
