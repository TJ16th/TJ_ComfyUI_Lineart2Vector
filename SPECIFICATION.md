# Center Vector - ComfyUI Custom Node 仕様書

## 概要
ラインアート画像から中心線を抽出し、SVGパスとして出力するComfyUIカスタムノード

## ノード構成

### 2ノード構成（推奨案）

```
[Image Input]
     ↓
[Line Region Detector]
     ↓
[Line Mask] + [Preview Image]
     ↓
[Centerline to SVG]
     ↓
[SVG String] + [Centerline Preview]
```

---

## ノード1: Line Region Detector

### 機能
- 背景と前景の分離
- 線領域と塗り領域の分離
- カラー情報の抽出（オプション）

### 入力
| パラメータ | 型 | デフォルト | 範囲 | 説明 |
|-----------|-----|-----------|------|------|
| `image` | IMAGE | - | - | 入力画像 |
| `background_mode` | ENUM | "auto" | auto/white/black/custom | 背景色の検出方法 |
| `background_threshold` | INT | 240 | 0-255 | 背景判定の閾値 |
| `line_detection_method` | ENUM | "edge" | edge/morphology/hybrid | 線検出アルゴリズム |
| `min_line_width` | INT | 1 | 1-100 | 想定される最小線幅（ピクセル） |
| `max_line_width` | INT | 50 | 1-500 | 想定される最大線幅（ピクセル） |
| `fill_handling` | ENUM | "separate" | ignore/separate/include | 塗り領域の扱い |
| `color_clustering` | BOOLEAN | False | - | 色でクラスタリングするか |
| `num_colors` | INT | 5 | 2-20 | クラスタリング時の色数 |

### 出力
| 出力名 | 型 | 説明 |
|-------|-----|------|
| `line_mask` | MASK | 線領域のマスク（白黒） |
| `fill_mask` | MASK | 塗り領域のマスク（オプション） |
| `preview_image` | IMAGE | 検出結果のプレビュー画像 |
| `color_info` | STRING | JSON形式の色情報 |

### 処理アルゴリズム

#### 1. 前処理
```
- RGBからグレースケール変換
- ノイズ除去（ガウシアンブラー）
```

#### 2. 背景分離
```
方法1: Auto
  - Otsu's method で自動閾値決定
  - または、4隅のピクセル値から背景色を推定

方法2: White/Black
  - 固定閾値で二値化

方法3: Custom
  - ユーザー指定の色を背景として除去
```

#### 3. 線領域検出
```
方法1: Edge (エッジベース)
  - Canny エッジ検出
  - モルフォロジー処理（Dilation）で線を太らせる
  - 内部の塗りを除去

方法2: Morphology (モルフォロジーベース)
  - Erosion で塗り領域を縮小
  - Opening/Closing で線領域を強調
  - 差分から線領域を抽出

方法3: Hybrid
  - Edge と Morphology を組み合わせ
  - より正確な線領域を検出
```

#### 4. 塗り領域の分離（オプション）
```
- 前景マスクから線マスクを減算
- Flood fill で連結領域を特定
- 小さすぎる領域はノイズとして除去
```

#### 5. カラークラスタリング（オプション）
```
- K-means で色空間をクラスタリング
- 各クラスタの代表色を抽出
- 領域ごとの色情報を JSON で出力
```

---

## ノード2: Centerline to SVG

### 機能
- Distance Transform による中心線抽出
- Ridge Detection（尾根検出）
- SVGパスの生成
- パスの最適化と平滑化

### 入力
| パラメータ | 型 | デフォルト | 範囲 | 説明 |
|-----------|-----|-----------|------|------|
| `line_mask` | MASK | - | - | 線領域のマスク |
| `original_image` | IMAGE | - | - | 元画像（色情報用、オプション） |
| `color_info` | STRING | "" | - | JSON形式の色情報（オプション） |
| `algorithm` | ENUM | "ridge" | ridge/skeleton/watershed | 中心線抽出アルゴリズム |
| `smoothing` | FLOAT | 2.0 | 0.0-10.0 | パスの平滑化レベル |
| `min_path_length` | INT | 10 | 1-1000 | 最小パス長（ピクセル） |
| `simplify_tolerance` | FLOAT | 1.0 | 0.0-10.0 | Douglas-Peucker 簡略化の許容値 |
| `bezier_smoothing` | BOOLEAN | True | - | ベジェ曲線で平滑化するか |
| `preserve_colors` | BOOLEAN | True | - | 元の色を保持するか |

### 出力
| 出力名 | 型 | 説明 |
|-------|-----|------|
| `svg_string` | STRING | SVG形式の文字列 |
| `centerline_image` | IMAGE | 中心線のプレビュー画像 |
| `path_count` | INT | 生成されたパス数 |
| `statistics` | STRING | JSON形式の統計情報 |

### 処理アルゴリズム

#### 1. Distance Transform
```
- cv2.distanceTransform で境界からの距離を計算
- 距離マップから局所最大値を検出
- これらが線の中心軸となる
```

#### 2. 中心線抽出

##### Ridge Detection（推奨）
```
- 距離マップの Hessian 行列を計算
- 固有値解析で尾根（Ridge）を検出
- 連続性を保ちながら中心線を抽出
```

##### Skeleton（代替手法）
```
- Zhang-Suen Thinning アルゴリズム
- または、skimage.morphology.skeletonize
- 位相を保った骨格化
```

##### Watershed（代替手法）
```
- Watershed セグメンテーション
- 分水嶺から中心線を導出
```

#### 3. パス生成
```
1. 連結成分解析
   - 各連結領域を個別のパスとして処理
   
2. 点列の順序付け
   - 端点を検出
   - 深さ優先探索で点を順序付け
   - 分岐点の処理
   
3. パス簡略化
   - Douglas-Peucker アルゴリズム
   - 冗長な点を削減
   
4. 平滑化
   - Catmull-Rom スプライン
   - または、ベジェ曲線で近似
```

#### 4. SVG生成
```
構造:
<svg width="W" height="H" xmlns="http://www.w3.org/2000/svg">
  <metadata>
    <created>timestamp</created>
    <source>tj_comfyui_centerVector</source>
    <parameters>...</parameters>
  </metadata>
  <g id="centerlines">
    <path id="path0" d="M x,y L x,y ..." 
          stroke="color" stroke-width="2" 
          fill="none" />
    ...
  </g>
</svg>
```

#### 5. 色情報の統合
```
- original_image から各パスの位置の色をサンプリング
- または、color_info JSON から色をマッピング
- SVG の stroke 属性に反映
```

---

## 追加ユーティリティノード（将来実装）

### Mask Editor
- マスクの手動修正
- ブラシツール、消しゴムツール
- 領域の追加・削除

### SVG Exporter
- SVGファイルとして保存
- ファイル名、パスの指定
- メタデータの埋め込み

### Path Simplifier
- 既存のSVGパスを簡略化
- 点数の削減
- 再平滑化

### Multi-layer SVG Combiner
- 複数のSVGレイヤーを統合
- Z-order の管理
- グループ化

---

## 技術スタック

### 必須ライブラリ
- `numpy`: 配列処理
- `opencv-python` (cv2): 画像処理
- `opencv-contrib-python`: Thinning アルゴリズム
- `scikit-image`: モルフォロジー処理
- `scipy`: 科学計算、補間

### オプションライブラリ
- `svgwrite`: SVG生成の補助
- `shapely`: 幾何計算
- `Pillow`: 画像I/O

---

## 性能要件

### 処理速度
- 1024x1024 画像: < 5秒（目標）
- 2048x2048 画像: < 20秒（目標）

### メモリ使用量
- 基本: 画像サイズの 5-10倍
- Distance Transform: 追加で 2-3倍

### 精度
- 中心線の位置誤差: ± 1ピクセル以内
- パスの簡略化後も視覚的に元の形状を保持

---

## エラーハンドリング

### 入力検証
- 画像が空でないか
- マスクのサイズが画像と一致するか
- パラメータが有効範囲内か

### 処理エラー
- 線が検出できない場合 → 空のSVGを返す
- メモリ不足 → ダウンサンプリングして再試行
- アルゴリズム失敗 → 代替手法にフォールバック

---

## 出力例

### SVG出力サンプル
```xml
<svg width="512" height="512" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <metadata>
    <created>2025-11-08T00:00:00</created>
    <generator>tj_comfyui_centerVector v1.0</generator>
  </metadata>
  <g id="centerlines">
    <path id="path0" d="M 100,100 Q 150,120 200,100 L 250,150" 
          stroke="#000000" stroke-width="2" 
          fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <path id="path1" d="M 300,200 L 350,250 Q 380,280 400,300" 
          stroke="#FF0000" stroke-width="2" 
          fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>
```

### 統計情報サンプル（JSON）
```json
{
  "path_count": 2,
  "total_length": 1234.56,
  "average_path_length": 617.28,
  "processing_time": 2.34,
  "colors_detected": ["#000000", "#FF0000"],
  "image_size": [512, 512],
  "parameters": {
    "algorithm": "ridge",
    "smoothing": 2.0,
    "min_path_length": 10
  }
}
```

---

## バージョン管理

### v1.0（初期リリース）
- 基本的な2ノード構成
- Ridge Detection アルゴリズム
- SVG出力

### v1.1（計画）
- 色保持機能の強化
- 複数アルゴリズムの選択
- 性能最適化

### v2.0（将来）
- ユーティリティノードの追加
- GPU アクセラレーション
- リアルタイムプレビュー

---

## ライセンス
MIT License

## 作成者
tj_comfyui_centerVector

## 更新日
2025-11-08
