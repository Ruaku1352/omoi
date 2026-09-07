> Tornado 2026 発表作品

# omoi - 一枚の写真ではなく、一つの思い出を飾る。

<div align="center">

  [![React](https://img.shields.io/badge/React-19.2-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.139-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![Gemini](https://img.shields.io/badge/Google-Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
  [![Firebase](https://img.shields.io/badge/Firebase-Hosting-FFCA28?style=for-the-badge&logo=firebase&logoColor=black)](https://firebase.google.com/)

  **複数の写真に残った一つの出来事を、AIで多層の立体作品へ再構成し、日常に飾れる形で残すプロダクト**

  <img src="./assets/tornado2026_発表用/スライド12.PNG" alt="omoi — Our Memories, One Image" width="760">

  ---

  [![Tornado 2026](https://img.shields.io/badge/Tornado%202026-NTTレゾナントテクノロジー賞-gold?style=for-the-badge&logo=trophy)](#-tornado-2026-)

  ## 🎉 Tornado 2026 🎉
  ### **🏆 NTTレゾナントテクノロジー賞 受賞**
  **チーム「ミリオンがえし」**

  ---

  ### クイックリンク

  [![技術仕様書](https://img.shields.io/badge/技術仕様書-詳細ドキュメント-blue?style=for-the-badge)](./docs/README.md)
  [![ギャラリー](https://img.shields.io/badge/ギャラリー-発表資料-green?style=for-the-badge)](./docs/gallery.md)
  [![Live Demo](https://img.shields.io/badge/Live%20Demo-omoi-4285F4?style=for-the-badge&logo=firebase&logoColor=white)](https://omoi-506412.web.app/)

</div>

---

## 目次

- [Live Demo](#live-demo)
- [🎉 Tornado 2026 🎉](#-tornado-2026-)
- [開発メンバー](#開発メンバー)
- [製品概要](#製品概要)
  - [背景（製品開発のきっかけ・課題など）](#背景製品開発のきっかけ課題など)
  - [製品説明（具体的な製品の説明）](#製品説明具体的な製品の説明)
  - [システム構成](#システム構成)
  - [完成した立体レイヤーアート](#完成した立体レイヤーアート)
  - [特長](#特長)
  - [解決できること](#解決できること)
  - [想定する利用シーン](#想定する利用シーン)
  - [注力したこと（こだわり等）](#注力したことこだわり等)
- [技術仕様書](#技術仕様書)
- [ギャラリー](#-ギャラリー)
- [開発技術](#開発技術)
  - [活用した技術](#活用した技術)
  - [独自の設計](#独自の設計)
- [UI・デザイン](#uiデザイン)

---

## Live Demo

**Webアプリ**: https://omoi-506412.web.app/

## 🎉 Tornado 2026 🎉

omoiは、Tornado 2026にて **NTTレゾナントテクノロジー賞** をいただきました。

## 開発メンバー

| 名前 | 担当 |
| :--- | :--- |
| 担当者 | AI・画像処理 |
| 担当者 | Design / UI |
| 担当者 | Physical Output |
| 担当者 | Backend |
| 担当者 | 横断支援・開発基盤 |
| 担当者 | Frontend |

---

## 製品概要

### 背景（製品開発のきっかけ・課題など）

家族旅行や子どもの成長、誕生日など、大切な出来事ほど多くの写真が残ります。写真を撮り、保存することは簡単になった一方で、写真が増えるほど過去の記録はスマートフォンの中に埋もれ、自分から探さなければ見返す機会は減っていきます。

omoiが向き合うのは、**思い出は残っているのに、日常の中で振り返るきっかけが減っていく**という課題です。

思い出は一枚の写真だけでできているわけではありません。人物、場所、物、景色、そのときの出来事など、複数の断片が重なって形づくられています。omoiは「一番良い一枚」を選ぶのではなく、複数の写真に残った**一つの出来事**を残します。

### 製品説明（具体的な製品の説明）

> **一枚の写真ではなく、一つの思い出を飾る。**

**omoi**は、残したい出来事の複数の写真と任意の思い出テキストをもとに、AIがその出来事を象徴する人物・場所・物を選び、一つの立体レイヤーアートへ再構成するサービスです。

写真をそのまま並べるのではなく、写真に分散した要素を取り出し、前後関係を持たせて一つの作品に構成します。完成案は3Dで確認でき、気になる場合だけ位置・大きさ・前後関係を調整できます。確認した作品は、最終的に日常に置ける2.5Dの物理作品へつながります。

AIは新しい思い出を描き足すためではなく、**「この出来事を一つの作品で表すなら何を残すか」**を考え、最初の完成案をつくるために使います。

### システム構成

| コンポーネント | 技術スタック | 役割 |
| :--- | :--- | :--- |
| **Frontend** | React / TypeScript / Vite | 写真入力、生成結果、3D Preview、2D Edit |
| **Backend API** | Python / FastAPI / Pydantic | 生成の受け付け、作品データと素材の提供 |
| **AI・画像処理** | Gemini / EfficientSAM-Ti / ONNX Runtime | 意味理解、要素選定、構成情報・透明Layer生成 |
| **Physical Output** | 3Dプリント・写真プリント | 確定した作品構成を立体作品へつなぐ |

<div align="center">
<img src="./assets/tornado2026_発表用/スライド30.PNG" width="760" alt="omoiの入力から物理作品までの構成">
</div>

### 完成した立体レイヤーアート

omoiでは、画面上の作品構成と物理出力を別のものにしません。Artwork Dataの `x` / `y` / `scale` / `layerIndex` を3Dプレビュー、編集、STL生成で共有し、実際に完成した立体レイヤーアートまで一つの作品として扱います。

<div align="center">
<img src="./assets/tornado2026_発表用/スライド32.PNG" width="760" alt="完成したomoiの立体レイヤーアート。画面の作品構成を物理作品へ再現している">
</div>

### 特長

#### 1. **一番良い写真ではなく、一つの出来事を残す**

家族、場所、食べ物、景色など、複数の写真に分散した要素を一つの作品に再構成します。「あの旅行」「あの頃」といった出来事全体を、特別な形として残せます。

#### 2. **AIがまず完成案をつくり、必要なときだけ整えられる**

ユーザーが最初から切り抜きや配置を細かく操作する必要はありません。AIがまず完成案を示し、気になる部分がある場合だけ自分の思いを反映できます。AI任せでも、手作業だけでもない体験を目指しています。

#### 3. **思い出を壊さない**

omoiは、元の記録にないものをAIが新たに描き加えるのではなく、実際に撮影した写真に残る人物や物、景色から作品を構成します。思い出を扱うプロダクトだからこそ、記録に根ざした作品づくりを大切にします。

#### 4. **画面の中で終わらせず、日常へ戻す**

完成画像を保存するだけでなく、棚やデスクに置ける物理作品へつなげます。作品がふと目に入ることで、スマートフォンの中に眠っていた出来事を日常の中で振り返る入口をつくります。

### 解決できること

- 複数の写真に残った一つの出来事を、写真の集合ではなく一つの思い出の作品として残せる
- 写真を探しに行かなくても、日常に置いた作品を通じて思い出に触れるきっかけをつくれる
- 専門的な画像編集の知識がなくても、AIの完成案から作品づくりを始められる
- 自分たちの写真に残る要素から、その出来事だけの記念オブジェクトをつくれる

### 想定する利用シーン

子どもの成長、家族旅行、誕生日、入学・卒業、運動会など、多くの写真が残る大切な出来事を、家族で振り返るための作品として想定しています。

- 自分用に飾る記念作品
- 家族で思い出を共有するための作品
- 大切な出来事を贈るギフト

### 注力したこと（こだわり等）

- **複数写真を横断した理解**: 一枚ずつを独立に加工するのではなく、写真群と任意の思い出テキストから「何を残すか」を考える
- **完成案から始めるUX**: 最初から制作作業を求めず、AIによる最初の提案を確認してから必要な部分だけ調整できる
- **デジタルと実物の一貫性**: AI生成、プレビュー、編集、物理出力を別々の作品にせず、同じArtwork Dataでつなぐ
- **End-to-Endの体験**: 写真入力から物理作品までを一つの流れとして成立させる

---

## 技術仕様書

詳細な仕様は、領域ごとの専門資料としてまとめています。

### Tornado 2026版

- **[プロダクト仕様書](./docs/README.md)** - omoiの全体像と作品づくりの流れ
- **[Artwork Data仕様書](./docs/artwork-data-specification-tornado2026.md)** - 画面と実物をつなぐ作品構成
- **[フロントエンド仕様書](./docs/frontend-specification-tornado2026.md)** - 写真選択、3D確認、2D微調整、完成までの体験
- **[バックエンド仕様書](./docs/backend-specification-tornado2026.md)** - 作品生成、進行状況、出力データの受け渡し
- **[AI・画像処理仕様書](./docs/ai-image-processing-specification-tornado2026.md)** - 写真理解、要素抽出、構成提案
- **[物理出力仕様書](./docs/physical-output-specification-tornado2026.md)** - STL・写真プリント用データから立体作品へ至る流れ

## 📸 ギャラリー

Tornado 2026の発表資料に含まれる、プロダクトの考え方、入力から作品への変換、構成図はギャラリーページにまとめています。

**[ギャラリーページを見る](./docs/gallery.md)**

## 開発技術

### 活用した技術

| カテゴリ | 技術スタック | 用途 |
| :--- | :--- | :--- |
| **Frontend** | React / TypeScript / Vite | 写真入力、生成結果の表示、作品編集UI |
| **3D / 2D表現** | three / React Three Fiber / Konva | 立体プレビューと2D編集 |
| **Backend** | Python / FastAPI / Pydantic | 生成の受け付け、作品データと素材の提供 |
| **AI・画像処理** | Gemini / EfficientSAM-Ti / ONNX Runtime | 意味理解、要素選定、透明Layer生成 |
| **Hosting** | Firebase Hosting / Cloud Run | Frontend・BackendのDeploy Unit |

### 独自の設計

| 設計 | 概要 | 仕様書 |
| :--- | :--- | :--- |
| **Artwork Data** | AI、Backend、Frontend、物理出力で共有する、作品構成の唯一の正本 | [システム仕様書](./docs/system-specification-tornado2026.md) |
| **Asset Manifest** | Artwork Dataから実行時URLを分離し、Layer Assetを解決する仕組み | [バックエンド仕様書](./docs/backend-specification-tornado2026.md) |
| **編集可能な作品構成** | 一枚の完成画像で終わらせず、位置・大きさ・前後関係を持つLayerとして扱う | [フロントエンド仕様書](./docs/frontend-specification-tornado2026.md) |
| **物理出力への接続** | 画面で確認・編集した同じ作品データを、物理作品の入力として使う | [物理出力仕様書](./docs/physical-output-specification-tornado2026.md) |

## UI・デザイン

omoiでは、ユーザーが最初から細かな作品編集をするのではなく、写真と思い出を入力したあとにAIの完成案を確認する体験を中心に設計しています。

3Dプレビューでは完成形の立体感を確認し、気になる場合だけ2D編集で位置・大きさ・前後関係を調整します。写真だけでは分からない「自分にとって何が大切だったか」を思い出テキストで補いながら、できるだけ少ない操作で自分らしい作品へ近づけることを目指します。
