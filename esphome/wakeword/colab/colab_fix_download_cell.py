# REPLACEMENT for the notebook cell that starts with
#   "# === Download standard negative datasets (DNS challenge, AudioSet, MIT IRs) ==="
# The original links broke: kahrendt/microwakeword now ships ZIPs (no fma_16k.tar,
# no speech/ folders) and agkphysics/AudioSet moved from .tar to .parquet.
# Safe to re-run: every step skips work that is already done.
import os, glob, subprocess, zipfile
from concurrent.futures import ThreadPoolExecutor
from huggingface_hub import hf_hub_download

def to_16k_wav(src, dst):
    if os.path.exists(dst):
        return
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', src,
                    '-ac', '1', '-ar', '16000', '-sample_fmt', 's16', dst])

# 1) Negative spectrogram features (speech, dinner party, no speech, eval)
os.makedirs('negative_datasets', exist_ok=True)
for name in ['speech', 'dinner_party', 'no_speech', 'dinner_party_eval']:
    if os.path.isdir(f'negative_datasets/{name}') and os.listdir(f'negative_datasets/{name}'):
        print(f'{name}: ready'); continue
    print(f'Downloading {name}.zip ...')
    z = hf_hub_download('kahrendt/microwakeword', f'{name}.zip', repo_type='dataset',
                        local_dir='/content/hf_zips')
    with zipfile.ZipFile(z) as zf:
        zf.extractall('negative_datasets')
    os.remove(z)
    print(f'{name}: ready' if os.path.isdir(f'negative_datasets/{name}')
          else f'!! {name}.zip did not unpack to negative_datasets/{name} -- tell Claude: '
               + str(os.listdir('negative_datasets')))

# 2) MIT room impulse responses (reverb augmentation) -- unchanged, link still works
if not os.path.exists('mit_rirs') or not os.listdir('mit_rirs'):
    print('Downloading MIT room impulse responses...')
    subprocess.run('mkdir -p mit_rirs && cd mit_rirs && wget -q https://www.openslr.org/resources/28/rirs_noises.zip && unzip -q rirs_noises.zip',
                   shell=True, check=True)

# 3) FMA background music, converted to 16 kHz wav
if not os.path.exists('fma_16k') or not os.listdir('fma_16k'):
    print('Downloading FMA background corpus...')
    z = hf_hub_download('mchl914/fma_xsmall', 'fma_xs.zip', repo_type='dataset',
                        local_dir='/content/fma')
    with zipfile.ZipFile(z) as zf:
        zf.extractall('/content/fma')
    mp3s = glob.glob('/content/fma/**/*.mp3', recursive=True)
    os.makedirs('fma_16k', exist_ok=True)
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(lambda p: to_16k_wav(p, f'fma_16k/{os.path.basename(p)[:-4]}.wav'), mp3s))
    print(f'fma_16k: {len(os.listdir("fma_16k"))} clips')

# 4) AudioSet background sounds: one parquet shard (~690 MB), 16 kHz wav
if not os.path.exists('audioset_16k') or not os.listdir('audioset_16k'):
    import pyarrow.parquet as pq
    print('Downloading AudioSet background corpus (1 shard)...')
    pqf = hf_hub_download('agkphysics/AudioSet', 'data/bal_train/00.parquet',
                          repo_type='dataset', local_dir='/content/audioset')
    os.makedirs('/content/audioset/raw', exist_ok=True)
    os.makedirs('audioset_16k', exist_ok=True)
    jobs = []
    for row in pq.read_table(pqf, columns=['video_id', 'audio']).to_pylist():
        if not row['audio'] or not row['audio'].get('bytes'):
            continue
        ext = os.path.splitext(row['audio'].get('path') or '.flac')[1] or '.flac'
        raw = f"/content/audioset/raw/{row['video_id']}{ext}"
        with open(raw, 'wb') as f:
            f.write(row['audio']['bytes'])
        jobs.append((raw, f"audioset_16k/{row['video_id']}.wav"))
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(lambda j: to_16k_wav(*j), jobs))
    print(f'audioset_16k: {len(os.listdir("audioset_16k"))} clips')

print('All negative datasets ready')
