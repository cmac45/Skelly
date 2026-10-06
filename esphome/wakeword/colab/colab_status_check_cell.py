# Paste into a NEW cell and run it after re-running the CONFIGURE cell.
# Restores what a Python restart wipes (working folder, microWakeWord import
# path) and reports which steps' files survived, so you know where to resume.
import os, sys
os.chdir('/content')
if '/content/microWakeWord' not in sys.path:
    sys.path.insert(0, '/content/microWakeWord')

def count(path):
    if not os.path.isdir(path):
        return 'MISSING'
    return f'{sum(1 for _ in os.scandir(path))} items'

print('OUTPUT_NAME =', globals().get('OUTPUT_NAME', 'NOT SET -- run the CONFIGURE cell first'))
for step, path in [
    ('install',            'microWakeWord'),
    ('wake word samples',  'generated_samples'),
    ('sound-alikes',       'confusable_negatives'),
    ('negatives',          'negative_datasets/speech'),
    ('negatives',          'negative_datasets/dinner_party'),
    ('negatives',          'negative_datasets/no_speech'),
    ('negatives',          'negative_datasets/dinner_party_eval'),
    ('room echo',          'mit_rirs'),
    ('music background',   'fma_16k'),
    ('sound background',   'audioset_16k'),
    ('features',           'generated_augmented_features/training/wakeword_mmap'),
    ('sound-alike feats',  'confusable_features/training/wakeword_mmap'),
]:
    print(f'{step:18} {path:52} {count(path)}')
