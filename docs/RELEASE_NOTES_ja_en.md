# Bad Apple!! ERB — リリースノート / Release notes

## 日本語

### 収録内容

79桁×24行の Bad Apple!! 文字映像を、AA 付きメニューから2種類の方式で再生できます。メニュー、フレーム計算、表示処理、両再生方式は、1つの `PLAYER.ERB` に収録されています。

| 入力 | 選択 | 動作 |
|---|---|---|
| `1` | 時間同期 | 経過時間に対応するフレームを選び、処理が遅れたコマを省略する |
| `2` | 全フレーム | 全6,573コマを順番に計算して表示する |
| `0` | 終了 | プログラムを終了する |

半角数字を入力して Enter で決定します。再生が終わるとメニューへ戻り、繰り返し再生や方式の切り替えができます。メニューの静止 AA は、大きなリボン、リンゴ、魔女帽子と箒をモチーフにしています。

両方式は共通の数値モデルと描画処理を使用します。時間同期は30 fps・**219.100秒（3分39.1秒）**の時間軸を基準に進み、最終フレームを表示します。終端をまたいだ計算・表示に必要な時間は、目標時間を超過することがあります。全フレームはコマを省略せず、処理性能に応じて再生時間が長くなります。

### Windows の UTF-8 起動処理

`BadAppleERB.cmd` は `console_utf8.py` を通して起動し、コンソールの入出力と Python の標準ストリームを UTF-8 に設定します。日本語メニューの出力とコンソールのコードページをそろえ、起動前の入力・出力コードページをそれぞれ保存して、終了処理で復元します。`BadAppleERB_CPython.cmd` も同じ起動経路を使用します。

文字化けする場合は、同じ配布版の `BadAppleERB.cmd` と `console_utf8.py` を両方展開し、`BadAppleERB.cmd` から起動してください。文字が四角になる場合は、日本語の字形を持つフォントを使用してください。

### 配布ファイル

GitHub の Releases に、次のファイルを収録します。

| ファイル | 内容 |
|---|---|
| `BadAppleERB_79x24_menu_win64_PyPy.zip` | Windows x64実行用。PyPy 同梱 |
| `BadAppleERB_79x24_menu_linux64_PyPy.tar.gz` | Linux x86_64実行用。PyPy 同梱 |
| `BadAppleERB_79x24_menu_source.zip` | 生成用スクリプト、参照データ、実行用ファイルを含むソース一式 |
| `BadAppleERB_79x24_menu_verification.json` | 再構成・再生処理などの確認結果 |

実行用パッケージは **PyEmuera 3.0.0** と **PyPy 8.0.1（Python 3.12.15）** を使用します。PyPy の Python 3.12 実装は上流で beta と位置づけられています。通常の再生に元の MP4、FFmpeg、NumPy は不要です。

### 起動と表示条件

Windows は展開したフォルダーの `BadAppleERB.cmd` を起動します。Linux は展開先で次を実行します。

```sh
sh ./run.sh
```

リポジトリのソースから実行する場合は、Python 3.10以上を用意し、`runtime` 内で起動します。

```sh
cd runtime
python -B console_utf8.py PyEmuera.pyz .
```

必要に応じて `python` を `python3` に置き換えてください。

- 端末は **80桁×25行以上**。本編は79桁×24行・256階調です。
- 24ビットカラー、ANSI の画面制御、UTF-8、日本語対応の等幅フォントを使用します。
- 音声はありません。初回のデータ読み込みとメニュー操作は、映像の再生時間に含まれません。
- Windows x64版は Windows UCRT と Microsoft x64 Visual C++ ランタイム、Linux x86_64版は glibc 2.28以上を使用します。
- 診断ログと再生記録を保存するため、書き込み可能な場所へ展開してください。

映像の一致対象は、元動画を固定条件で縮小した79×24セルの明度です。端末の字形、行間、文字セルの縦横比は表示環境に従います。

操作方法は [README_ja.md](../runtime/README_ja.md)、生成と再生の詳しい説明は [HOW_IT_WORKS_ja.txt](../runtime/HOW_IT_WORKS_ja.txt) を参照してください。プロジェクトで作成したコードのライセンスは [LICENSE](../LICENSE)、元映像・動画由来のデータ・同梱コンポーネントについては [CREDITS.md](../CREDITS.md) に記載しています。

## English

### Included features

Bad Apple!! ERB plays a 79-column × 24-row character animation through a title menu with static ASCII artwork. One `PLAYER.ERB` contains the menu, frame calculation, presentation, and both playback modes.

| Input | Selection | Behavior |
|---|---|---|
| `1` | Time-synchronized | Selects the current frame from elapsed time and skips obsolete frames when processing is late. |
| `2` | All frames | Calculates and displays all 6,573 frames in sequence. |
| `0` | Exit | Closes the program. |

Type a number and press Enter. Playback returns to the menu for another selection. The title artwork depicts a ribboned silhouette, an apple, and a witch hat and broom.

Both modes share the numerical model and renderer. Time-synchronized playback follows the **30 fps, 219.100-second** timeline and displays the final frame. Calculation or presentation that crosses the end boundary can extend playback by the work required to finish. All-frame playback preserves every frame and can take longer when processing is slow.

### Windows UTF-8 startup

`BadAppleERB.cmd` starts the engine through `console_utf8.py`, which aligns console input, console output, and Python text streams with UTF-8. It preserves the original input and output code pages separately and restores changed pages during shutdown. `BadAppleERB_CPython.cmd` uses the same startup path.

If Japanese menu text is garbled, extract `BadAppleERB.cmd` and `console_utf8.py` together from the same package version and launch with `BadAppleERB.cmd`. Missing-glyph boxes require a font with Japanese glyphs.

### Release assets

The GitHub release includes:

| File | Contents |
|---|---|
| `BadAppleERB_79x24_menu_win64_PyPy.zip` | Windows x64 runtime with bundled PyPy. |
| `BadAppleERB_79x24_menu_linux64_PyPy.tar.gz` | Linux x86_64 runtime with bundled PyPy. |
| `BadAppleERB_79x24_menu_source.zip` | Build scripts, reference data, and runtime files. |
| `BadAppleERB_79x24_menu_verification.json` | Reconstruction and playback verification results. |

The runtime bundles use **PyEmuera 3.0.0** and **PyPy 8.0.1 with Python 3.12.15**. Upstream identifies this Python 3.12 implementation as beta. Normal playback does not require the original MP4, FFmpeg, or NumPy.

### Startup and display requirements

On Windows, run `BadAppleERB.cmd` from the extracted folder. On Linux, run:

```sh
sh ./run.sh
```

To run the repository with an installed Python 3.10 or later:

```sh
cd runtime
python -B console_utf8.py PyEmuera.pyz .
```

Use `python3` instead of `python` where appropriate.

- Use a terminal of at least **80 columns × 25 rows**. The movie occupies 79 × 24 cells with 256 grayscale levels.
- The terminal needs 24-bit color, cursor control, UTF-8 support, and a monospaced font with Japanese glyphs.
- Playback has no audio. Initial data loading and menu time are outside the movie timeline.
- The Windows x64 package uses Windows UCRT and the Microsoft x64 Visual C++ runtime. The Linux x86_64 package requires glibc 2.28 or later.
- Extract to a writable location for diagnostic and playback logs.

The reconstruction target is the fixed 79 × 24 grayscale reference derived from the original video. Glyph shape, line spacing, and physical cell proportions depend on the terminal.

See [README_en.md](../runtime/README_en.md) for usage and troubleshooting, and [HOW_IT_WORKS_en.txt](../runtime/HOW_IT_WORKS_en.txt) for the numerical model and playback scheduling. [LICENSE](../LICENSE) covers project-authored code. [CREDITS.md](../CREDITS.md) describes the original video, video-derived data, and upstream components.
