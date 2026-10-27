#!/usr/bin/env python3
"""Offline prop-play studies: Pokemon games and cute monster-inspired creatures.

24 keyed frames per loop. Native sprite art and all props occupy 40x32 pixels;
the right 24 Canvas columns are black. No firmware/sender selection is changed.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

try:
    from .companion_designs import quantized
except ImportError:
    from companion_designs import quantized

ROOT = Path(__file__).resolve().parents[1]
FRAMES = 24
MOODS = ("idle", "busy", "hard")
CASTS = {
    "pokemon-play": {"cubone": "#D4C599", "treecko": "#A2CE71", "torchic": "#E4AC59"},
    "monster-play": {"nibble": "#90ADCF", "nox": "#B398CE", "volt": "#B9D789"},
}


def keyed(frame, keys):
    """Linear interpolation between deliberately placed action beats."""
    if frame <= keys[0][0]:
        return keys[0][1:]
    for left, right in zip(keys, keys[1:]):
        if frame <= right[0]:
            t = (frame - left[0]) / (right[0] - left[0])
            return tuple(round(a + (b - a) * t) for a, b in zip(left[1:], right[1:]))
    return keys[-1][1:]


@lru_cache(maxsize=3)
def pokemon_base(name):
    with Image.open(ROOT / "tools/art/pokemon-icons" / (name + ".png")) as source:
        source = source.convert("RGBA")
        actor = source.crop(source.getchannel("A").getbbox())
    # Native pixels, with restrained intensity for the emissive matrix.
    channels = actor.split()
    actor = Image.merge("RGBA", (*[channel.point(lambda v: round(v * .82)) for channel in channels[:3]], channels[3]))
    if name == "cubone":
        ImageDraw.Draw(actor).rectangle((0, 11, 7, 18), fill=(0, 0, 0, 0))
    if name == "torchic":
        actor = ImageOps.mirror(actor)
    return actor


def put(image, actor, x, bottom, *, mirror=False, crouch=0):
    if mirror:
        actor = ImageOps.mirror(actor)
    if crouch:
        actor = actor.resize((actor.width, actor.height - crouch), Image.Resampling.NEAREST)
    if not (0 <= x <= 40 - actor.width and actor.height - 1 <= bottom < 32):
        raise ValueError("actor placement exceeds the 40x32 play area")
    image.paste(actor, (round(x), round(bottom) - actor.height + 1), actor)


def bone(draw, center, angle):
    dx, dy = round(3 * math.cos(angle)), round(3 * math.sin(angle))
    a, b = (center[0] - dx, center[1] - dy), (center[0] + dx, center[1] + dy)
    draw.line((a, b), fill="#B8B99E", width=2)
    for x, y in (a, b):
        for side in (-1, 1):
            px, py = x - round(math.sin(angle)) * side, y + round(math.cos(angle)) * side
            draw.ellipse((px - 1, py - 1, px + 1, py + 1), fill="#CBC9AC")


def berry(draw, x, y, color="#C5738D"):
    draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)
    draw.point((x - 1, y - 1), fill="#E2C2B4")
    draw.line(((x, y - 3), (x + 1, y - 2)), fill="#72A05B")


def pokemon_scene(name, f, mood):
    image = Image.new("RGB", (64, 32), "black")
    d = ImageDraw.Draw(image)
    active, hard = mood != "idle", mood == "hard"
    actor = pokemon_base(name)
    if name == "cubone":
        x, floor = (2, 29)
        if active:
            x, floor = keyed(f, [(0, 2, 29), (3, 1, 30), (5, 3, 29), (8, 3, 29),
                                  (10, 13, 28 if hard else 29), (13, 17, 30), (15, 17, 30),
                                  (18, 9, 28 if hard else 29), (21, 2, 29), (23, 2, 29)])
        put(image, actor, x, floor, crouch=1 if active and f in (2, 3, 13, 14) else 0)
        # Painted wood pins sit ahead of the character, rather than on its body.
        for index, px in enumerate((30, 33, 36)):
            fallen = active and 8 <= f <= 20 and (hard or index < 2)
            if fallen:
                d.line(((px - 1, 29), (px + 1, 30 - index % 2)), fill="#9B754B", width=2)
            else:
                d.rectangle((px, 24, px + 1, 29), fill="#815E3F")
                d.point((px, 24), fill="#CAA371")
                d.point((px + 1, 26), fill="#C2A58A")
        if not active:
            center, tilt = (x + 17, 23), -.5 + .12 * math.sin(f * math.tau / FRAMES)
        elif f <= 4:
            cx, cy = keyed(f, [(0, x + 17, 23), (3, x + 4, 19), (4, x + 18, 24)])
            center, tilt = (cx, cy), -1.2 if f in (2, 3) else .3
        elif f < 8:
            center = keyed(f, [(5, 23, 25), (7, 31, 27)])
            tilt = f * .8
        elif f <= 13:
            center, tilt = (34, 28), .1
        else:
            center, tilt = (x + 17, 25 if f < 17 else 23), -.3
        bone(d, center, tilt)
        if not active or f < 5 or f >= 14:
            d.line(((x + 13, floor - 5), (center[0] - 2, center[1])), fill="#AC8C5E")
        if active and 8 <= f <= 10:
            for px, py in ((29, 21), (34, 20), (37, 23)):
                d.point((px, py + f - 8), fill="#C7AF7A")
    elif name == "treecko":
        lean = keyed(f, [(0, 0), (5, -1), (11, 1), (17, -1), (23, 0)])[0] if active else 0
        floor = 30 - (1 if active and f % 6 < 2 else 0)
        put(image, actor, 8 + lean, floor)
        left, right = (10 + lean, 21), (27 + lean, 21)
        if not active:
            bx, by = keyed(f, [(0, 28, 18), (6, 29, 17), (12, 28, 18), (18, 27, 18), (23, 28, 18)])
            berry(d, bx, by, "#C0788D")
        else:
            beat = f % (8 if hard else 12)
            left = (left[0], 19 if beat in (1, 2) else 21)
            right = (right[0], 20 if beat in (5, 6) else 21)
            d.line(((16 + lean, 23), left), fill="#8CAF61", width=2)
            d.line(((20 + lean, 23), right), fill="#8CAF61", width=2)
            for hand in (left, right):
                d.line(((hand[0] - 1, hand[1]), (hand[0] + 1, hand[1])), fill="#B5D380")
            count = 3 if hard else 2
            for index in range(count):
                t = (f / FRAMES + index / count) % 1
                if t < .72:
                    u = t / .72
                    px, py = round(left[0] + (right[0] - left[0]) * u), round(19 - math.sin(math.pi * u) * 13)
                else:
                    u = (t - .72) / .28
                    px, py = round(right[0] + (left[0] - right[0]) * u), 19 + round(math.sin(u * math.pi) * 4)
                berry(d, px, py, ("#C5738D", "#8873B7", "#C6A35D")[index])
        # The tail carries the low return pass in the three-berry game.
            if hard and f % 8 in (2, 3):
                d.line(((25, 23), (28, 22), (30, 23)), fill="#8DB15B")
    else:
        if active:
            x, ball_x, hop = keyed(f, [(0, 5, 21, 0), (3, 5, 21, 0), (4, 7, 22, 0),
                                       (9, 17, 35, 0), (11, 17, 33, 5 if hard else 3),
                                       (14, 14, 28, 0), (19, 5, 20, 0), (23, 5, 21, 0)])
        else:
            x, ball_x, hop = 5, 21 + (1 if 10 <= f <= 13 else 0), 0
        put(image, actor, x, 29 - hop, crouch=1 if f in (2, 3) else 0)
        if 3 <= f <= 5 or (not active and 8 <= f <= 11):
            d.line(((x + 8, 28), (ball_x - 3, 28)), fill="#C1A05D", width=2)
        ball_y = 28 - (1 if active and f in (5, 6, 12, 13) else 0)
        d.ellipse((ball_x - 3, ball_y - 3, ball_x + 3, ball_y + 3), fill="#416D8B", outline="#8EBAC8")
        d.line(((ball_x - 2, ball_y), (ball_x + 2, ball_y)), fill="#B8CBAD")
        d.point((ball_x + (f % 3) - 1, ball_y - 1), fill="#D2D8B5")
        if hard and 9 <= f <= 14:
            for px, py in ((4, 9), (33, 7), (37, 12)):
                d.point((px, py + f % 3), fill="#B16C35")
    return image


def feather(d, x, y, tilt=0):
    d.line(((x - 2, y + 2), (x + 2, y - 2)), fill="#A99FBF")
    d.polygon(((x - 1, y), (x + tilt, y - 3), (x + 3, y - 2), (x + 1, y + 1)), fill="#7F719B")


def monster_scene(name, f, mood):
    image = Image.new("RGB", (64, 32), "black")
    d = ImageDraw.Draw(image)
    active, hard = mood != "idle", mood == "hard"
    if name == "nibble":
        # Low, heavy rock-gobbler: blue scales, orange jaw and stumpy feet.
        x, duck = keyed(f, [(0, 0, 0), (4, -1, 1), (8, 4, 2), (12, 4, 0),
                            (16, 1, 0), (23, 0, 0)]) if active else (0, 0)
        d.polygon(((8+x, 23), (3+x, 24), (2+x, 21), (5+x, 20), (11+x, 21)), fill="#3A526E", outline="#6B819A")
        d.ellipse((6+x, 13+duck, 25+x, 27), fill="#3B5675", outline="#7389A4")
        for px, py in ((10, 14), (14, 13), (18, 14), (22, 15)):
            d.polygon(((px+x-2, py), (px+x, py-3), (px+x+2, py)), fill="#61748C")
        for px in (10, 21):
            d.rectangle((px+x-1, 25, px+x+3, 28), fill="#50627C")
            d.point((px+x+3, 28), fill="#A1A0A0")
        d.polygon(((18+x, 15+duck), (25+x, 15+duck), (29+x, 19+duck), (28+x, 25),
                   (23+x, 28), (17+x, 24)), fill="#9F7949", outline="#C3A16A")
        d.line(((20+x, 24), (26+x, 24)), fill="#62492D", width=2)
        d.rectangle((21+x, 18+duck, 23+x, 20+duck), fill="#172333")
        if f not in (18, 19):
            d.point((23+x, 18+duck), fill="#DECE91")
        if active and 10 <= f <= 15:
            d.line(((21+x, 24), (25+x, 24-(f%2))), fill="#D5AC6F")
        # Nose contact at frames 7–9, stone rolls outward, then is gently caught.
        rock_x = keyed(f, [(0, 33), (6, 33), (9, 36), (13, 35), (18, 31), (23, 33)])[0] if active else 33
        rock_y = 26 - (1 if hard and 10 <= f <= 13 else 0)
        d.polygon(((rock_x-2, rock_y-2), (rock_x+1, rock_y-3), (rock_x+3, rock_y-1),
                   (rock_x+2, rock_y+2), (rock_x-2, rock_y+2)), fill="#666370", outline="#9E9790")
        if hard:
            d.point((4, 28), fill="#6E6762")
            d.point((34, 29), fill="#6E6762")
    elif name == "nox":
        # A winged night-cat with a long tufted tail. Crouch, launch, paw contact.
        x, lift, crouch = keyed(f, [(0, 0, 0, 0), (5, -1, 0, 2), (9, 5, 5 if hard else 3, 0),
                                   (12, 6, 1, 0), (15, 4, 0, 1), (20, 0, 0, 0), (23, 0, 0, 0)]) if active else (0, 0, 1)
        y = 22 - lift + crouch
        tail_y = 15 + (f % 4 if active else 0)
        d.line(((10+x, y+1), (4+x, y), (3+x, tail_y), (6+x, tail_y-2)), fill="#5B4C72", width=2)
        d.polygon(((5+x, tail_y-3), (9+x, tail_y-2), (7+x, tail_y+1)), fill="#756384")
        d.ellipse((8+x, y-6, 23+x, y+4), fill="#333044", outline="#695D7D")
        d.polygon(((12+x, y-2), (7+x, y-7), (8+x, y+3), (17+x, y+3)), fill="#493952", outline="#806A88")
        d.polygon(((17+x, y-6), (17+x, y-13), (21+x, y-9), (25+x, y-13),
                   (27+x, y-6), (26+x, y+1), (20+x, y+2), (16+x, y-2)), fill="#424052", outline="#7B718B")
        d.polygon(((18+x, y-11), (20+x, y-8), (18+x, y-7)), fill="#9F6677")
        d.polygon(((24+x, y-9), (25+x, y-11), (25+x, y-7)), fill="#9F6677")
        for px in (20, 25):
            d.line(((px+x, y-5), (px+x+1, y-5)), fill="#D1A575" if f not in (20,21) else "#8F7892")
        d.point((24+x, y-2), fill="#B199A0")
        feather_x = 34 if not active else keyed(f, [(0,34), (9,34), (12,36), (16,32), (23,34)])[0]
        feather_y = 28 if not active else keyed(f, [(0,28), (9,28), (12,21), (16,25), (23,28)])[0]
        paw = (feather_x, feather_y) if active and 9 <= f <= 13 else (23+x, y+6)
        d.line(((22+x, y+1), paw), fill="#756780", width=2)
        d.line(((12+x, y+2), (11+x, y+6)), fill="#756780", width=2)
        feather(d, feather_x, feather_y, 1 if hard else 0)
    else:
        # A squat thunder-pup: cream mane, teal scales, gold horns and four paws.
        x, lift = keyed(f, [(0,0,0), (5,0,0), (9,4,4 if hard else 2),
                            (13,5,0), (18,1,0), (23,0,0)]) if active else (0,0)
        y = 23-lift
        d.polygon(((10+x,y), (4+x,y+1), (2+x,y-3), (4+x,y-5), (7+x,y-2), (12+x,y-3)), fill="#3D6E70", outline="#72A190")
        d.ellipse((8+x,y-7,24+x,y+3), fill="#376566", outline="#6D9690")
        for px in (11,20):
            d.line(((px+x,y+1), (px+x-1,y+5), (px+x+3,y+5)), fill="#72958A", width=2)
        d.polygon(((17+x,y-6), (17+x,y-11), (20+x,y-8), (23+x,y-12),
                   (24+x,y-8), (28+x,y-7), (26+x,y-3), (29+x,y), (24+x,y+2), (19+x,y-1)),
                  fill="#B3AB7A", outline="#D5C791")
        d.polygon(((22+x,y-8), (24+x,y-14), (25+x,y-8)), fill="#A98D55")
        d.polygon(((17+x,y-7), (18+x,y-13), (21+x,y-8)), fill="#A98D55")
        d.polygon(((21+x,y-6), (26+x,y-6), (28+x,y-3), (26+x,y), (21+x,y-1)), fill="#4C7C73")
        d.point((25+x,y-4), fill="#E2D795")
        d.point((28+x,y-2), fill="#283D43")
        bugs=3 if hard else 2 if active else 1
        for index in range(bugs):
            bx,by=keyed((f+index*8)%24,[(0,34,20), (5,32,15), (10,36,17), (15,34,24), (23,34,20)])
            d.point((bx,by),fill="#B7D482")
            d.point((bx-1,by+1),fill="#52745B")
        if hard and 7<=f<=14:
            d.line(((8+x,y-8),(10+x,y-10),(12+x,y-8)),fill="#99BD8A")
    return image


def sprite(name, frame, mood="idle"):
    if mood not in MOODS or name not in {n for cast in CASTS.values() for n in cast}:
        raise ValueError("unknown play character or activity")
    frame %= FRAMES
    return pokemon_scene(name, frame, mood) if name in CASTS['pokemon-play'] else monster_scene(name, frame, mood)


def export(cast_name, directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    cast=CASTS[cast_name]
    native=Image.new('RGB',(40*FRAMES,32*9),'black')
    labelled=Image.new('RGB',(1096,1320),'#0C0C0C')
    labels=ImageDraw.Draw(labelled)
    for col in range(12):labels.text((128+col*80,5),str(col),fill='#B4B4B4')
    gallery=[]
    for frame in range(FRAMES):
        sheet=Image.new('RGB',(744,616),'#0C0C0C');d=ImageDraw.Draw(sheet)
        d.text((8,6),cast_name.upper()+' / 24 KEYED FRAMES',fill='#B4B4B4')
        for col,mood in enumerate(MOODS):d.text((112+col*208,28),mood.upper(),fill='#B4B4B4')
        for row,name in enumerate(cast):
            y=48+row*188;d.text((8,y+70),name.upper(),fill=cast[name])
            for col,mood in enumerate(MOODS):
                cell=quantized(sprite(name,frame,mood)).crop((0,0,40,32))
                sheet.paste(cell.resize((200,160),Image.Resampling.NEAREST),(112+col*208,y))
        gallery.append(sheet)
    gallery[9].save(directory/'preview.png')
    gallery[0].save(directory/'preview.gif',save_all=True,append_images=gallery[1:],duration=125,loop=0,disposal=2,optimize=False)
    row=0
    for name in cast:
        for mood in MOODS:
            frames=[]
            for frame in range(FRAMES):
                cell=quantized(sprite(name,frame,mood)).crop((0,0,40,32))
                native.paste(cell,(frame*40,row*32))
                y=24+(row*2+frame//12)*72
                labelled.paste(cell.resize((80,64),Image.Resampling.NEAREST),(128+frame%12*80,y))
                frames.append(cell)
            for half in range(2):
                y=24+(row*2+half)*72
                labels.text((8,y+10),name.upper(),fill=cast[name])
                labels.text((8,y+26),mood.upper(),fill='#B4B4B4')
                labels.text((8,y+42),'0-11' if half==0 else '12-23',fill='#777777')
            duration=round(1000/{'idle':3,'busy':8,'hard':12}[mood])
            frames[0].save(directory/f'{name}-{mood}.gif',save_all=True,append_images=frames[1:],duration=duration,loop=0,disposal=2,optimize=False)
            row+=1
    native.save(directory/'sprite-sheet.png');labelled.save(directory/'sprite-sheet-labelled.png')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cast',choices=(*CASTS,'all'),default='all')
    p.add_argument('--output-dir',type=Path,default=ROOT/'docs/ui/companions')
    args=p.parse_args()
    for name in CASTS if args.cast=='all' else (args.cast,):export(name,args.output_dir/name)


if __name__=='__main__':main()
