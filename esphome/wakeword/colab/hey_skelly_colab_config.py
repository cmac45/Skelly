# Paste over the "CONFIGURE YOUR WAKE WORD HERE" cell (same notebook as Hello Skelly).
# Output: hey_skelly.tflite + hey_skelly.json in Google Drive/wakeword_training_hey_skelly/
# Runs ALONGSIDE Hello Skelly on the device (second wake-word slot), not instead of it.

# ─── Wake word identity ───
WAKE_WORD = "Hey Skelly"
OUTPUT_NAME = "hey_skelly"
AUTHOR = "cmac"
AUTHOR_WEBSITE = "https://github.com/"

# ─── Mode ───
MODE = "generate"

# ─── Drive folder (created if missing) ───
DRIVE_FOLDER = "wakeword_training_hey_skelly"

# ─── If MODE == "generate" ───
WAKE_WORD_IPA_US = "hˈeɪ skˈɛli"
WAKE_WORD_IPA_UK = "hˈeɪ skˈɛli"
SAMPLES_US = 30000
SAMPLES_UK = 15000

# Confusable phrases -- should NOT trigger the wake word.
# NO Skelly sound-alikes this time (Kelly/Shelly/Telly/Sally): young kids say
# "Skelly" exactly like those, and the Hello Skelly model learned to reject them.
CONFUSABLE_PHRASES = [
    "hey", "hey there", "hey you", "hey now", "hey guys", "okay",
    "hey siri", "hey google", "okay google", "hey alexa", "okay nabu",
    "skelly", "skeleton",
]
SAMPLES_PER_CONFUSABLE = 1000

# ─── If MODE == "bundle" ───
BUNDLE_NAME = "data_bundle.zip"

# ─── Manifest tuning (tune after on-device testing; no retrain needed) ───
PROBABILITY_CUTOFF = 0.7
SLIDING_WINDOW_SIZE = 5
TENSOR_ARENA_SIZE = 50000

# ─── Languages this model is trained for (manifest metadata) ───
TRAINED_LANGUAGES = ["en"]

print(f"Training '{WAKE_WORD}' as {OUTPUT_NAME} in mode={MODE!r}")
print(f"Output → /content/drive/MyDrive/{DRIVE_FOLDER}/{OUTPUT_NAME}.tflite")
