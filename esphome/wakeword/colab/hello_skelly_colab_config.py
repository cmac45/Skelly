# Paste over the "CONFIGURE YOUR WAKE WORD HERE" cell of
# https://colab.research.google.com/github/alfiedennen/microwakeword-trainer/blob/main/notebooks/microWakeWord_train_any_wakeword.ipynb
# Output: hello_skelly.tflite + hello_skelly.json in Google Drive/wakeword_training_hello_skelly/
# -> copy both into esphome/wakeword/ and Claude wires them into skelly-voice.yaml.

# ─── Wake word identity ───
WAKE_WORD = "Hello Skelly"
OUTPUT_NAME = "hello_skelly"
AUTHOR = "cmac"
AUTHOR_WEBSITE = "https://github.com/"

# ─── Mode ───
MODE = "generate"

# ─── Drive folder (created if missing) ───
DRIVE_FOLDER = "wakeword_training_hello_skelly"

# ─── If MODE == "generate" ───
WAKE_WORD_IPA_US = "həlˈoʊ skˈɛli"
WAKE_WORD_IPA_UK = "həlˈəʊ skˈɛli"
SAMPLES_US = 30000
SAMPLES_UK = 15000

# Confusable phrases -- should NOT trigger the wake word.
# "skelly" alone matters most: Skelly says his own name out loud, and
# visitors will say it mid-conversation.
CONFUSABLE_PHRASES = [
    # General "hello X" near-misses
    "hello", "hello there", "hello everyone", "oh hello",
    # Other assistant wake words
    "hey siri", "hey google", "okay google", "hey alexa", "okay nabu",
    # Bare name and sound-alikes
    "skelly", "hey skelly", "kelly", "hello kelly", "hello shelly",
    "hello sally", "hello smelly", "jelly", "hello telly", "yellow belly",
]
SAMPLES_PER_CONFUSABLE = 1000

# ─── If MODE == "bundle" ───
BUNDLE_NAME = "data_bundle.zip"

# ─── Manifest tuning (tune after on-device testing; no retrain needed) ───
PROBABILITY_CUTOFF = 0.85
SLIDING_WINDOW_SIZE = 5
TENSOR_ARENA_SIZE = 50000

# ─── Languages this model is trained for (manifest metadata) ───
TRAINED_LANGUAGES = ["en"]

print(f"Training '{WAKE_WORD}' as {OUTPUT_NAME} in mode={MODE!r}")
print(f"Output → /content/drive/MyDrive/{DRIVE_FOLDER}/{OUTPUT_NAME}.tflite")
