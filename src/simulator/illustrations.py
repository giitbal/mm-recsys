"""Deterministic studio illustrations for the catalog and independent query renderer."""
from __future__ import annotations

from PIL import Image, ImageColor, ImageDraw

PAPER = '#f4f1ed'
Point = tuple[int, int]
Color = tuple[int, int, int]


def shade(base: Color, target: int, amount: float) -> Color:
    r, g, b = base
    return (round(r + (target - r) * amount), round(g + (target - g) * amount),
            round(b + (target - b) * amount))


class Fabric:
    def __init__(self, image: Image.Image, color: str):
        self.draw = ImageDraw.Draw(image)
        self.base = ImageColor.getrgb(color)[:3]
        self.edge = shade(self.base, 0, .38)
        self.light = shade(self.base, 255, .32)
        self.panel = shade(self.base, 245, .14)
        self.dark = shade(self.base, 0, .20)

    def piece(self, points: list[Point], fill: Color | None = None) -> None:
        self.draw.polygon(points, fill=fill or self.base)
        self.draw.line(points + points[:1], fill=self.edge, width=2, joint='curve')

    def seam(self, points: list[Point], width: int = 2) -> None:
        self.draw.line(points, fill=self.light, width=width, joint='curve')

    def pocket(self, x: int, y: int, w: int, h: int) -> None:
        self.draw.rounded_rectangle((x, y, x+w, y+h), radius=4, fill=self.panel, outline=self.edge, width=2)
        self.seam([(x+3, y+5), (x+w-3, y+5)])


def bag(f: Fabric, leaf: str, design: int) -> None:
    # Six cut patterns combined with four pocket / panel constructions.
    cut, trim = design % 6, design // 6
    width = (54, 44, 68, 59, 48, 64)[cut]
    x, r = 112-width, 112+width
    y = (93, 77, 108, 88, 98, 82)[cut]
    if leaf == 'backpack':
        y -= 21
        f.draw.arc((95, y-17, 129, y+17), 180, 360, fill=f.dark, width=6)
        f.draw.rounded_rectangle((x-4, y+24, r+4, 187), radius=20, fill=f.dark)
        f.draw.rounded_rectangle((x, y, r, 184), radius=18+cut*2, fill=f.base, outline=f.edge, width=2)
        f.draw.arc((x+6, y+6, r-6, y+78), 185, 355, fill=f.light, width=2)
    elif leaf == 'crossbody bag':
        y += 14
        f.draw.arc((x-3, 33+cut*3, r+4, 2*y-33-cut*3), 180, 360, fill=f.edge, width=6)
        f.draw.rounded_rectangle((x, y, r, 176), radius=10+cut*2, fill=f.base, outline=f.edge, width=2)
        f.piece([(x+1,y+4),(r-1,y+4),(r-8,y+26),(109,y+36),(x+7,y+27)], f.dark)
    else:
        inset = (9, 1, 17, -6, 12, -2)[cut]
        for offset in (-4, 3):
            f.draw.arc((90+offset, 31+cut*3, 135+offset, 2*y-31-cut*3), 180, 360,
                       fill=f.edge if offset < 0 else f.panel, width=6)
        f.piece([(x,y),(r,y),(r-inset,177),(r-inset-7,184),(x+inset+7,184),(x+inset,178)])
        f.seam([(x+4,y+6),(r-4,y+6)])
    if trim == 0:
        f.pocket(96, y+28, 32, 26)
    elif trim == 1:
        f.piece([(x+8,y+34),(r-8,y+44),(r-11,167),(x+11,158)], f.panel)
        f.seam([(x+12,y+38),(r-12,y+48)])
    elif trim == 2:
        for center in (x+22,r-22):
            f.draw.line([(center,y+5),(center,172)], fill=f.panel, width=8)
            f.seam([(center-2,y+8),(center-2,169)], 1)
    else:
        f.pocket(x+12, y+34, width-15, 24)
        f.pocket(115, y+34, width-15, 24)


def upper(f: Fabric, leaf: str, mid: str, cut: int, fit: int) -> None:
    w = 32 + fit*4 + cut%3*3
    hem = (177 if mid == 'coats' else 153) + cut%3*6
    vest = leaf in ('knitted vest', 'padded vest')
    sleeve = 96 if leaf in ('t-shirt','polo shirt') else 143
    x, r = 112-w, 112+w
    left = [(96,44),(79,50),(x-5,55),(x-22,sleeve),(x-7,sleeve+5),(x+4,88)]
    if vest:
        left = [(96,44),(82,48),(x+7,56),(x+8,73),(x,89)]
    f.piece(left + [(x,hem),(r,hem)] + [(224-a,b) for a,b in reversed(left)])
    f.seam([(x+3,hem-6),(r-3,hem-6)])
    if leaf == 'hoodie':
        f.piece([(82,53),(93,32),(112,27),(132,32),(142,53),(122,63),(103,63)], f.panel)
        for offset in (-7,7):
            f.seam([(112+offset,59),(113+offset,86)])
        f.piece([(94,hem-42),(130,hem-42),(140,hem-17),(84,hem-17)], f.panel)
    elif mid in ('shirts','coats','jackets') or leaf in ('cardigan','fleece jacket','padded vest'):
        f.seam([(112,54),(112,hem-2)])
        for s in (-1,1):
            f.piece([(112,57),(112+s*16,44),(112+s*24,56),(112+s*12,75)], f.panel)
        if leaf in ('blazer','pea coat','trench coat','long coat'):
            f.seam([(87,68),(107,96),(112,105)])
        for yy in range(86,hem-12,19):
            f.draw.ellipse((115,yy,118,yy+3),fill=f.light)
    else:
        f.draw.pieslice((94,32,130,61),0,180,fill=PAPER)
        f.draw.arc((93,33,131,64),0,180,fill=f.light,width=3)
    if leaf in ('puffer jacket','padded vest') or cut in (1,4):
        for yy in range(90,hem-10,13 if mid == 'warm' else 18):
            f.seam([(x+3,yy),(110,yy+3),(r-3,yy)])
    elif cut in (2,5) or leaf == 'denim jacket':
        f.pocket(x+7,82,19,18)
        if cut == 5:
            f.pocket(r-26,82,19,18)
    if leaf == 'trench coat':
        f.draw.rectangle((x+1,115,r-1,122),fill=f.dark)
        f.draw.rectangle((106,114,119,123),outline=f.light,width=2)


def bottom(f: Fabric, leaf: str, mid: str, cut: int, fit: int) -> None:
    w = 31 + fit*3
    end = (105+cut%3*7 if mid == 'shorts' or leaf == 'mini skirt' else 175+cut%3*4)
    if leaf == 'pleated skirt':
        end = 146+cut%3*8
    spread = 42 + cut%3*9 + fit*2
    x,r = 112-w,112+w
    if mid == 'skirts':
        f.piece([(x,47),(r,47),(112+spread,end),(112-spread,end)])
        for off in range(-24,25,12 if leaf == 'pleated skirt' else 24):
            f.seam([(112+off,56),(112+off*spread//w,end-4)],1)
    else:
        gap = 8+cut%3*3
        f.piece([(x,47),(r,47),(112+spread,end),(112+gap,end),(112,94),
                 (112-gap,end),(112-spread,end)])
        f.seam([(x+17,54),(x+12,67),(x+2,73)])
        f.seam([(r-17,54),(r-12,67),(r-2,73)])
        f.seam([(115,55),(115,77),(111,83)],1)
        if leaf == 'cargo pants' or cut >= 3:
            f.pocket(x-1,83,17,19)
    f.draw.rectangle((x,45,r,54), fill=f.dark,outline=f.edge)
    for xx in (x+9,r-10):
        f.seam([(xx,46),(xx,54)])


def shoe(f: Fabric, leaf: str, mid: str, cut: int) -> None:
    heel_x = 39+cut%3*6
    ankle = {'boots':56,'hiking shoes':90,'heels':99,'sandals':132}.get(leaf,105)
    toe = 149-cut%3*5
    f.piece([(heel_x,ankle),(heel_x+35,ankle-3),(86,109),(100,100),(121,123),
             (146,135),(177,toe-5),(185,toe+5),(181,158),(heel_x,158)])
    if leaf == 'heels':
        f.piece([(heel_x,150),(93,152),(158,154),(182,151),(180,160),(139,160),(78,143),
                 (heel_x+9,174),(heel_x+2,174)], f.dark)
        f.draw.polygon([(60,100),(99,95),(115,123),(91,115)],fill=PAPER)
    else:
        f.piece([(heel_x,149),(79,153),(145,154),(184,toe+5),(181,161),(148,166),(heel_x,163)], f.panel)
    if leaf == 'sandals':
        for xx in (79,111,139):
            f.draw.polygon([(xx,119),(xx+14,127),(xx+6,145),(xx-5,142)],fill=PAPER)
    elif leaf in ('loafers','slip-on shoes'):
        f.piece([(89,108),(111,115),(132,132),(121,137),(101,125)],f.panel)
    else:
        for i in range(3+cut%2):
            f.seam([(90+i*8,111+i*5),(102+i*8,106+i*5)],3)
    if cut >= 3 or mid == 'outdoor':
        f.seam([(heel_x+5,ankle+7),(heel_x+15,132),(77,145),(102,144)])
    f.seam([(143,143),(163,toe-3),(175,toe)],1)


def accessory(f: Fabric, leaf: str, cut: int) -> None:
    w = 45+cut%3*6
    if leaf in ('cap','beanie','bucket hat'):
        if leaf == 'bucket hat':
            crown = 61 + cut%3*5
            f.piece([(84,crown),(140,crown),(106+w,119),(118-w,119)])
            f.piece([(118-w,109),(106+w,109),(122+w,142),(148,147),(100-w,140)], f.panel)
            if cut >= 3:
                f.seam([(121-w,102),(103+w,102)],4)
        else:
            f.draw.pieslice((112-w,54-cut%3*5,112+w,188),180,360,fill=f.base,outline=f.edge,width=2)
            if leaf == 'cap':
                f.piece([(112-w,115),(141,112),(170,118),(183,127),(162,130),(122,124)], f.panel)
            else:
                f.draw.rounded_rectangle((109-w,113,115+w,139),radius=7,fill=f.panel,outline=f.edge,width=2)
                for xx in range(118-w,110+w,7):
                    f.seam([(xx,117),(xx,135)],1)
            f.seam([(108,60),(98,75),(92,94),(91,112)])
    elif leaf == 'belt':
        f.draw.ellipse((35,83,185,139),outline=f.base,width=10+cut)
        f.draw.rounded_rectangle((83,115,119,139),radius=4,outline=f.light,width=5)
        for xx in (129,138,147):
            f.draw.ellipse((xx,126,xx+2,128),fill=f.edge)
    elif leaf == 'gloves':
        for dx,dy in ((0,15),(65,-7)):
            outline=[(56,149),(51,120),(39,101),(43,96),(56,108),(53,77),(59,74),
                     (66,99),(63,64),(69,62),(76,97),(74,59),(81,60),(87,97),(87,70),
                     (93,72),(99,112),(95,147)]
            f.piece([(a+dx,b+dy) for a,b in outline])
            f.seam([(58+dx,139+dy),(93+dx,136+dy)],3+cut%3)
    else:
        f.piece([(65,57),(94,47),(157,168),(131,181)])
        f.piece([(120,48),(153,62),(91,184),(62,170)],f.panel)
        for i in range(4):
            f.seam([(69+i*5,167+i*2),(65+i*5,178+i*2)])
        for yy in range(74,148,18+cut):
            xx=141-(yy-60)//2
            f.seam([(xx-15,yy),(xx+7,yy+11)],3)


def illustration(row: dict, cfg: dict, variant: int) -> Image.Image:
    image = Image.new('RGB', (224,224), PAPER)
    f = Fabric(image, cfg['simulator']['colors'][row['color']])
    leaf, mid, kind = row['category_l3'], row['category_l2'], row['category_l1']
    fit = {'slim':0,'regular':1,'relaxed':2,'oversized':3}.get(row['style'],1)
    cut = variant % 6
    if mid == 'bags':
        bag(f, leaf, variant % 24)
    elif kind in ('tops','outerwear'):
        upper(f, leaf, mid, cut, fit)
    elif kind == 'bottoms':
        bottom(f, leaf, mid, cut, fit)
    elif kind == 'footwear':
        shoe(f, leaf, mid, cut)
    else:
        accessory(f, leaf, cut)
    size = cfg['simulator']['image_size']
    return image if size == 224 else image.resize((size,size), Image.Resampling.LANCZOS)
