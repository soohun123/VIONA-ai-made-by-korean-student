"""Import the user's linked unrestricted public stroller dataset, preserving provenance."""
import hashlib,io,json,urllib.request,zipfile
from pathlib import Path
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parent
URL='https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003514095&fileDetailSn=1&insertDataPrcus=N'
DEST=ROOT/'data/training/datasets/daejeon-strollers'
DEST.mkdir(parents=True,exist_ok=True)
archive=DEST/'source.zip'
if not archive.exists():
    temporary=DEST/'source.zip.download'
    with urllib.request.urlopen(URL,timeout=60) as response,temporary.open('wb') as output:
        count=0
        while block:=response.read(1024*1024):
            count+=len(block)
            if count>512*1024**2:raise RuntimeError('Dataset download exceeds 512MiB cap')
            output.write(block)
    temporary.replace(archive)
manifest=DEST/'dataset.json'
if manifest.exists():raise SystemExit('Dataset already imported; existing records preserved.')
records=[]
with zipfile.ZipFile(archive) as z:
    members=[f for f in z.infolist() if not f.is_dir() and Path(f.filename).suffix.lower() in ('.jpg','.jpeg','.png','.webp')]
    if len(members)>500 or sum(f.file_size for f in members)>600*1024**2:raise RuntimeError('Dataset extraction cap exceeded')
    for index,f in enumerate(sorted(members,key=lambda x:x.filename)):
        if f.file_size>10*1024**2:continue
        raw=z.read(f);digest=hashlib.sha256(raw).hexdigest();target=DEST/(digest[:24]+'.png')
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height>16000000:continue
            normalized=ImageOps.exif_transpose(im).convert('RGB');normalized.thumbnail((512,512));normalized.info.clear()
            if not target.exists():normalized.save(target)
        records.append({'image':target.name,'caption':'a photograph of a stroller, baby carriage with wheels','sha256':digest,'split':'validation' if index%10==0 else 'train'})
    del raw
data={'id':'daejeon-strollers','name':'대전광역시 서구 유모차 사진','source':'https://www.data.go.kr/data/15151337/fileData.do','discovery':'https://data.edmgr.kr/dataView.do?id=www-data-go-kr-data-filedata-15151337','license':'이용허락범위 제한 없음 (제공기관 원문 확인); 교육 포털 cc-zero 표기','source_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'caption_method':'dataset-level English caption; YOLO boxes are not text captions','records':records}
manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('IMPORTED',len(records),'train',sum(x['split']=='train' for x in records),'validation',sum(x['split']=='validation' for x in records),flush=True)
