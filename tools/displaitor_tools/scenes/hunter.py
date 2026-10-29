"""Hand-detailed, native-pixel Monster Hunter camp portraits and reactions."""

from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageChops, ImageDraw

PERIOD = 16.0
NAMES = ('palico', 'rathalos', 'zinogre', 'poogie')
INK = '#25343B'
Draw = ImageDraw.ImageDraw


def fern(draw: Draw, x: int, y: int, *, cool: bool = False) -> None:
    stem, leaf, light = ('#3E695D', '#467C6A', '#75A585') if not cool else ('#37585B', '#4C7A77', '#85ABA0')
    draw.line((x, y, x, y - 6), fill=stem)
    for i in range(3):
        yy = y - i * 2
        draw.line((x, yy, x - 3 + i, yy - 2), fill=leaf)
        draw.line((x, yy, x + 3 - i, yy - 2), fill=light)


@lru_cache(maxsize=4)
def background(name: str) -> Image.Image:
    """A quiet, fixed setting with its own materials and lighting for each actor."""
    image = Image.new('RGB', (64, 32), '#203343')
    draw = ImageDraw.Draw(image)
    if name == 'palico':
        # A shaded camp kitchen: distant peaks, canvas seams, wooden worktop.
        draw.polygon(((0, 15), (6, 8), (13, 12), (21, 6), (31, 15), (63, 15), (63, 25), (0, 25)), fill='#3D5A5F')
        draw.polygon(((0, 24), (3, 4), (13, 4), (22, 24)), fill='#8B775B', outline='#424C46')
        draw.polygon(((3, 6), (6, 5), (3, 22), (1, 22)), fill='#C1A46E')
        draw.line((5, 5, 15, 5), fill='#D9BC84')
        draw.line((12, 6, 20, 23), fill='#B69A6E')
        draw.polygon(((7, 23), (11, 10), (15, 23)), fill='#3C423C')
        draw.line((10, 17, 10, 22), fill='#6B6650')
        draw.line((0, 26, 63, 26), fill='#65735B')
        draw.rectangle((0, 27, 63, 31), fill='#445345')
        # Warm hanging lantern and herb bundles leave the chef's outline clear.
        draw.line((55, 3, 55, 27), fill='#665948')
        draw.line((46, 6, 61, 6), fill='#AE9266')
        draw.line((49, 7, 49, 9), fill='#6F6955')
        draw.rectangle((47, 10, 51, 14), fill='#9C8052', outline=INK)
        draw.line((48, 10, 50, 10), fill='#F7D591')
        draw.rectangle((48, 11, 50, 13), fill='#E4B96F')
        draw.point((49, 11), fill='#FFF0BB')
        for x in (57, 60):
            draw.line((x, 7, x, 12), fill='#91A47A')
            draw.line((x - 1, 9, x + 1, 10), fill='#668461')
        draw.rectangle((44, 27, 63, 29), fill='#947855')
        draw.line((45, 27, 63, 27), fill='#C2A179')
        draw.line((46, 30, 46, 31), fill='#6F5E48')
        draw.line((60, 30, 60, 31), fill='#6F5E48')
    elif name == 'poogie':
        # Sunlit village, timber framing and a flower-filled cobbled lane.
        draw.rectangle((0, 0, 63, 13), fill='#566F80')
        draw.line((24, 5, 36, 5), fill='#91A69F')
        draw.line((26, 4, 31, 4), fill='#91A69F')
        for x in (-6, 49):
            draw.rectangle((x, 10, x + 20, 24), fill='#9F8E70')
            draw.polygon(((x - 2, 10), (x + 10, 1), (x + 23, 10)), fill='#7E514B', outline='#5F4C47')
            draw.line((x + 2, 8, x + 10, 3), fill='#CC8E68')
            for y in (7, 9):
                draw.line((x + 4, y, x + 16, y), fill='#A16E58')
            draw.line((x + 3, 11, x + 3, 23), fill='#7F6D53')
            draw.line((x, 19, x + 20, 19), fill='#9D8969')
            draw.rectangle((x + 7, 12, x + 13, 18), fill='#5D6E67', outline='#806A51')
            draw.line((x + 10, 12, x + 10, 18), fill='#B2A27C')
            draw.line((x + 7, 15, x + 13, 15), fill='#B2A27C')
        draw.rectangle((0, 24, 63, 31), fill='#7B8069')
        for i in range(22):
            x, y = i * 19 % 64, 25 + i % 6
            draw.line((x, y, x + 2, y), fill='#A49C7F' if i % 3 else '#7F826B')
        for x in (3, 9, 56, 61):
            draw.line((x, 26, x + 1, 21), fill='#678467')
            draw.line((x - 1, 23, x + 2, 24), fill='#8DA16E')
            draw.line((x, 21, x + 2, 21), fill='#E7C18E' if x % 2 else '#D6A1AA')
    else:
        # Amber forest for Rathalos, blue-green bamboo for Zinogre.
        cool = name == 'zinogre'
        far, trunk, foliage = ('#2B4857', '#3A6063', '#3F6F68') if cool else ('#4B4F48', '#635D4A', '#6B6D4B')
        draw.ellipse((45, 2, 51, 8), fill='#C1D1BD' if cool else '#DFC591')
        draw.polygon(((0, 16), (11, 8), (23, 12), (36, 5), (49, 12), (63, 9), (63, 26), (0, 26)), fill=far)
        for i, x in enumerate((1, 8, 57, 63)):
            draw.rectangle((x, 0, x + 2, 26), fill=trunk)
            draw.line((x + 1, 1, x + 1, 24), fill='#789084' if cool else '#958867')
            if cool:
                for y in (4 + i, 12 + i, 20 + i):
                    draw.line((x - 1, y, x + 3, y), fill='#284C53')
                    draw.line((x + 2, y, x + 5, y - 3), fill=foliage)
                    draw.line((x + 3, y - 2, x + 6, y - 2), fill='#77A18B')
            else:
                for y in (3 + i, 10 + i, 17 + i):
                    draw.polygon(((x, y), (x - 4, y - 2), (x - 7, y + 1), (x + 3, y + 3), (x + 8, y - 1)), fill=foliage)
                    draw.line((x - 3, y, x + 2, y + 1), fill='#9C9B69')
        draw.polygon(((0, 27), (12, 24), (26, 27), (44, 24), (63, 26), (63, 31), (0, 31)), fill='#576F62' if cool else '#7D795A')
        draw.line(((0, 30), (11, 28), (29, 30), (48, 28), (63, 29)), fill='#91A087' if cool else '#B1A278')
        fern(draw, 4, 31, cool=cool)
        fern(draw, 60, 30, cool=cool)
        for x, y in ((12, 30), (52, 29), (2, 27), (61, 31)):
            draw.line((x, y, x + 2, y), fill='#B6B99B' if cool else '#C2AF81')
    return image


def palico(draw: Draw, elapsed: float, *, reaction: float | None = None) -> None:
    # Fluffy tabby face, lobed toque, blue neckerchief, stitched apron and paws.
    fur, shade, light = '#E9C791', '#B78255', '#FFF0C3'
    stir = (0, 1, 1, 0, -1, -1, 0, 0)[int(elapsed * 4) % 8]
    serve = 0 if reaction is None else round(math.sin(math.pi * reaction / 3.2) * 6)
    draw.ellipse((16, 29, 39, 31), fill='#35483E')
    draw.line(((24, 27), (18, 27), (15, 24), (15, 20), (17, 19)), fill=INK, width=4)
    draw.line(((24, 27), (18, 27), (15, 24), (15, 20), (17, 19)), fill=fur, width=2)
    draw.point((15, 23), fill=shade)
    draw.point((18, 27), fill=light)
    draw.polygon(((24, 21), (32, 21), (35, 25), (34, 29), (24, 29), (22, 26)), fill=shade, outline=INK)
    draw.rectangle((25, 28, 28, 30), fill=fur)
    draw.rectangle((32, 28, 35, 30), fill=fur)
    draw.line((25, 30, 28, 30), fill='#8D765B')
    draw.line((32, 30, 35, 30), fill='#8D765B')
    draw.point((26, 29), fill=light)
    draw.point((33, 29), fill=light)
    draw.polygon(((25, 22), (32, 22), (33, 28), (24, 28)), fill='#E0D9BC', outline='#928F7D')
    draw.line((26, 24, 31, 24), fill='#F7E9CB')
    draw.rectangle((27, 25, 30, 26), fill='#BEBBA0')
    draw.point((29, 25), fill='#7A938A')
    draw.point((25, 26), fill='#FAE8C3')
    draw.point((32, 27), fill='#ADA78C')
    draw.point((26, 30), fill='#9E8161')
    draw.point((34, 30), fill='#9E8161')
    draw.line(((24, 23), (21, 25), (19, 24)), fill=INK, width=3)
    draw.line(((24, 23), (21, 25), (19, 24)), fill=fur)
    draw.point((19, 23), fill=light)
    # Cheek tufts break the silhouette instead of a flat hexagonal head.
    draw.polygon(((21, 12), (20, 8), (24, 10), (26, 9), (32, 9), (37, 7),
                  (36, 13), (38, 15), (37, 17), (38, 18), (35, 19), (33, 21),
                  (25, 21), (22, 19), (20, 18), (21, 16), (20, 14)), fill=fur, outline=INK)
    draw.polygon(((21, 9), (24, 11), (22, 13)), fill='#D59A82')
    draw.polygon(((36, 9), (33, 11), (35, 12)), fill='#D59A82')
    draw.line((23, 11, 25, 12), fill=light)
    draw.line((32, 12, 34, 11), fill=light)
    for x in (27, 30):
        draw.line((x, 10, x, 12), fill=shade)
    draw.line((21, 14, 23, 15), fill=shade)
    draw.line((36, 13, 35, 14), fill=shade)
    draw.point((23, 13), fill='#D99B65')
    draw.line((35, 15, 36, 15), fill='#C99161')
    draw.point((22, 18), fill='#F4D6A1')
    draw.point((34, 19), fill='#F4D6A1')
    draw.polygon(((25, 17), (28, 16), (31, 16), (34, 17), (33, 19), (29, 20), (25, 19)), fill=light)
    happy = reaction is not None and .6 < reaction < 2.6
    blink = 7.0 <= elapsed % 8 < 7.25
    for x in (25, 32):
        if happy:
            draw.line(((x - 1, 15), (x, 14), (x + 1, 15)), fill='#3D423C')
        elif blink:
            draw.line((x - 1, 15, x + 1, 15), fill='#3D423C')
        else:
            draw.rectangle((x, 14, x + 1, 16), fill='#34423C')
            draw.point((x, 14), fill='#F8F6D6')
            draw.point((x + 1, 16), fill='#6D7D61')
    draw.line((28, 17, 30, 17), fill='#AE7164')
    draw.point((29, 18), fill='#AE7164')
    draw.point((28, 17), fill='#E5B29A')
    draw.line(((27, 19), (28, 20), (29, 19), (30, 20), (31, 19)), fill='#8E6C54')
    draw.point((23, 17), fill='#D4947E')
    draw.point((35, 16), fill='#D4947E')
    draw.line((20, 16, 22, 17), fill='#DED6AD')
    draw.line((36, 16, 39, 15), fill='#DED6AD')
    draw.polygon(((23, 21), (33, 21), (30, 23), (28, 22), (26, 24)), fill='#548E97', outline=INK)
    draw.line((25, 21, 31, 21), fill='#A1D0C6')
    draw.point((28, 22), fill='#B9DACC')
    # Three offset puffs, dark creases and a shaded cuff make the chef hat read.
    draw.polygon(((23, 7), (22, 5), (24, 3), (27, 3), (28, 1), (32, 1), (34, 3),
                  (36, 3), (37, 5), (35, 7), (35, 9), (24, 9)), fill='#D6DAC5', outline=INK)
    draw.line(((24, 5), (25, 4), (27, 4)), fill='#FFF2D2')
    draw.line((29, 2, 31, 2), fill='#FFF2D2')
    draw.line((34, 4, 35, 5), fill='#FFF2D2')
    draw.line((27, 6, 27, 7), fill='#A8BBAE')
    draw.line((33, 6, 33, 7), fill='#A8BBAE')
    draw.line((25, 8, 34, 8), fill='#FFF0CC')
    draw.point((24, 6), fill='#BAC7B7')
    draw.point((30, 5), fill='#F3E8C9')
    draw.point((35, 6), fill='#B7C4B4')
    # The paw actually carries the dish when serving; no floating platter.
    hand_y = 24 - serve
    draw.line(((34, 23), (36, 24 - serve // 2), (40, hand_y)), fill=INK, width=3)
    draw.line(((34, 23), (36, 24 - serve // 2), (40, hand_y)), fill=fur)
    draw.point((40, hand_y), fill=light)
    if serve > 0:
        draw.ellipse((36, hand_y - 2, 47, hand_y), fill='#DADECC', outline='#6F8C83')
        draw.line((38, hand_y - 1, 45, hand_y - 1), fill='#FFF0CF')
        draw.polygon(((39, hand_y - 3), (40, hand_y - 6), (43, hand_y - 6), (46, hand_y - 3)), fill='#B97744')
        draw.line((41, hand_y - 5, 43, hand_y - 5), fill='#F2BF73')
        draw.point((40, hand_y - 3), fill='#91A96A')
    else:
        draw.line((39 + stir, 20, 42, 28), fill='#CDB88C')
        draw.line((39 + stir, 20, 39 + stir, 22), fill='#EED7A4')
    # Round iron cauldron: rim, shaded iron, handles and a warm cooking flame.
    draw.arc((36, 25, 41, 29), 70, 290, fill='#9BA69A')
    draw.arc((47, 25, 51, 29), 250, 110, fill='#9BA69A')
    draw.ellipse((39, 25, 49, 30), fill='#3C5151', outline=INK)
    draw.line((40, 28, 41, 29), fill='#738C80')
    draw.line((47, 28, 47, 29), fill='#223A40')
    draw.ellipse((38, 24, 49, 27), fill='#CAD0AD', outline='#6D8D80')
    draw.line((40, 25, 47, 25), fill='#A7BA83')
    draw.point((42, 25), fill='#D9DBA1')
    draw.point((46, 25), fill='#DB9B70')
    draw.point((44, 26), fill='#6C9A73')
    draw.line((41, 31, 47, 31), fill='#9E704A')
    draw.point((43, 30), fill='#EAB668')
    draw.point((46, 30), fill='#C68852')
    for i in range(2):
        age = (elapsed / 2 + i * .5) % 1
        x, y = 42 + i * 4 + round(math.sin(age * math.tau)), 22 - round(age * 6)
        draw.line((x, y, x + 1, y - 1), fill='#B3C0B1')


def rathalos(draw: Draw, elapsed: float, *, reaction: float | None = None) -> None:
    breath = round(math.sin(elapsed * math.tau / 4))
    edge, red, light = '#3C3B42', '#B9514D', '#E38664'
    draw.ellipse((8, 28, 57, 31), fill='#5C624E')
    # Segmented armoured tail curls around the nest, with blue-black tip spines.
    draw.line(((26, 28), (17, 29), (10, 27), (7, 23), (8, 20)), fill=edge, width=7)
    draw.line(((26, 28), (17, 29), (10, 27), (7, 23), (8, 20)), fill=red, width=5)
    draw.line(((24, 27), (17, 28), (11, 26), (9, 23)), fill=light)
    for x, y in ((11, 28), (16, 30), (21, 30)):
        draw.line((x, y - 2, x, y), fill='#723E43')
    draw.polygon(((6, 22), (3, 18), (7, 19), (10, 17), (11, 21), (9, 24)), fill='#476477', outline=edge)
    draw.line((5, 19, 7, 21), fill='#7C96A3')
    # Hindquarters and a pale plated belly, tucked talons visible under the wing.
    draw.ellipse((18, 18 + breath, 45, 30), fill=red, outline=edge)
    draw.polygon(((23, 24), (36, 23), (43, 26), (40, 29), (26, 30), (21, 28)), fill='#D5AC79')
    for x in (26, 30, 34, 38):
        draw.line((x, 27, x + 1, 29), fill='#AE825F')
    draw.ellipse((27, 26, 37, 29), fill='#9E4D49', outline=edge)
    draw.line((31, 28, 37, 28), fill=light)
    for x in (31, 34, 37):
        draw.line((x, 29, x + 1, 29), fill='#E8D6AA')
    # The folded wing has four structural fingers and patterned membrane cells.
    top = 7 + breath
    draw.polygon(((20, 25), (20, 14), (18, top), (23, top + 2), (29, 16),
                  (31, top - 1), (35, 12 + breath), (42, 21), (44, 27),
                  (38, 25), (35, 27), (30, 24), (27, 26), (23, 23)), fill='#723F48', outline=edge)
    draw.polygon(((21, top + 4), (27, 17), (27, 23), (23, 21)), fill='#D97B5F')
    draw.polygon(((28, 18), (31, top + 2), (34, 14), (35, 24)), fill='#C06553')
    draw.polygon(((35, 16), (40, 22), (42, 25), (37, 23)), fill='#D78A65')
    draw.line(((19, top + 1), (24, 13 + breath), (29, 20), (42, 26)), fill='#E7AF7C')
    draw.line((29, 20, 27, 25), fill='#E1A574')
    draw.line((29, 20, 31, top + 1), fill='#E1A574')
    draw.line((34, 22, 35, 26), fill='#E1A574')
    for x, y in ((23, 16), (25, 20), (31, 16), (33, 21), (38, 22)):
        draw.line((x, y + breath, x + 1, y + breath), fill='#964B48')
    # Membrane markings sit inside each finger cell and follow the breathing wing.
    for x, y in ((23, 18), (25, 21), (32, 17), (33, 20), (37, 21)):
        draw.point((x, y + breath), fill='#D68765')
        draw.line((x, y + 1 + breath, x + 1, y + 1 + breath), fill='#A2554D')
    for x, y in ((22, 10 + breath), (31, top), (40, 22)):

        draw.point((x, y), fill='#AAB7AB')
    # Broad dinosaur muzzle, horned brow and layered blue jaw armour.
    draw.polygon(((38, 22), (39, 17), (42, 15), (47, 16), (50, 20), (55, 21),
                  (58, 24), (57, 27), (50, 29), (43, 28), (39, 26)), fill=red, outline=edge)
    draw.polygon(((40, 19), (40, 15), (38, 12), (43, 14), (45, 18)), fill='#BCC8BA', outline=edge)
    draw.line((40, 14, 42, 16), fill='#E9D8AA')
    draw.polygon(((46, 18), (47, 14), (49, 14), (50, 20)), fill='#607D88', outline=edge)
    draw.polygon(((42, 21), (46, 19), (50, 21), (53, 22), (49, 23)), fill=light)
    draw.line((45, 19, 47, 20), fill='#ECAC7C')
    if reaction is not None and .3 < reaction < 2.8:
        draw.rectangle((46, 22, 48, 23), fill='#F6D278')
        draw.line((47, 22, 47, 23), fill=INK)
        draw.point((46, 22), fill='#FFE3A1')
    else:
        draw.line(((45, 23), (47, 24), (49, 23)), fill='#3E4141')
        draw.point((46, 22), fill='#B5735D')
    draw.polygon(((49, 26), (56, 25), (57, 27), (51, 29), (46, 28)), fill='#607B83', outline=edge)
    draw.line((50, 27, 55, 26), fill='#CBD3B7')
    draw.point((53, 22), fill='#703F42')
    draw.point((55, 23), fill='#F1AA78')
    draw.line((42, 25, 44, 26), fill='#D0775C')
    draw.point((43, 27), fill='#873D43')
    draw.line((41, 22, 43, 23), fill='#DC8061')
    draw.point((42, 24), fill='#903E43')
    draw.point((44, 21), fill='#F0A174')
    draw.point((54, 27), fill='#E8D2A5')
    draw.point((51, 28), fill='#D6C5A0')
    if reaction is None:
        age = elapsed % 4 / 4
        x, y = 55 + round(age * 2), 15 - round(age * 7)
        draw.line((x, y, x + 2, y), fill='#C3BEA0')
        draw.point((x + 2, y - 1), fill='#C3BEA0')


def zinogre(draw: Draw, elapsed: float, *, reaction: float | None = None) -> None:
    sway = round(math.sin(elapsed * math.tau / 4))
    blue, shade, light = '#4B93A3', '#356274', '#8AC6C5'
    fur, furshade, gold = '#F1E6BD', '#B8BDA2', '#D2A75F'
    draw.ellipse((9, 28, 56, 31), fill='#3E5956')
    # Heavy furred tail: stepped tufts, teal underside, pale striped plates.
    draw.polygon(((25, 25), (17, 25), (13, 23), (11, 19), (6, 16 + sway),
                  (8, 11 + sway), (10, 8 + sway), (13, 13 + sway), (17, 14 + sway),
                  (17, 17), (22, 17), (24, 21), (28, 23)), fill=shade, outline=INK)
    draw.polygon(((9, 12 + sway), (11, 14 + sway), (13, 14 + sway), (15, 18), (21, 20),
                  (24, 23), (18, 23), (14, 20), (11, 18), (8, 16 + sway)), fill=light)
    draw.line(((10, 10 + sway), (12, 16 + sway), (15, 17), (16, 20), (21, 22)), fill=fur, width=2)
    draw.line((13, 16 + sway, 13, 18 + sway), fill='#4E8792')
    draw.line((17, 20, 17, 22), fill='#4E8792')
    # Powerful haunches, tucked belly, and large armoured forepaws.
    draw.ellipse((22, 19, 46, 28), fill=blue, outline=INK)
    draw.polygon(((25, 23), (30, 21), (33, 23), (31, 27), (26, 28), (22, 27)), fill=shade)
    draw.line((26, 22, 29, 22), fill=light)
    draw.polygon(((24, 25), (29, 26), (28, 29), (23, 30), (20, 29)), fill=blue, outline=INK)
    draw.line((23, 28, 26, 28), fill=light)
    draw.polygon(((37, 22), (42, 22), (45, 28), (44, 30), (35, 30), (35, 28)), fill=blue, outline=INK)
    draw.polygon(((37, 23), (41, 23), (43, 27), (38, 27), (35, 28)), fill=gold, outline='#8D805E')
    draw.line((38, 24, 40, 24), fill='#F3D394')
    draw.point((40, 26), fill='#A47F4E')
    for x in (22, 25, 36, 39, 42):
        draw.line((x, 29, x + 1, 29), fill=fur)
    # Jagged layered mane, not a single cream polygon.
    draw.polygon(((28, 21), (29, 16), (31, 17), (32, 11), (35, 14), (38, 9),
                  (40, 13), (43, 12), (46, 17), (44, 24), (41, 26), (39, 23),
                  (37, 25), (35, 22), (32, 23), (32, 20)), fill=furshade, outline=INK)
    draw.polygon(((30, 18), (32, 18), (33, 14), (35, 17), (38, 12), (39, 16),
                  (42, 15), (44, 18), (41, 22), (40, 23), (38, 20), (36, 23),
                  (35, 20), (32, 21)), fill=fur)
    draw.line((34, 17, 33, 20), fill='#D4CFAB')
    draw.line((38, 16, 37, 20), fill='#C8C8A8')
    draw.point((39, 22), fill='#99A997')
    # Swept horns, brow plates and a narrow canine muzzle over a white jaw ruff.
    draw.polygon(((39, 17), (39, 12), (42, 10), (47, 12), (48, 16), (53, 18),
                  (56, 21), (54, 24), (48, 24), (45, 22), (41, 23)), fill=blue, outline=INK)
    draw.polygon(((40, 13), (37, 9), (36, 4), (39, 6), (42, 11)), fill='#B6C6B2', outline=INK)
    draw.line((37, 6, 39, 9), fill='#F2E8C2')
    draw.polygon(((45, 12), (46, 7), (48, 4), (49, 6), (48, 13)), fill='#B6C6B2', outline=INK)
    draw.line((47, 8, 48, 6), fill='#F2E8C2')
    draw.polygon(((40, 13), (42, 11), (46, 13), (48, 16), (45, 17), (42, 15)), fill=gold)
    draw.line((42, 12, 45, 14), fill='#F3D394')
    draw.line((44, 15, 47, 16), fill='#9A8156')
    draw.line((47, 17, 49, 18), fill='#F6D882')
    draw.line((49, 17, 49, 18), fill=INK)
    draw.point((47, 17), fill='#FFF2C6')
    draw.line((51, 19, 54, 20), fill=light)
    draw.point((55, 21), fill=INK)
    draw.polygon(((47, 21), (50, 22), (54, 22), (53, 25), (49, 26), (46, 24)), fill=furshade, outline=INK)
    draw.line((49, 23, 53, 23), fill=fur)
    draw.point((52, 24), fill=fur)
    draw.line((45, 19, 44, 21), fill=light)
    draw.point((46, 20), fill='#B3D9CC')
    draw.point((48, 20), fill='#3B6D7D')
    # Fur clumps, scale facets and tendon highlights use the remaining body pixels.
    for x, y in ((31, 19), (35, 18), (39, 20)):
        draw.line((x, y, x + 1, y - 1), fill='#C0C5A4')
        draw.point((x + 1, y - 2), fill='#FFF0C9')
    for x, y in ((26, 24), (30, 23), (33, 25)):
        draw.line((x, y, x + 1, y - 1), fill='#70ADB4')
    draw.point((38, 25), fill='#B88E52')
    draw.point((41, 26), fill='#F0CA86')
    # Individual gold scale clusters continue from the mane down the back.
    for x, y in ((24, 19), (28, 17), (32, 15)):
        draw.polygon(((x - 1, y), (x, y - 2), (x + 2, y - 1), (x + 2, y + 1)), fill=gold, outline='#8D805E')
        draw.point((x, y - 1), fill='#F0CF8A')
    if reaction is not None and .5 < reaction < 2.7:
        for x, y in ((11, 15 + sway), (18, 21), (32, 18), (36, 16), (40, 21)):
            draw.line((x, y, x + 1, y - 1), fill='#C7F3E4')


def poogie(draw: Draw, elapsed: float, *, reaction: float | None = None) -> None:
    # The body and hooves stay planted; only the snout, ears and curled tail move.
    nose = 1 if 2.5 < elapsed % 4 < 3.1 else 0
    happy = reaction is not None and .4 < reaction < 2.8
    ear = 1 if happy or 5.5 < elapsed % 8 < 6 else 0
    draw.ellipse((15, 28, 52, 31), fill='#7C8064')
    draw.arc((12, 18, 19, 25), 65, 340, fill='#9A726C', width=2)
    draw.arc((12, 18, 18, 24), 65, 340, fill='#CD9B87')
    draw.point((14, 19), fill='#E4B798')
    # Shaded legs, cloven hooves and a rounded striped costume.
    for x, y in ((22, 26), (35, 26), (25, 28), (42, 28)):
        draw.rectangle((x, y, x + 3, 30), fill='#BC8777', outline='#8F7569')
        draw.line((x, 30, x + 3, 30), fill='#685A53')
        draw.point((x + 2, 30), fill='#A7957B')
        draw.point((x + 1, y + 1), fill='#DCA28C')
    draw.ellipse((17, 11, 45, 29), fill='#72956C', outline='#3F5E53')
    draw.polygon(((20, 15), (24, 12), (34, 12), (40, 16), (40, 20), (19, 20)), fill='#95B387')
    draw.polygon(((18, 22), (27, 25), (37, 25), (43, 21), (42, 26), (36, 28), (24, 28), (19, 26)), fill='#4D7659')
    # Curved cream stripes follow the belly instead of straight flat bars.
    for x in (22, 30, 38):
        draw.polygon(((x, 12), (x + 3, 12), (x + 1, 17), (x + 1, 23), (x + 3, 27),
                      (x, 28), (x - 2, 23), (x - 2, 17)), fill='#BDC3A2')
        draw.line((x, 14, x - 1, 17), fill='#DDD6B5')
        draw.line((x - 1, 24, x + 1, 27), fill='#929F83')
    draw.line(((19, 25), (23, 28), (30, 29), (36, 28)), fill='#637E60')
    # Short knit stitches and seam shadows describe the curved cloth surface.
    for x, y in ((25, 16), (27, 20), (25, 24), (33, 21), (35, 24)):
        draw.line((x, y, x + 1, y), fill='#628963')
        draw.point((x, y - 1), fill='#A8BC8B')
    # A small costume bow and button accent the broad green-and-cream silhouette.
    draw.polygon(((32, 14), (35, 15), (37, 13), (38, 16), (35, 17), (33, 17)), fill='#4C776A')
    draw.point((35, 16), fill='#E6C88E')
    # Three-quarter face: folded floppy ears, shiny dark eye and a big soft snout.
    draw.ellipse((35, 13, 50, 28), fill='#C38D7C', outline='#916E65')
    draw.polygon(((37, 16), (38, 13), (44, 14), (48, 17), (47, 22), (39, 23), (36, 20)), fill='#DEA68D')
    draw.polygon(((36, 17), (33, 12 - ear), (34, 8 - ear), (38, 10 - ear), (41, 15)), fill='#B97B73', outline='#89685F')
    draw.line(((35, 10 - ear), (37, 12 - ear), (38, 15)), fill='#DFA68D')
    draw.line((35, 12 - ear, 37, 14 - ear), fill='#AF756F')
    draw.polygon(((45, 15), (47, 9 + ear), (50, 11 + ear), (50, 15 + ear), (47, 19)), fill='#B97B73', outline='#89685F')
    draw.line(((48, 11 + ear), (49, 13 + ear), (47, 16 + ear)), fill='#D49A83')
    draw.point((39, 17), fill='#B18C78')
    if happy or 7 <= elapsed % 8 < 7.25:
        draw.line(((39, 20), (40, 19), (41, 20)), fill='#4B4941')
    else:
        draw.rectangle((40, 18, 41, 20), fill='#3D4140')
        draw.point((40, 18), fill='#FFF0CE')
        draw.point((41, 20), fill='#795C50')
    draw.ellipse((42 + nose, 21, 53 + nose, 28), fill='#AC726D', outline='#805F5F')
    draw.ellipse((43 + nose, 21, 53 + nose, 26), fill='#CF9482')
    draw.line((45 + nose, 22, 50 + nose, 22), fill='#E7B18E')
    for x in (46, 51):
        draw.line((x + nose, 24, x + nose, 25), fill='#6F5153')
        draw.point((x - 1 + nose, 24), fill='#B47B73')
    draw.point((39, 24), fill='#C58D7E')
    draw.point((40, 25), fill='#D59C86')
    draw.line(((40, 26), (41, 27), (43, 27)), fill='#986A60')
    draw.line((38, 21, 38, 23), fill='#D29A85')
    draw.point((43 + nose, 23), fill='#DDA58C')
    draw.point((48 + nose, 26), fill='#BA7F73')


@lru_cache(maxsize=64)
def actor(name: str, tick: int) -> Image.Image:
    """Bounded pose cache; cached images are only ever read by compositors."""
    image = Image.new('RGBA', (64, 32))
    _ACTORS[name](ImageDraw.Draw(image), tick / 10)
    return image


_ACTORS = {'palico': palico, 'rathalos': rathalos, 'zinogre': zinogre, 'poogie': poogie}


def render(name: str, elapsed: float) -> Image.Image:
    image = background(name).copy()
    draw = ImageDraw.Draw(image)
    # Environmental animation stays above the character silhouette.
    for i in range(3):
        x = (i * 23 + int(elapsed * 8)) % 64
        y = round(3 + math.sin(elapsed * math.tau / 8 + i * 2))
        draw.point((x, y), fill='#D5C9A2' if name == 'poogie' else '#88AAA0')
    if name == 'zinogre':
        for i in range(3):
            angle = elapsed * math.tau / 8 + i * 2
            draw.point((round(31 + 25 * math.cos(angle)), round(12 + 5 * math.sin(angle))), fill='#A3D4C0')
    sprite = actor(name, math.floor(elapsed * 10 + 1e-8) % 80)
    image.paste(sprite, (0, 0), sprite)
    return image


@lru_cache(maxsize=4)
def actor_surfaces(name: str) -> tuple[Image.Image, Image.Image]:
    """Return the pose union and pixels identical in every ambient pose."""
    first = actor(name, 0)
    mask = Image.new('L', (64, 32))
    variation = Image.new('L', (64, 32))
    # Every actor's longest pose cycle is eight seconds; the scene loop is 16.
    for tick in range(80):
        pose = actor(name, tick)
        mask = ImageChops.lighter(mask, pose.getchannel('A'))
        for channel in ImageChops.difference(first, pose).split():
            variation = ImageChops.lighter(variation, channel)
    stable = first.copy()
    stable.putalpha(ImageChops.multiply(first.getchannel('A'), variation.point(lambda value: 255 if value == 0 else 0)))
    return mask, stable


def actor_mask(name: str) -> Image.Image:
    """Union of ambient poses lets a reaction replace the actor without ghosts."""
    return actor_surfaces(name)[0]


def reaction_layer(name: str, elapsed: float) -> Image.Image:
    """Replace only possible actor pixels, preserving the fixed surrounding scene."""
    image = Image.new('RGBA', (64, 32))
    mask, stable = actor_surfaces(name)
    image.paste(background(name), (0, 0), mask)
    _ACTORS[name](ImageDraw.Draw(image), elapsed, reaction=elapsed)
    # Omit static body pixels already supplied by every possible ambient frame.
    # Keep only changed pixels and the background needed to erase a moving limb.
    red, green, blue, _ = ImageChops.difference(image, stable).split()
    difference = ImageChops.lighter(red, ImageChops.lighter(green, blue))
    matching = difference.point(lambda value: 255 if value == 0 else 0)
    removable = ImageChops.multiply(stable.getchannel('A'), matching)
    image.putalpha(ImageChops.subtract(image.getchannel('A'), removable))
    return image
