"""Resumable frozen CLIP features for the entire H&M catalog, retaining missing images."""
from pathlib import Path
from zipfile import ZipFile
import hashlib,io,json,time
import numpy as np
from PIL import Image
from src.common.artifacts import file_hash,fingerprint,write_json
from src.common.config import load_config
from src.external_data.expansion_common import plan
from src.recommendation.datasets import read_data
from src.search.encoder import CLIPEncoder


def run():
    spec,work,results=plan(); root=work/'hm_embeddings';root.mkdir(exist_ok=True)
    products=read_data(Path(spec['source_work'])/'hm')['products'].sort_values('product_id').reset_index(drop=True)
    cfg=load_config();cfg['search'].update(batch_size=spec['clip_batch_size'],torch_threads=spec['clip_threads'])
    encoder=CLIPEncoder(cfg)
    ids=['<PAD>']+products.product_id.tolist()
    identity=fingerprint(dict(ids=ids,model=encoder.metadata,source=file_hash(Path(spec['source_work'])/'hm/products.parquet')))
    marker=root/'progress.json'
    state=json.loads(marker.read_text()) if marker.exists() else dict(identity=identity,text=0,image=0,missing=0)
    if state['identity']!=identity:raise ValueError('CLIP cache identity changed')
    arrays={}
    for mode in ['text','image']:
        path=root/f'{mode}.npy'
        arrays[mode]=np.lib.format.open_memmap(path,mode='r+' if path.exists() else 'w+',dtype=np.float32,shape=(len(ids),encoder.dim))
        arrays[mode][0]=0
    batch=spec['clip_batch_size'];started=time.perf_counter()
    texts=(products.name.fillna('')+'. '+products.description_en.fillna('')).tolist()
    text_cache={texts[i]:arrays['text'][i+1].copy() for i in range(state['text'])}
    for start in range(state['text'],len(products),batch):
        frame=products.iloc[start:start+batch]
        batch_text=texts[start:start+len(frame)]
        missing=list(dict.fromkeys(t for t in batch_text if t not in text_cache))
        if missing:text_cache.update(zip(missing,encoder.encode_texts(missing)))
        values=np.stack([text_cache[t] for t in batch_text])
        arrays['text'][start+1:start+1+len(frame)]=values
        state['text']=start+len(frame)
        if state['text']%2048==0 or state['text']==len(products):
            arrays['text'].flush();write_json(marker,state);print('H&M text',state['text'],'/',len(products),flush=True)
    archive=Path(spec['source_dir'])/'h-and-m-personalized-fashion-recommendations.zip'
    with ZipFile(archive) as z:
        names=set(z.namelist())
        for start in range(state['image'],len(products),batch):
            frame=products.iloc[start:start+batch];images=[];positions=[]
            try:
                arrays['image'][start+1:start+1+len(frame)]=0
                for i,row in frame.iterrows():
                    if row.image_path not in names:state['missing']+=1;continue
                    with Image.open(io.BytesIO(z.read(row.image_path))) as image:images.append(image.convert('RGB').copy())
                    positions.append(int(i)+1)
                if images:arrays['image'][positions]=encoder.encode_images(images)
            finally:
                for image in images:image.close()
            state['image']=start+len(frame)
            if state['image']%1024==0 or state['image']==len(products):
                arrays['image'].flush();write_json(marker,state);print('H&M image',state['image'],'/',len(products),flush=True)
    for value in arrays.values():value.flush()
    write_json(root/'ids.json',ids)
    write_json(results/'hm_embeddings.json',dict(status='PASS',acceptance='UNMEASURED',identity=identity,
        products=len(products),missing_images=state['missing'],model=encoder.metadata,
        hashes={str(root/f'{name}.npy'):file_hash(root/f'{name}.npy') for name in arrays},
        ids_sha256=file_hash(root/'ids.json'),seconds_this_invocation=time.perf_counter()-started,
        scope='all catalog texts and all available source images; frozen CLIP; zero image vector for missing images; no product excluded'))

if __name__=='__main__':run()
