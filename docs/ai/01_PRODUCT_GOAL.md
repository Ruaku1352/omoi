# AI処理から見たomoiの課題とゴール

## omoiが解決したいこと

写真は大量に撮られるが、デジタルストレージに埋もれ、あとから自然に見返す機会が少ない。
omoiは、複数写真の中から思い出を象徴するものをAIが見つけ、棚などに置ける2.5Dの物理作品として残す。

## AI処理の成功条件

AI処理が成功しているとは「画像認識精度が高い」ことではない。

以下を満たすこと:

1. ユーザーが手作業で切り抜き対象を指定しなくても初期作品ができる
2. 写真群の文脈から「思い出として意味のある要素」を選べる
3. 元写真由来の人物・物体が自然な形で残る
4. 作品として使える3〜5程度のLayer Assetが生成できる
5. LayerはあとからFrontendで編集・差し替えできる
6. 生成がCloud Run CPU構成で現実的に完了する

## P0で目指さないもの

- 3D Scene Reconstruction
- 正確なMetric Depth推定
- 写真内全Objectの完全なPanoptic Segmentation
- 生成AIで元写真にない面・形状を補完
- 一枚の完成画像を生成してから再Segmentation
- 写真を完全自動で芸術評価すること

## Sceneの再現ではなくArtwork生成

```text
Scene Depth != Artwork Layer Order
```

元写真で手前にある物体が、Artworkで必ず最前面になるとは限らない。
主役を前面に置く等、作品としての意味が優先される。

## Object != Artwork Layer

1つのLayerは1 Object Maskとは限らない。

例:

```text
「誕生日の主役」
= 子ども + パーティーハット + 手に持つプレゼント
```

複数Maskをunionして1 Visual Elementにする設計を許容する。
