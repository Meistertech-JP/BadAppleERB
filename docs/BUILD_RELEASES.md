# 配布アーカイブの再構築 / Rebuilding release archives

## 日本語

この手順は、ソースツリー内の検証済み実行用ファイルを再梱包します。Python 3.10以上を使用し、リポジトリのルートから実行します。

1. `runtime/third_party/PyPy/bundle_provenance.json` の取得元と SHA-256 に対応する、次の公式アーカイブを `upstream/` に配置します。

   - `pypy3.12-v8.0.1-win64.zip`
   - `pypy3.12-v8.0.1-linux64.tar.gz`

2. 次のコマンドで配布物を作成します。

   ```sh
   python3 bundle_release.py --upstream-dir upstream
   ```

3. `deliverables/` に Windows 版、Linux 版、ソース一式、UTF-8 更新用差分、検証記録、アニメーションWebP、`SHA256SUMS.txt` が生成されます。

梱包処理は、実行用ファイル・既存の再生関数・上流アーカイブのハッシュを検証します。さらに、作成したアーカイブを読み戻し、全ファイルのハッシュと Linux 版のシンボリックリンクを照合します。検証記録は、その記録が対象にしたソースのハッシュを保持しています。

`baseline/` と `validation/` はこの照合に必要です。`.gitattributes` の `* -text` は、CMD、ERB、JSON、Unicode 数値データなどのバイト列を Git の改行変換から保護します。PyPy 本体と生成済み配布物は Git 管理の対象外です。

数値モデルを変更・再生成する手順は [HOW_IT_WORKS_ja.txt](../runtime/HOW_IT_WORKS_ja.txt) にあります。配布物の再梱包と、数値モデルの再生成は別の操作です。実行コードやデータを変更した場合は、変更した内容に対応する検証を行い、その結果に基づいてハッシュと検証記録を更新します。

## English

This procedure repackages the verified runtime files in the source tree. Use Python 3.10 or later and run from the repository root.

1. Place the official `pypy3.12-v8.0.1-win64.zip` and `pypy3.12-v8.0.1-linux64.tar.gz` archives in `upstream/`. Their download URLs and expected SHA-256 values are recorded in `runtime/third_party/PyPy/bundle_provenance.json`.
2. Run `python3 bundle_release.py --upstream-dir upstream`.
3. Collect the runtime bundles, source archive, UTF-8 overlay, verification report, animated WebP, and `SHA256SUMS.txt` from `deliverables/`.

The builder checks the recorded runtime hashes, preserved playback functions, and upstream archive hashes. It then reads back the generated archives and verifies every file hash and Linux symbolic link. Historical verification records retain the hashes of the source they cover.

The `baseline/` and `validation/` directories are required by these checks. The `* -text` rule in `.gitattributes` prevents Git line-ending conversion from changing verified bytes. The PyPy interpreter payload and generated release archives are excluded from Git.

See [HOW_IT_WORKS_en.txt](../runtime/HOW_IT_WORKS_en.txt) for model regeneration. Repackaging the runtime and regenerating its numerical model are separate operations. Changes to executable code or model data require appropriate validation before their expected hashes and verification records are updated.
