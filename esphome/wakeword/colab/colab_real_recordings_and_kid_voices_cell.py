# NEW CELL -- insert it right ABOVE "# === Augmentation + feature extraction ===".
# 1) Brings in the family's real "Hey Skelly" takes (real_recordings.zip, uploaded
#    to the Drive folder). The notebook trains on /content/real_recordings with
#    extra weight automatically.
# 2) Adds child-pitched copies of a third of the synthetic samples, because the
#    synthetic voices are all adults and young kids failed to wake Hello Skelly.
import os, glob, random, zipfile, subprocess
from concurrent.futures import ThreadPoolExecutor
os.chdir('/content')

zip_path = f'/content/drive/MyDrive/{DRIVE_FOLDER}/real_recordings.zip'
assert os.path.exists(zip_path), f'Upload real_recordings.zip to {zip_path} first'
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall('/content')
print('real recordings:', len(glob.glob('/content/real_recordings/*.wav')))

def kid_copy(job):
    src, factor = job
    dst = src[:-4] + f'_kid{int(factor * 100)}.wav'
    if not os.path.exists(dst):
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', src, '-af',
                        f'asetrate=16000*{factor},aresample=16000,atempo={1 / factor:.4f}',
                        '-ac', '1', '-ar', '16000', '-sample_fmt', 's16', dst])

random.seed(42)
pool = [p for p in glob.glob('generated_samples/*.wav') if '_kid' not in p]
picked = random.sample(pool, len(pool) // 3)
# 1.19-1.41 = +3 to +6 semitones: roughly adult -> 9-year-old -> 5-year-old pitch
jobs = [(p, random.choice([1.19, 1.26, 1.33, 1.41])) for p in picked]
with ThreadPoolExecutor(16) as ex:
    list(ex.map(kid_copy, jobs))
print('positive samples now:', len(glob.glob('generated_samples/*.wav')))
