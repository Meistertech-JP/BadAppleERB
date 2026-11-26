# Bad Apple!! ERB

Bad Apple!! ERB plays the silhouette animation in a terminal using a single ERB script. The title menu selects either playback synchronized to elapsed time or playback of every source frame. Both modes calculate the same 79 × 24 grayscale picture from numerical span trajectories.

The movie contains **6,573 frames at 30 frames per second**, with a **219.100-second** timeline. Playback is video only; there is no audio.

For the full explanation of image generation and scheduling, see [HOW_IT_WORKS_en.txt](HOW_IT_WORKS_en.txt). Japanese documentation is available in [README_ja.md](README_ja.md) and [HOW_IT_WORKS_ja.txt](HOW_IT_WORKS_ja.txt).

## Quick start

Extract the complete archive before launching. Keep the files and subdirectories together, and use an interactive terminal with at least **80 columns × 25 rows**, a monospaced font, and 24-bit color support.

### Windows x64 package

Run `BadAppleERB.cmd` from the extracted folder. It selects the bundled PyPy interpreter automatically.

The launcher uses `console_utf8.py` from the same folder to configure console input, console output, and Python text streams for UTF-8 automatically. When the program exits, it restores the original console input and output code pages separately.

### Linux x64 package

Open a terminal in the extracted folder and run:

```sh
sh ./run.sh
```

The platform packages include PyPy, so a separate Python installation is not needed for their default launchers. The initial selection loads the numerical movie data; the title screen displays a loading message during this step.

## Menu and controls

Type a number and press **Enter**. The on-screen labels are Japanese:

| Number | Label | Action |
|---|---|---|
| `1` | 時間同期 | Synchronize playback to elapsed time. |
| `2` | 全フレーム | Calculate and display every frame in order. |
| `0` | 終了 | Exit. |

Playback returns to the title menu when it finishes. A different mode can then be selected, or the same mode can be played again. Empty or invalid input displays an input hint and keeps the menu open. **Ctrl+C** interrupts the program.

The title illustration is static ASCII art depicting a ribboned silhouette, an apple, and a witch with a broom. It is embedded in `PLAYER.ERB`; the movie itself uses the numerical rendering pipeline described below.

## Choosing a playback mode

### 1 — Time-synchronized playback

The player calculates the source-frame index from the elapsed clock time. If calculation or terminal output falls behind, it skips obsolete frames and proceeds to the current frame. The target movie duration is **3 minutes 39.1 seconds**, excluding menu time and initial data loading.

A selected frame finishes calculation and display before the next target is chosen. The final source frame is displayed, and any calculation or terminal update that crosses the end boundary can extend playback by that remaining work. This mode does not accumulate a queue of missed frames to play afterward.

### 2 — All-frame playback

The player visits frames `0` through `6572` in order. It waits for the nominal 30 fps deadlines when processing is fast enough. When processing is slower, it continues with the next consecutive frame without dropping any frames, so playback can take longer than 219.100 seconds.

Both choices use the same renderer, trajectory data, and grayscale values. The scheduling policy determines which source frames are displayed and when.

## Interpreter selection

The default launchers choose an interpreter in this order:

1. The executable specified by `PYEMUERA_PYTHON`, if that variable is set.
2. The bundled PyPy executable.
3. `python` on Windows, or `python3` on Linux, otherwise.

The packages contain **PyPy 8.0.1**, with **Python 3.12.15** compatibility, and **PyEmuera 3.0.0**. Upstream identifies the Python 3.12 implementation in this PyPy release as beta. Interpreter licenses and component notices are included under `pypy/` and `third_party/`; version and archive information is recorded in `third_party/PyPy/bundle_provenance.json`.

An installed **CPython 3.10 or later** can run the same ERB and menu. On Windows, use:

```bat
BadAppleERB_CPython.cmd
```

On Linux, use:

```sh
PYEMUERA_PYTHON=python3 sh ./run.sh
```

`PYEMUERA_PYTHON` accepts an executable name or path. Supply the executable alone, without command-line arguments. A path containing spaces must be quoted when setting the variable in the shell.

## Terminal display

The movie occupies **79 columns × 24 rows**. The remaining terminal column and row provide room for ordinary console cursor behavior without wrapping the picture. Playback uses the whole picture area without menu text or progress counters over the image.

Black cells are spaces. Nonblack cells are `#` characters whose foreground color represents an 8-bit grayscale value from 1 to 255. A 24-bit color terminal preserves those requested colors; a terminal with fewer colors can quantize them.

The reconstruction target is the movie after conversion to the fixed 79 × 24 grayscale reference. The visible shape of `#`, glyph antialiasing, line spacing, and physical cell dimensions are controlled by the terminal font. To approach the original 4:3 display aspect ratio, use cells whose height is approximately **2.47 times their width**. Font settings do not change the calculated grayscale cell values.

## Runtime requirements

- The Windows package is for 64-bit Windows. Its PyPy interpreter uses the Microsoft x64 Visual C++ runtime and Windows Universal C Runtime.
- The Linux package is for x86_64 systems with glibc 2.28 or later.
- The extracted directory must be writable for diagnostics and engine-generated logs or caches.
- Playback needs an interactive terminal with cursor control, UTF-8 text support, a monospaced font, and 24-bit color. A font with Japanese glyphs makes the menu labels readable.

Normal playback uses only the bundled engine, script, and numerical data. It does not require the original MP4, FFmpeg, NumPy, or an Internet connection. The separate source package includes tools and requirements for rebuilding the numerical data.

## Files

| File or directory | Purpose |
|---|---|
| `BadAppleERB.cmd`, `run.sh` | Default platform launchers. |
| `BadAppleERB_CPython.cmd` | Windows launcher for an installed CPython. |
| `console_utf8.py` | Windows UTF-8 console setup, engine startup, and restoration of the original code pages. |
| `PyEmuera.pyz` | ERB interpreter. |
| `ERB/PLAYER.ERB` | Menu, both playback modes, and the shared renderer. |
| `ERB/PLAYER.ERH` | Runtime variables and state arrays. |
| `ERB/GEOMETRY.ERH` | Movie constants and shared rational-curve coefficients. |
| `txt00.txt`–`txt04.txt` | Packed numerical trajectories and topology events. |
| `packed_format.json` | Data-format description and payload checksums. |
| `CSV/` | Game metadata required by the engine. |
| `pypy/` | Bundled platform interpreter. |
| `third_party/` | Component notices, provenance, and licenses. |
| `logs/diagnostics.log` | Standard-error output from the latest launcher run. |

Keep the payload files byte-for-byte intact. Although they have `.txt` extensions, their characters encode numbers and should not be edited or reformatted as prose.

## Troubleshooting

**The picture wraps, scrolls, or loses a row.** Set the terminal to at least 80 × 25 before starting, use a monospaced font, and launch in a terminal rather than an editor output panel. Check that the terminal supports cursor movement and line replacement.

**Gray edges look stepped or colors are missing.** Enable the terminal's 24-bit color mode. Some terminals or remote-console configurations reduce the requested RGB values to a smaller palette.

**Japanese menu text is garbled or appears as boxes.** On Windows, extract `BadAppleERB.cmd` and `console_utf8.py` together from the same package version, then start with `BadAppleERB.cmd`; it configures UTF-8 automatically. For missing glyphs shown as boxes, select a monospaced font or fallback font with Japanese glyphs. On Linux, use a UTF-8 terminal. The menu numbers remain `1`, `2`, and `0`.

**All-frame playback is slow.** This mode intentionally retains every frame. Select `1` for elapsed-time playback, and check that the default launcher is using the bundled PyPy rather than an unintended `PYEMUERA_PYTHON` override.

**Windows reports that `VCRUNTIME140.dll` is missing.** Install the Microsoft x64 Visual C++ runtime referenced by the [official PyPy download instructions](https://pypy.org/download.html), then launch again.

**The interpreter cannot be found or started.** Check that the correct platform archive was fully extracted, the `pypy/` directory is intact, and `PYEMUERA_PYTHON` points to a valid executable. On Linux, preserve the executable permissions and symbolic links from the tar archive.

**A data-loading error appears.** Restore `txt00.txt` through `txt04.txt` and `ERB/GEOMETRY.ERH` from the same archive. Do not mix generated files from different builds. The launchers set the working directory to the game folder automatically.

**The program exits with an error.** Read `logs/diagnostics.log`. The Windows launcher prints the exit code and the log location if an error occurs. Open the log as UTF-8. Check that the extracted directory is writable and that the required platform runtime is installed.
