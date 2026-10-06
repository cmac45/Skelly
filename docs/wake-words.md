# Custom wake words: "Hello Skelly" and "Hey Skelly"

Both are [microWakeWord](https://github.com/kahrendt/microWakeWord) models
(`esphome/wakeword/*.tflite` + `.json`), running on the reSpeaker at the same
time through Home Assistant's two wake-word slots.

| Model | Trained on | Notes |
|---|---|---|
| `hello_skelly` | ~45,000 synthetic samples (Piper TTS, US + UK) | Works well for adults; young kids struggled to wake it |
| `hey_skelly` | The same synthetic recipe **plus** real family recordings and child-pitched copies | Trained to fix the kids problem |

## Training

Training ran in the community
[microwakeword-trainer Colab notebook](https://github.com/alfiedennen/microwakeword-trainer)
(A100 runtime, about 45 minutes). The cells in `esphome/wakeword/colab/`
are what was pasted into it:

| File | Use |
|---|---|
| `hello_skelly_colab_config.py`, `hey_skelly_colab_config.py` | Paste over the notebook's "CONFIGURE YOUR WAKE WORD HERE" cell |
| `colab_fix_download_cell.py` | **Replaces** the "Download standard negative datasets" cell. The original links broke: the negative datasets now ship as zips and AudioSet moved to parquet |
| `colab_real_recordings_and_kid_voices_cell.py` | New cell above "Augmentation + feature extraction": adds your own recordings (uploaded as `real_recordings.zip` to the Drive folder) and child-pitched copies of a third of the synthetic samples |
| `colab_status_check_cell.py` | After a Colab restart: restores paths and reports which steps' files survived |

### Lessons

- **Kids say "Skelly" like "Kelly".** The first model listed "Hello Kelly",
  "Hello Shelly" and similar as *negatives* to cut false wakes, which taught it
  to reject exactly how a five-year-old pronounces the word. The Hey Skelly
  config drops those sound-alikes.
- **Synthetic voices are all adults.** Child-pitched copies (+3 to +6
  semitones) and ~20 real takes per family member made the difference.
  Recording tip: one long voice memo per person, saying the phrase ~30 times
  with pauses, varying loudness and distance; cut it into clips with ~0.25 s
  of padding, then add ±1 semitone, ±10% speed and a child-pitched variant.
- **Tune without retraining.** Sensitivity is a probability cutoff. This build
  exposes `Hello Skelly threshold` and `Hey Skelly threshold` numbers in Home
  Assistant (applied at boot) — lower wakes more easily, higher means fewer
  false wakes. The stock "Wake word sensitivity" select only affects the
  built-in models.
