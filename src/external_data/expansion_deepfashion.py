"""Larger nested official CLIP benchmark with category errors and attribute AP."""
from collections.abc import Sequence
import hashlib,io,json,time
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import yaml
from PIL import Image
from sklearn.metrics import average_precision_score
from src.common.artifacts import file_hash,fingerprint,write_json
from src.common.config import load_config
from src.external_data.expansion_common import plan
from src.external_data.deepfashion import PREFIX,annotation_rows
from src.external_data.io import member_text
from src.search.encoder import CLIPEncoder


def nested_selection(partitions: Sequence[Sequence[str]], old: dict[str, list[str]], limits: dict[str, int], seed: int) -> dict[str, list[str]]:
    rng=np.random.default_rng(seed);selected={}
    for split,limit in limits.items():
        prefix=old[split]
        pool=np.array(sorted({name for name,part in partitions if part==split}-set(prefix)))
        selected[split]=prefix+sorted(rng.choice(pool,limit-len(prefix),replace=False).tolist())
    return selected


def retrieval(scores: np.ndarray, labels: np.ndarray, truth: int, duplicate: np.ndarray) -> tuple[float, float, int]:
    allowed=np.flatnonzero(~duplicate);order=allowed[np.argsort(-scores[allowed],kind='stable')[:10]]
    hits=labels[order]==truth;positions=np.flatnonzero(hits)
    relevant=int((labels[allowed]==truth).sum())
    mrr=1/(positions[0]+1) if len(positions) else 0.
    ideal=(1/np.log2(np.arange(2,min(relevant,10)+2))).sum()
    ndcg=float((hits/np.log2(np.arange(2,len(order)+2))).sum()/ideal) if ideal else 0.
    return float(mrr),ndcg,relevant


def attribute_archive(source: Path, configured: str | None = None) -> Path:
    if configured is not None:
        return source / configured
    members = {PREFIX + 'Anno_coarse/list_attr_cloth.txt', PREFIX + 'Anno_coarse/list_attr_img.txt'}
    matches = []
    for path in source.glob('*.zip'):
        with ZipFile(path) as archive:
            if members.issubset(archive.namelist()):
                matches.append(path)
    if len(matches) != 1:
        raise ValueError('set deepfashion.attributes_archive to the ZIP containing the two attribute annotations')
    return matches[0]


def run() -> None:
    spec,work,results=plan();source=Path(spec['source_dir']);local=work/'deepfashion';local.mkdir(exist_ok=True)
    oldspec=yaml.safe_load(Path('config/external_data.yaml').read_text())['deepfashion']
    old=json.loads((Path(spec['source_work'])/'deepfashion/selection.json').read_text())
    label_text=member_text(source/oldspec['categories_archive'],PREFIX+'Anno_coarse/list_category_img.txt')
    split_text=member_text(source/oldspec['partitions_archive'],PREFIX+'Eval/list_eval_partition.txt')
    class_text=member_text(source/oldspec['classes_archive'],PREFIX+'Anno_coarse/list_category_cloth.txt')
    labels={name:int(label)-1 for name,label in annotation_rows(label_text)};partitions=annotation_rows(split_text)
    classes=[' '.join(row[:-1]).replace('_',' ') for row in annotation_rows(class_text)]
    selected=nested_selection(partitions,old['names'],{'train':spec['deepfashion']['gallery_images'],'val':spec['deepfashion']['queries_per_split'],'test':spec['deepfashion']['queries_per_split']},spec['seed'])
    cfg=load_config();cfg['search'].update(batch_size=spec['clip_batch_size'],torch_threads=spec['clip_threads']);encoder=CLIPEncoder(cfg)
    identity=fingerprint(dict(selection=selected,model=encoder.metadata))
    marker=local/'progress.json';state=json.loads(marker.read_text()) if marker.exists() else dict(identity=identity,counts=dict(train=0,val=0,test=0),hashes={k:[] for k in selected})
    if state['identity']!=identity:raise ValueError('changed DeepFashion checkpoint')
    arrays={};started=time.perf_counter()
    with ZipFile(source/oldspec['images_archive']) as z:
        for split,names in selected.items():
            path=local/f'{split}.npy';arrays[split]=np.lib.format.open_memmap(path,mode='r+' if path.exists() else 'w+',dtype=np.float32,shape=(len(names),encoder.dim))
            for start in range(state['counts'][split],len(names),spec['clip_batch_size']):
                batch=names[start:start+spec['clip_batch_size']];images=[];hashes=[]
                try:
                    for name in batch:
                        raw=z.read(name);hashes.append(hashlib.sha256(raw).hexdigest())
                        with Image.open(io.BytesIO(raw)) as image:images.append(image.convert('RGB').copy())
                    arrays[split][start:start+len(batch)]=encoder.encode_images(images)
                finally:
                    for image in images:image.close()
                state['hashes'][split].extend(hashes);state['counts'][split]=start+len(batch)
                if state['counts'][split]%1024==0 or state['counts'][split]==len(names):
                    arrays[split].flush();write_json(marker,state);print('DeepFashion',split,state['counts'][split],flush=True)
    class_vectors=encoder.encode_texts([f'a photo of a {name}' for name in classes])
    attr_archive = attribute_archive(source, spec['deepfashion'].get('attributes_archive'))
    attribute_text=member_text(attr_archive,PREFIX+'Anno_coarse/list_attr_cloth.txt')
    attributes=[' '.join(r[:-1]).replace('_',' ') for r in annotation_rows(attribute_text)]
    attribute_vectors=encoder.encode_texts([f'a photo of clothing with {name}' for name in attributes])
    attr_labels={};wanted=set(selected['val']+selected['test'])
    with ZipFile(attr_archive) as z,z.open(PREFIX+'Anno_coarse/list_attr_img.txt') as incoming:
        declared=int(incoming.readline());incoming.readline();seen=0
        for raw in incoming:
            name,label_text_row=raw.decode().split(maxsplit=1);seen+=1
            if name in wanted:
                values=np.fromstring(label_text_row,sep=' ',dtype=np.int8)
                if len(values)!=len(attributes) or not np.isin(values,[-1,0,1]).all():raise ValueError('invalid attribute labels')
                attr_labels[name]=values
        assert seen==declared and set(attr_labels)==wanted
    gallery_labels=np.array([labels[n] for n in selected['train']]);gallery_hashes=np.array(state['hashes']['train'])
    majority=np.bincount([labels[n] for n,part in partitions if part=='train']).argmax();measured={}
    for split in ['val','test']:
        truth=np.array([labels[n] for n in selected[split]]);scores=arrays[split]@class_vectors.T
        order=np.argsort(-scores,axis=1,kind='stable');pred=order[:,0];correct=pred==truth
        confusion: list[dict] = []
        for a in range(len(classes)):
            for b in range(len(classes)):
                count=int(((truth==a)&(pred==b)).sum())
                if a!=b and count:confusion.append(dict(actual=classes[a],predicted=classes[b],count=count))
        retrieval_values=[];duplicates=0
        for start in range(0,len(truth),128):
            image_scores=arrays[split][start:start+128]@arrays['train'].T
            for j,row in enumerate(image_scores):
                i=start+j;dup=gallery_hashes==state['hashes'][split][i];duplicates+=int(dup.sum())
                retrieval_values.append(retrieval(row,gallery_labels,truth[i],dup))
        gold=np.stack([attr_labels[n] for n in selected[split]]);attribute_scores=arrays[split]@attribute_vectors.T
        aps: list[dict] = []
        for j,name in enumerate(attributes):
            valid=gold[:,j]!=0;y=gold[valid,j]==1;positive=int(y.sum())
            if positive and positive<len(y):
                aps.append(dict(attribute=name,positives=positive,negatives=len(y)-positive,ap=float(average_precision_score(y,attribute_scores[valid,j])),constant_score_ap=float(y.mean())))
        measured[split]=dict(queries=len(truth),zero_shot_top1=float(correct.mean()),zero_shot_top5=float((order[:,:5]==truth[:,None]).any(axis=1).mean()),
            majority_accuracy=float((truth==majority).mean()),original_query_subset_top1=float(correct[:len(old['names'][split])].mean()),
            macro_category_accuracy=float(np.mean([correct[truth==i].mean() for i in np.unique(truth)])),
            per_category=[dict(category=classes[i],queries=int((truth==i).sum()),accuracy=float(correct[truth==i].mean())) for i in np.unique(truth)],
            confusions=sorted(confusion,key=lambda x:-x['count'])[:20],
            image_category_mrr_at_10=float(np.mean([v[0] for v in retrieval_values])),image_category_ndcg_at_10=float(np.mean([v[1] for v in retrieval_values])),
            no_relevant_gallery_queries=sum(v[2]==0 for v in retrieval_values),exact_duplicate_pairs_excluded=duplicates,
            attribute_macro_ap=float(np.mean([a['ap'] for a in aps])),attribute_constant_macro_ap=float(np.mean([a['constant_score_ap'] for a in aps])),
            evaluated_attributes=len(aps),attributes=aps)
    write_json(local/'selection.json',dict(names=selected,hashes=state['hashes']))
    write_json(results/'deepfashion_expanded.json',dict(status='PASS',acceptance='UNMEASURED',counts=state['counts'],metrics=measured,
        model=encoder.metadata,selection_fingerprint=fingerprint(selected),source_image_sha256=file_hash(source/oldspec['images_archive']),
        attribute_source_sha256=file_hash(attr_archive),embedding_hashes={str(local/f'{k}.npy'):file_hash(local/f'{k}.npy') for k in arrays},
        seconds_this_invocation=time.perf_counter()-started,
        scope='nested 10k gallery and 5k per official heldout split; frozen CLIP; 50 category and 1000 attribute prompts fixed before evaluation',
        limitations=['category/attribute semantics, not same-product identity','near-duplicate images not audited','attribute labels may be incomplete; unknown 0 excluded','no model fine-tuning or test-selected prompts']))
    print('Expanded DeepFashion complete',flush=True)

if __name__=='__main__':run()
