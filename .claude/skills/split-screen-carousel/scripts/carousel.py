#!/usr/bin/env python3
"""Scout real video frames and render the saved two-panel carousel style."""
import argparse
import hashlib
import html
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

FONT_PATH = '/System/Library/Fonts/HelveticaNeue.ttc'
TRACKING = -1.2


def ffmpeg_path(explicit):
    candidate = explicit or shutil.which('ffmpeg')
    if not candidate:
        try:
            import imageio_ffmpeg
            candidate = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass
    if not candidate:
        raise ValueError('FFmpeg unavailable. Pass --ffmpeg /absolute/path/to/ffmpeg.')
    return str(candidate)


def font_path(explicit, index):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        idx = index if index is not None else 0
    elif Path(FONT_PATH).is_file():
        path, idx = Path(FONT_PATH), 1 if index is None else index
    else:
        raise ValueError('Helvetica Neue unavailable. Select a bold sans-serif with --font and disclose the substitution.')
    font = ImageFont.truetype(str(path), 60, index=idx)
    return font, path, idx


def frame(source, seconds, ffmpeg, cache):
    t = float(seconds)
    if not math.isfinite(t) or t < 0:
        raise ValueError(f'Invalid source time: {seconds}')
    stat = source.stat()
    key = hashlib.sha256(f'{source}|{stat.st_size}|{stat.st_mtime_ns}|{t:.9f}'.encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f'{key}.png'
    if not path.exists():
        result = subprocess.run([ffmpeg, '-v', 'error', '-ss', str(t), '-i', str(source),
                                 '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                                capture_output=True)
        if result.returncode or not result.stdout:
            raise ValueError(f'Cannot extract {t}s: {result.stderr.decode(errors="replace")[-1200:]}')
        with Image.open(io.BytesIO(result.stdout)) as im:
            im.convert('RGB').save(path)
    with Image.open(path) as im:
        return im.convert('RGB')


def crop_image(im, crop, require_panel=True):
    if not isinstance(crop, list) or len(crop) != 4 or any(type(v) is not int for v in crop):
        raise ValueError('Crop must be four integers: [left, top, width, height].')
    x, y, w, h = crop
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > im.width or y+h > im.height:
        raise ValueError(f'Crop {crop} falls outside the oriented source {im.size}.')
    if require_panel and w * 2 != h * 3:
        raise ValueError(f'Crop {crop} must have a 3:2 width:height ratio; do not stretch the image.')
    return im.crop((x, y, x+w, y+h))


def text_width(font, text):
    return sum(font.getlength(c) for c in text) + TRACKING * max(0, len(text)-1)


def check_text(font, text):
    if not isinstance(text, str):
        raise ValueError('Panel text must be a string.')
    lines = text.split('\n')
    if not 1 <= len(lines) <= 2 or any(not line.strip() for line in lines):
        raise ValueError(f'Use one or two nonempty lines: {text!r}')
    widths = [text_width(font, line) for line in lines]
    if max(widths) > 996:
        raise ValueError(f'Caption is {max(widths):.1f}px wide (maximum 996). Shorten or rebreak: {text!r}')
    return lines, widths


def text_line(draw, font, line, y, fill):
    x = (1080-text_width(font, line))/2
    for char in line:
        draw.text((x, y+44), char, font=font, fill=fill, anchor='ls')
        x += font.getlength(char) + TRACKING


def render_panel(photo, text, font, alpha):
    im = photo.resize((1080, 720), Image.Resampling.LANCZOS).convert('RGBA')
    shade = Image.new('RGBA', im.size, (0,0,0,0))
    draw = ImageDraw.Draw(shade)
    for y in range(460,720):
        draw.line([(0,y),(1079,y)], fill=(0,0,0,round(alpha*((y-460)/259)**0.8)))
    im = Image.alpha_composite(im, shade)
    lines, widths = check_text(font, text)
    ys = [590] if len(lines)==1 else [556,624]
    shadow = Image.new('RGBA', im.size)
    draw = ImageDraw.Draw(shadow)
    for line,y in zip(lines,ys):
        text_line(draw,font,line,y+3,(0,0,0,230))
    im = Image.alpha_composite(im,shadow.filter(ImageFilter.GaussianBlur(3)))
    ink = Image.new('RGBA',im.size)
    draw = ImageDraw.Draw(ink)
    for line,y in zip(lines,ys):
        text_line(draw,font,line,y,(255,255,255,255))
    return Image.alpha_composite(im,ink).convert('RGB'), widths


def overview(paths, dest, font):
    cols = min(4,len(paths)); rows = math.ceil(len(paths)/cols)
    sheet = Image.new('RGB',(24+cols*364,24+rows*522),(22,22,22))
    draw = ImageDraw.Draw(sheet)
    for i,path in enumerate(paths):
        x=24+(i%cols)*364; y=24+(i//cols)*522
        with Image.open(path) as im:
            sheet.paste(im.resize((340,453),Image.Resampling.LANCZOS),(x,y))
        draw.text((x,y+464),f'{i+1:02d}',font=font,fill='#cccccc')
    sheet.save(dest,quality=95)


def gallery(title, slides):
    escaped = html.escape(title)
    style = 'body{margin:0;background:#171717;color:#eee;font:16px Helvetica,Arial,sans-serif}header{max-width:1140px;margin:32px auto;padding:0 20px}h1{font-size:28px}p{color:#bbb;line-height:1.5}main{max-width:1140px;margin:auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;padding:0 20px 40px}figure{margin:0}img{width:100%;display:block}figcaption{padding:10px 0;color:#bbb}a{color:#fff}@media(max-width:700px){main{grid-template-columns:1fr}}'
    result = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escaped}</title><style>{style}</style><header><h1>{escaped}</h1><p>{len(slides)} slides · 1080 × 1440</p><p><a href="carousel.zip">Download all JPEGs</a> · <a href="slide-copy.txt">Slide copy</a> · <a href="frame-sources.json">Frame sources</a></p></header><main>'
    for i,slide in enumerate(slides,1):
        alt=html.escape((slide['top']['text']+' '+slide['bottom']['text']).replace('\n',' '),quote=True)
        result+=f'<figure><a href="slides/{i:02d}.jpg"><img src="slides/{i:02d}.jpg" alt="{alt}" loading="lazy"></a><figcaption>{i:02d} / {len(slides)}</figcaption></figure>'
    return result+'</main></html>'


def render(args):
    manifest_path = Path(args.manifest).expanduser().resolve()
    data = json.loads(manifest_path.read_text())
    source = Path(data['source']).expanduser()
    if not source.is_absolute():
        source = manifest_path.parent/source
    source = source.resolve(strict=True)
    slides = data['slides']
    if not isinstance(slides,list) or not slides:
        raise ValueError('Manifest needs a nonempty slides list.')
    if data.get('frame_match') not in ('exact','illustrative'):
        raise ValueError('Declare frame_match as exact or illustrative.')
    if not data.get('frame_note','').strip():
        raise ValueError('Provide an accurate frame_note.')
    alpha = data.get('shade_alpha',100)
    if type(alpha) is not int or not 0 <= alpha <= 255:
        raise ValueError('shade_alpha must be an integer from 0 to 255.')
    out = Path(args.out).expanduser().resolve()
    if out.exists():
        raise ValueError(f'Output already exists; use a new version directory: {out}')
    work = Path(args.work).expanduser().resolve()
    if out == work or out in work.parents:
        raise ValueError('The work directory must be outside the output directory.')
    font,fp,fi = font_path(args.font,args.font_index)
    small = ImageFont.truetype(str(fp),24,index=fi)
    for slide in slides:
        for which in ('top','bottom'):
            check_text(font,slide[which]['text'])
            if slide[which].get('crop',data.get('default_crop')) is None:
                raise ValueError('Select a source crop for every panel before rendering.')
    ffmpeg = ffmpeg_path(args.ffmpeg)
    work.mkdir(parents=True,exist_ok=True)
    seen = {}; warnings = []; panels = []; frame_slides = []
    copy = [data.get('title','Carousel'),f'{len(slides)} slides · 1080 × 1440','']
    with tempfile.TemporaryDirectory(prefix='carousel-',dir=work) as temp:
        stage = Path(temp); (stage/'slides').mkdir()
        for number,slide in enumerate(slides,1):
            output = Image.new('RGB',(1080,1440)); frame_slide={'slide':number}
            copy.append(f'SLIDE {number:02d}')
            for which,y in (('top',0),('bottom',720)):
                panel=slide[which]; t=float(panel['time'])
                crop=panel.get('crop',data.get('default_crop'))
                raw=frame(source,t,ffmpeg,work/'frame-cache')
                photo=crop_image(raw,crop)
                digest=hashlib.sha256(raw.tobytes()).hexdigest()
                label=f'{number:02d} {which}'
                if digest in seen:
                    warnings.append(f'{label} repeats the source frame used by {seen[digest]}.')
                seen[digest]=label
                rendered,widths=render_panel(photo,panel['text'],font,alpha)
                output.paste(rendered,(0,y))
                panels.append({'slide':number,'panel':which,'source_seconds':t,'crop':crop,
                               'line_widths':[round(w,2) for w in widths],'source_frame_sha256':digest})
                frame_slide[which]={'time':t,'crop':crop,'text':panel['text']}
                copy.append(which.upper()+': '+panel['text'].replace('\n',' '))
            frame_slides.append(frame_slide); copy.append('')
            output.save(stage/'slides'/f'{number:02d}.jpg',quality=97,subsampling=0)
        paths=sorted((stage/'slides').glob('*.jpg'))
        for path in paths:
            with Image.open(path) as im:
                if im.size != (1080,1440):
                    raise ValueError(f'Unexpected output dimensions: {path}')
                im.verify()
        with zipfile.ZipFile(stage/'carousel.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                archive.write(path,path.name)
        with zipfile.ZipFile(stage/'carousel.zip') as archive:
            if archive.testzip() or len(archive.namelist()) != len(slides):
                raise ValueError('ZIP integrity or count check failed.')
        overview(paths,stage/'preview.jpg',small)
        (stage/'index.html').write_text(gallery(data.get('title','Carousel'),slides))
        (stage/'slide-copy.txt').write_text('\n'.join(copy))
        provenance={'title':data.get('title','Carousel'),'source':str(source),
                    'frame_match':data['frame_match'],'frame_note':data['frame_note'],
                    'font':{'file':str(fp),'index':fi,'name':font.getname(),'size':60},
                    'shade_alpha':alpha,'slides':frame_slides}
        (stage/'frame-sources.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False))
        (stage/'qa.json').write_text(json.dumps({'size':[1080,1440],'slide_count':len(slides),
                                                'panels':panels,'warnings':warnings},indent=2))
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(stage,out)
    print(json.dumps({'output':str(out),'slides':len(slides),'font':font.getname(),
                      'warnings':warnings},ensure_ascii=False))


def scout(args):
    source=Path(args.source).expanduser().resolve(strict=True)
    times=[float(x.strip()) for x in args.times.split(',')]
    if not times or any(not math.isfinite(t) or t<0 for t in times):
        raise ValueError('Supply nonnegative comma-separated source times.')
    crop=[int(x.strip()) for x in args.crop.split(',')] if args.crop else None
    out=Path(args.out).expanduser().resolve()
    if out.exists():
        raise ValueError(f'Scout directory already exists: {out}')
    ffmpeg=ffmpeg_path(args.ffmpeg); out.mkdir(parents=True)
    thumbs=[]
    for number,t in enumerate(times,1):
        im=frame(source,t,ffmpeg,out/'frame-cache')
        if crop: im=crop_image(im,crop,require_panel=False)
        im.thumbnail((360,480),Image.Resampling.LANCZOS)
        im.save(out/f'{number:02d}-{t:g}s.jpg',quality=93); thumbs.append(im)
    cols=min(4,len(thumbs)); cell_w=384; cell_h=max(im.height for im in thumbs)+52
    sheet=Image.new('RGB',(cols*cell_w,math.ceil(len(thumbs)/cols)*cell_h),(22,22,22))
    draw=ImageDraw.Draw(sheet)
    try: font=ImageFont.load_default(size=20)
    except TypeError: font=ImageFont.load_default()
    for i,(im,t) in enumerate(zip(thumbs,times)):
        x=(i%cols)*cell_w+(cell_w-im.width)//2; y=(i//cols)*cell_h+12
        sheet.paste(im,(x,y)); draw.text((x,y+im.height+6),f'{i+1:02d} | {t:.2f}s',font=font,fill='white')
    sheet.save(out/'contact-sheet.jpg',quality=93)
    print(json.dumps({'contact_sheet':str(out/'contact-sheet.jpg'),'times':times}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('scout',help='Extract candidate thumbnails and a contact sheet.')
    p.add_argument('--source',required=True); p.add_argument('--times',required=True)
    p.add_argument('--out',required=True); p.add_argument('--crop'); p.add_argument('--ffmpeg')
    p=subs.add_parser('render',help='Render a reviewed JSON manifest into a finished carousel.')
    p.add_argument('--manifest',required=True); p.add_argument('--out',required=True)
    p.add_argument('--work',required=True); p.add_argument('--ffmpeg')
    p.add_argument('--font'); p.add_argument('--font-index',type=int)
    args=parser.parse_args()
    global Image,ImageDraw,ImageFont,ImageFilter
    try:
        from PIL import Image,ImageDraw,ImageFont,ImageFilter
    except ImportError:
        parser.error('Pillow is required. Run with the workspace Python or install Pillow into an isolated runtime.')
    try:
        (scout if args.command=='scout' else render)(args)
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(f'Error: {error}',file=sys.stderr); raise SystemExit(2)

if __name__=='__main__':
    main()
