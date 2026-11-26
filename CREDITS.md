# Credits and license scope / クレジットとライセンスの範囲

## 日本語

### プロジェクトのコード

Bad Apple!! ERB の独自のプログラムコードと説明文は、同梱の `LICENSE` に記載された MIT License の下で提供されます。著作権表示は **Copyright (c) 2026 Meistertech-JP** です。

この MIT License は、元映像、原作のキャラクター、楽曲、同梱する第三者のソフトウェアに新たな権利を付与するものではありません。各作品・コンポーネントの権利とライセンスは、それぞれの権利者に帰属します。

### 元映像

- 作品名: **【東方】Bad Apple!!　ＰＶ【影絵】**
- 投稿者: **あにら**
- 出典: [ニコニコ動画 sm8628149](https://www.nicovideo.jp/watch/sm8628149)
- 原作: **東方Project — ZUN / 上海アリス幻樂団**

`reference_frames.npz`、`persistent_gray/geometry_model.npz`、`ERB/GEOMETRY.ERH`、`txt00.txt`～`txt04.txt` は、元映像から生成した参照配列・数値モデル・係数・イベントデータです。ソースでは実行用のファイルを `runtime/` 以下に配置しています。数値へ変換しても元映像との関係は変わらず、プロジェクトの MIT License はこれらに含まれる元作品の表現を再許諾しません。映像の再現を含むプレビュー、端末記録、AA なども、原作・元作品に関する権利を一括して MIT License に変更する対象ではありません。

### 元映像で使用されている楽曲

本プログラムは映像のみを再生します。配布物には音源を含みません。

| 項目 | クレジット |
|---|---|
| 楽曲名 | Bad Apple!! feat. nomico |
| 原曲作曲 | ZUN |
| 作詞 | Haruka |
| 歌唱 | nomico |
| 編曲 | Masayoshi Minoshima (Alstroemeria Records) |

楽曲のクレジットは [Alstroemeria Records の公式案内](https://alst.net/licensing/) に基づきます。原作の案内は [東方Projectの二次創作ガイドライン](https://touhou-project.news/guideline/) を参照してください。これらの出典表記は、元映像や楽曲の利用許諾を示すものではありません。

### 同梱ソフトウェア

- **[PyEmuera 3.0.0](https://github.com/Meistertech-JP/PyEmuera/releases/tag/v3.0.0)**: `PyEmuera.pyz` を収録しています。MIT License と関連する告知・ライセンスは `third_party/PyEmuera/` にあります。
- **[PyPy 8.0.1 / Python 3.12.15](https://doc.pypy.org/release-v8.0.1.html)**: Windows x64版・Linux x86_64版の実行用アーカイブに、公式配布物を同梱しています。PyPy 本体と同梱ライブラリーのライセンスは `pypy/LICENSE` およびその配下の各ライセンス文書にあります。取得元・ハッシュ・構成の記録は `third_party/PyPy/` にあります。

上記の相対パスは実行用パッケージのルートを基準とします。ソースツリーでは `runtime/` 以下が対応します。PyPy 本体は実行用アーカイブに含まれます。

## English

### Project-authored code

The original program code and documentation of Bad Apple!! ERB are provided under the MIT License in `LICENSE`, with **Copyright (c) 2026 Meistertech-JP**.

This MIT License does not grant new rights to the original video, Touhou characters, music, or bundled third-party software. Those works and components retain their respective rights and licenses.

### Original video and derived data

The visual reference is **【東方】Bad Apple!!　ＰＶ【影絵】**, uploaded by **あにら (Anira)**: [Niconico sm8628149](https://www.nicovideo.jp/watch/sm8628149). The underlying work is **Touhou Project by ZUN / Team Shanghai Alice**.

`reference_frames.npz`, `persistent_gray/geometry_model.npz`, `ERB/GEOMETRY.ERH`, and `txt00.txt` through `txt04.txt` are reference arrays, numerical models, coefficients, and event data derived from that video. Runtime files are under `runtime/` in the source tree. Encoding the animation as numbers does not remove its connection to the original work; this project's MIT License does not relicense the original expression contained in those data. The same distinction applies to previews, terminal recordings, ASCII artwork, and other material incorporating imagery from the original works.

### Music credited by the original video

Playback is visual only. No audio recording is included in the distribution.

| Role | Credit |
|---|---|
| Title | Bad Apple!! feat. nomico |
| Original composer | ZUN |
| Lyrics | Haruka |
| Vocals | nomico |
| Arrangement | Masayoshi Minoshima (Alstroemeria Records) |

Music credits follow [Alstroemeria Records' official page](https://alst.net/licensing/). See also the [Touhou Project Fan Work Guidelines](https://touhou-project.news/guideline/). Attribution is not a grant of permission for the video or music.

### Bundled software

- **[PyEmuera 3.0.0](https://github.com/Meistertech-JP/PyEmuera/releases/tag/v3.0.0)** is included as `PyEmuera.pyz`. Its MIT License and accompanying notices are preserved under `third_party/PyEmuera/`.
- **[PyPy 8.0.1 / Python 3.12.15](https://doc.pypy.org/release-v8.0.1.html)** is bundled from the official Windows x64 and Linux x86_64 distributions in the corresponding runtime archives. Its license and bundled-library notices are preserved in `pypy/LICENSE` and the other license files within that directory. Download provenance, hashes, and file inventories are recorded under `third_party/PyPy/`.

These component paths are relative to the runtime-package root, or to `runtime/` in the source tree. The PyPy interpreter itself is included in the runtime archives.
