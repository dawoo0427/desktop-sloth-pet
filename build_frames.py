# -*- coding: utf-8 -*-
"""
나무늘보 클립 프레임 빌더 (빌드 시에만 실행, Pillow 필요)
- 배경 제거(투명 PNG는 알파 기반) -> 베이스 캐릭터 1장(TARGET_H)
- 그 '베이스를 통째로 변형'해서 각 프레임을 완성된 한 장으로 렌더(동적/베이스 겹침 없음)
- 클립(각 N프레임): idle(눈깜빡), happy(통통+웃는눈), startled(놀람 흔들림), curious(갸웃+깜빡)
- 결과: frames/{clip}_{k:02d}.png (마젠타 배경, 창에서 투명). 실행(pet.py)은 Pillow 불필요.
"""
import os
import math
from collections import deque
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))


def _src(local_name, onedrive_name):
    p = os.path.join(HERE, local_name)
    return p if os.path.exists(p) else os.path.join(r"C:\Users\user\OneDrive\바탕 화면", onedrive_name)


# 원본 그림(프로젝트 폴더 우선, 없으면 바탕화면)
SRC = _src("나무늘보.png", "나무늘보.png")            # 서있는 기본
SRC_SLEEP = _src("누운늘보.png", "누운늘보.png")        # 누워 자는 모습
OUTDIR = os.path.join(HERE, "frames")
MAG = (255, 0, 255)
TARGET_H = 150
N = 60                       # 클립당 프레임 수
N_SLEEP = 60                 # 누운 숨쉬기 한 주기 프레임 수
TM, SM, BM = 30, 26, 8       # 위/옆/아래 여백(변형 시 잘림 방지)


# ---- 배경 제거 -> RGBA 하드 알파 ----
def cut_by_alpha(im):
    im = im.convert("RGBA")
    W, H = im.size
    px = im.load()
    fg = [[px[x, y][3] >= 140 for x in range(W)] for y in range(H)]
    nb = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
    # 가장자리 fringe(반투명 + 흰 halo) 흡수: 배경에 닿은 픽셀 중
    #  alpha가 어중간하거나 거의 흰색(모든 채널 큰)이면 제거. 3회 erode.
    for _ in range(3):
        rm = []
        for y in range(H):
            for x in range(W):
                if not fg[y][x]:
                    continue
                edge = False
                for dx, dy in nb:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < W and 0 <= ny < H) or not fg[ny][nx]:
                        edge = True; break
                if not edge:
                    continue
                r, g, b, a = px[x, y]
                if a < 245 or min(r, g, b) > 226:   # 반투명/흰 halo -> 흡수
                    rm.append((x, y))
        if not rm:
            break
        for x, y in rm:
            fg[y][x] = False
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    op = out.load()
    for y in range(H):
        for x in range(W):
            if fg[y][x]:
                r, g, b, _ = px[x, y]
                op[x, y] = (r, g, b, 255)
    return out.crop(out.getbbox())


def cut_background(im):
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        if rgba.getchannel("A").getextrema()[0] < 250:
            return cut_by_alpha(rgba)
    im = im.convert("RGB")
    W, H = im.size
    px = im.load()

    def is_white(c, tol=64):
        return (255 - c[0])**2 + (255 - c[1])**2 + (255 - c[2])**2 < tol * tol

    bg = [[False] * W for _ in range(H)]
    dq = deque()
    for x in range(W):
        dq.append((x, 0)); dq.append((x, H - 1))
    for y in range(H):
        dq.append((0, y)); dq.append((W - 1, y))
    while dq:
        x, y = dq.popleft()
        if x < 0 or y < 0 or x >= W or y >= H or bg[y][x]:
            continue
        bg[y][x] = True
        if not is_white(px[x, y]):
            continue
        dq.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    def lum(c):
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    fg = [[not bg[y][x] for x in range(W)] for y in range(H)]
    for _ in range(2):
        rm = []
        for y in range(H):
            for x in range(W):
                if not fg[y][x]:
                    continue
                if lum(px[x, y]) < 205:
                    continue
                for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
                    if 0 <= nx < W and 0 <= ny < H and not fg[ny][nx]:
                        rm.append((x, y)); break
        for x, y in rm:
            fg[y][x] = False

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    op = out.load()
    for y in range(H):
        for x in range(W):
            if fg[y][x]:
                r, g, b = px[x, y]
                op[x, y] = (r, g, b, 255)
    return out.crop(out.getbbox())


# ---- 눈 검출(흰 반짝임 -> 좌/우 분리) ----
def detect_eyes(B):
    W, H = B.size
    px = B.load()
    whites = []
    for y in range(int(H * 0.17), int(H * 0.42)):
        for x in range(W):
            r, g, b, a = px[x, y]
            if a > 0 and r > 235 and g > 233 and b > 222:
                whites.append((x, y))
    eyes = []
    if not whites:
        return eyes
    uxs = sorted(set(p[0] for p in whites))
    splitx = (uxs[0] + uxs[-1]) / 2.0
    best = -1
    for i in range(1, len(uxs)):
        g = uxs[i] - uxs[i - 1]
        if g > best:
            best = g; splitx = (uxs[i - 1] + uxs[i]) / 2.0
    for grp in ([p for p in whites if p[0] < splitx], [p for p in whites if p[0] >= splitx]):
        if not grp:
            continue
        cx = sum(p[0] for p in grp) / len(grp)
        cy = sum(p[1] for p in grp) / len(grp)
        lr = lg = lb = lc = 0
        for sx, sy in ((cx, cy + 9), (cx - 8, cy + 3), (cx + 8, cy + 3)):
            ix, iy = int(sx), int(sy)
            if 0 <= ix < W and 0 <= iy < H and px[ix, iy][3] > 0:
                r, g, b, _ = px[ix, iy]; lr += r; lg += g; lb += b; lc += 1
        lid = (lr // lc, lg // lc, lb // lc) if lc else (235, 220, 190)
        dark = (60, 40, 30); dl = 1e9
        for yy in range(int(cy) - 6, int(cy) + 7):
            for xx in range(int(cx) - 9, int(cx) + 10):
                if 0 <= xx < W and 0 <= yy < H and px[xx, yy][3] > 0:
                    r, g, b, _ = px[xx, yy]
                    if r + g + b < dl:
                        dl = r + g + b; dark = (r, g, b)
        eyes.append({"cx": cx, "cy": cy + 0.5, "rx": 9.0, "ry": 6.5, "lid": lid, "lash": dark})
    return eyes


def draw_blink(E, eyes, openness):
    """크림 눈꺼풀이 위->아래로 동공+반짝임을 덮음(openness 1=뜸, 0=감음)."""
    if openness >= 0.999 or not eyes:
        return
    px = E.load(); W, H = E.size
    for e in eyes:
        cx, cy, rx, ry = e["cx"], e["cy"], e["rx"], e["ry"]
        top = cy - ry
        cover_to = top + (1.0 - openness) * (2 * ry)
        for yy in range(int(top), int(cy + ry) + 1):
            for xx in range(int(cx - rx), int(cx + rx) + 1):
                if 0 <= xx < W and 0 <= yy < H and \
                   ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0 and yy <= cover_to + 0.5:
                    c = e["lash"] if yy >= cover_to - 1.0 else e["lid"]
                    px[xx, yy] = (c[0], c[1], c[2], 255)


def draw_happy(E, eyes):
    """웃는 감은 눈(크림 채움 + 진한 '^' 곡선)."""
    if not eyes:
        return
    px = E.load(); W, H = E.size
    for e in eyes:
        cx, cy, rx, ry = e["cx"], e["cy"], e["rx"], e["ry"]
        lid, dark = e["lid"], e["lash"]
        for yy in range(int(cy - ry), int(cy + ry) + 1):
            for xx in range(int(cx - rx), int(cx + rx) + 1):
                if 0 <= xx < W and 0 <= yy < H and ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0:
                    px[xx, yy] = (lid[0], lid[1], lid[2], 255)
        span = rx * 0.8
        for i in range(-int(span), int(span) + 1):
            t = i / span
            yy = int(cy + 1 - 3 * (1 - t * t))   # 가운데 위로 솟은 '^'
            xx = int(cx + i)
            for d in (0, 1):
                if 0 <= xx < W and 0 <= yy + d < H:
                    px[xx, yy + d] = (dark[0], dark[1], dark[2], 255)


def squash(E, sy):
    """세로 sy배, 가로 (2-sy)배(부피 보존 느낌)."""
    w, h = E.size
    nw = max(1, round(w * (2 - sy)))
    nh = max(1, round(h * sy))
    return E.resize((nw, nh), Image.BICUBIC)


def tilt(E, ang):
    return E.rotate(ang, resample=Image.BICUBIC, center=(E.width / 2, E.height - 1))


def blink_at(center):
    seq = [0.6, 0.25, 0.0, 0.25, 0.6]
    return {center - 2 + i: seq[i] for i in range(5)}


def _flatten_to(out_rgba):
    """RGBA -> 마젠타 평탄화 RGB."""
    w, h = out_rgba.size
    px = out_rgba.load()
    flat = Image.new("RGB", (w, h), MAG)
    fp = flat.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a >= 128:
                fp[x, y] = (r, g, b)
    return flat


def build_sleep_frames():
    """누운늘보 -> 세근세근 숨쉬는(아주 미세한 상하 스케일) 프레임 sleep_*.png."""
    im = cut_background(Image.open(SRC_SLEEP)).convert("RGBA")
    w, h = im.size
    TW = 200
    base = im.resize((TW, max(1, round(h * TW / w))), Image.NEAREST)
    bw, bh = base.size
    M = 12
    CWs, CHs = bw + 2 * M, bh + 2 * M
    feet_y = M + bh                       # 바닥(눕는 면) 기준
    for k in range(N_SLEEP):
        ph = 2 * math.pi * k / N_SLEEP
        sx = 1.0 + 0.012 * math.sin(ph)   # 배가 살짝 부풀었다 꺼짐
        sy = 1.0 + 0.022 * math.sin(ph)
        nw, nh = max(1, round(bw * sx)), max(1, round(bh * sy))
        e = base.resize((nw, nh), Image.BICUBIC)
        canvas = Image.new("RGBA", (CWs, CHs), (0, 0, 0, 0))
        canvas.alpha_composite(e, (round(CWs / 2 - nw / 2), round(feet_y - nh)))
        _flatten_to(canvas).save(os.path.join(OUTDIR, f"sleep_{k:02d}.png"))
    return (CWs, CHs)


def _back_out(p):
    """back-ease-out: 0->1 이며 살짝 오버슈트(1 넘었다 안착)."""
    c1 = 1.9; c3 = c1 + 1
    p1 = p - 1.0
    return 1.0 + c3 * p1 ** 3 + c1 * p1 ** 2


def main():
    src = cut_background(Image.open(SRC))
    w, h = src.size
    scale = TARGET_H / h
    B = src.resize((round(w * scale), TARGET_H), Image.NEAREST).convert("RGBA")
    Bw = B.width
    eyes = detect_eyes(B)
    print("eyes:", [(round(e["cx"]), round(e["cy"])) for e in eyes])

    CW = Bw + 2 * SM
    CH = TM + TARGET_H + BM
    feet_y = TM + TARGET_H
    cxc = CW / 2.0

    def place(E, dx=0):
        canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        ew, eh = E.size
        canvas.alpha_composite(E, (round(cxc - ew / 2 + dx), round(feet_y - eh)))
        return canvas

    def flatten(canvas):
        px = canvas.load()
        flat = Image.new("RGB", (CW, CH), MAG)
        fp = flat.load()
        for y in range(CH):
            for x in range(CW):
                r, g, b, a = px[x, y]
                if a >= 128:
                    fp[x, y] = (r, g, b)
        return flat

    os.makedirs(OUTDIR, exist_ok=True)
    for f in os.listdir(OUTDIR):
        if f.endswith(".png"):
            os.remove(os.path.join(OUTDIR, f))

    idle_blinks = {}
    idle_blinks.update(blink_at(22)); idle_blinks.update(blink_at(50))
    curious_blinks = blink_at(34)

    for clip in ("idle", "happy", "startled", "curious"):
        for k in range(N):
            E = B.copy()
            ph = 2 * math.pi * k / N

            if clip == "idle":
                draw_blink(E, eyes, idle_blinks.get(k, 1.0))
                canvas = place(E)

            elif clip == "happy":
                draw_happy(E, eyes)
                sy = 1.0 + 0.09 * math.sin(2 * ph)        # 두 번 통통
                canvas = place(squash(E, sy))

            elif clip == "startled":
                decay = max(0.0, 1.0 - k / 42.0)
                dx = 7.0 * math.sin(2 * math.pi * 6 * k / N) * decay
                sy = 1.0 + 0.05 * decay                   # 처음에 움찔
                # 놀란 눈: 거의 뜬 채(끝에 한 번 깜빡)
                draw_blink(E, eyes, blink_at(N - 4).get(k, 1.0))
                canvas = place(squash(E, sy), dx=dx)

            else:  # curious
                ang = 5.0 * math.sin(ph)                  # 좌우로 한 번 갸웃
                draw_blink(E, eyes, curious_blinks.get(k, 1.0))
                canvas = place(tilt(E, ang))

            flatten(canvas).save(os.path.join(OUTDIR, f"{clip}_{k:02d}.png"))
        print("clip:", clip, "x", N)

    # 누운(세근세근 숨쉬는) 모션
    sleep_sz = build_sleep_frames()
    print("sleep_*:", N_SLEEP, sleep_sz)
    print("size:", (CW, CH), "->", OUTDIR)


if __name__ == "__main__":
    main()
