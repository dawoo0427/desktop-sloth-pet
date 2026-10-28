"""3D 나무늘보 프레임 빌드: Blender 로 렌더(sloth3d.py) -> 축소 + 마젠타 평탄화 -> frames/.

사용법:  python build_frames_3d.py            # 렌더 + 변환 (Blender 5.x, Pillow 필요)
         python build_frames_3d.py --no-render  # 이미 렌더된 render3d/ 로 변환만

pet.py 는 그대로. 기존 픽셀아트 프레임과 같은 크기로 맞춘다
(서있는 클립 142x188, 캐릭터 높이 150 / 누운 sleep 224x150).
3D와 픽셀아트 중간 느낌: 셀 셰이딩 렌더 -> 1/2 축소 -> 공통 팔레트 -> 1칸 외곽선 -> 2배 도트 확대.
"""
import glob
import os
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "render3d")
OUTDIR = os.path.join(HERE, "frames")
STAND = ["idle", "happy", "startled", "curious"]
N = 60
MAG = (255, 0, 255)
PIXEL = 2                 # 도트 크기 (2 = 2x2 픽셀 한 칸, 원본 픽셀아트보다 살짝 촘촘)
N_COLORS = 40             # 전체 공통 팔레트 색 수
OUTLINE_RGB = (70, 48, 31)


def _shade(hexc, band):
    """sloth3d.py 셀 셰이딩 결과색 = sRGB(linear(색) x 명암단계)."""
    out = []
    for i in (1, 3, 5):
        v = int(hexc[i:i + 2], 16) / 255
        v = v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        v *= band
        v = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        out.append(round(max(0, min(1, v)) * 255))
    return tuple(out)


KEEP_COLORS = [_shade(c, b) for c in ("#F59C9C", "#F6E8CC", "#7CC243", "#5EA332") for b in (1.0, 0.8, 0.64)] + [(255, 255, 255)]

STAND_W, STAND_H, CHAR_H, FOOT_PAD = 150, 188, 150, 8   # 발바닥이 아래에서 8px 위
SLEEP_W, SLEEP_H, SLEEP_PAD = 224, 150, 6


def find_blender():
    cands = sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender *\blender.exe"),
                   key=lambda p: [int(x) for x in p.split("Blender ")[-1].split("\\")[0].split(".")])
    if not cands:
        raise SystemExit("Blender 를 찾을 수 없습니다 (C:\\Program Files\\Blender Foundation).")
    return cands[-1]


def render():
    blender = find_blender()
    print("Blender:", blender)
    subprocess.run([blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "sloth3d.py"),
                    "--", RENDER, ",".join(STAND + ["sleep"]), str(N)], check=True)


def bbox_of(paths):
    """여러 프레임의 불투명 영역 합집합 bbox (모션 범위 전체)."""
    box = None
    for p in paths:
        b = Image.open(p).getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return box


def to_lowres(clips, W, H, ref_box, scale, anchor):
    """ref_box 기준 같은 배율/위치로 저해상도(W/PIXEL) RGBA 프레임을 만든다 (모션이 정규화되지 않게)."""
    w, h = W // PIXEL, H // PIXEL
    scale /= PIXEL
    ax, ay = anchor[0] / PIXEL, anchor[1] / PIXEL   # ref_box 의 (가로 중심, 바닥) 이 캔버스의 이 점에 오도록
    cx = (ref_box[0] + ref_box[2]) / 2
    out = {}
    for clip in clips:
        for k in range(N):
            src = Image.open(os.path.join(RENDER, f"{clip}_{k:02d}.png")).convert("RGBA")
            small = src.resize((round(src.width * scale), round(src.height * scale)), Image.LANCZOS)
            ox = round(ax - cx * scale)
            oy = round(ay - ref_box[3] * scale)
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(small, (ox, oy))      # 빈 캔버스라 RGBA 그대로 복사 (음수 좌표는 잘림)
            full = src.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
            if full:  # 잘림 검사 (외곽선 1칸 여유 포함)
                l, t = full[0] * scale + ox - 1, full[1] * scale + oy - 1
                r, bt = full[2] * scale + ox + 1, full[3] * scale + oy + 1
                if l < 0 or t < 0 or r > w or bt > h:
                    print(f"  경고: {clip}_{k:02d} 가 캔버스 밖으로 {l:.0f},{t:.0f},{r:.0f},{bt:.0f} ({w}x{h})")
            out[(clip, k)] = canvas
    return out


def pixelize(frames):
    """공통 팔레트로 색 줄이기 + 1칸 진갈색 외곽선 + PIXEL배 확대 + 마젠타 평탄화 -> frames/ 저장."""
    # 모든 프레임에서 고른 표본으로 팔레트 하나 (프레임마다 색이 달라 깜빡이는 것 방지)
    keys = sorted(frames)
    sample = [frames[k] for k in keys[::7]]
    sw = sum(f.width for f in sample)
    strip = Image.new("RGB", (sw, max(f.height for f in sample)), OUTLINE_RGB)
    x = 0
    for f in sample:
        strip.paste(f.convert("RGB"), (x, 0), f.getchannel("A").point(lambda v: 255 if v >= 128 else 0))
        x += f.width
    adaptive = strip.quantize(colors=N_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    colors = adaptive.getpalette()[:3 * N_COLORS]
    for c in KEEP_COLORS:            # 픽셀 수가 적어 탈락하기 쉬운 포인트 색(볼터치·손톱·반짝이) 고정
        colors += list(c)
    pal = Image.new("P", (1, 1))
    pal.putpalette(colors + [0] * (768 - len(colors)))

    for (clip, k), f in frames.items():
        w, h = f.size
        a = f.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        rgb = Image.new("RGB", (w, h), OUTLINE_RGB)
        rgb.paste(f.convert("RGB"), (0, 0), a)
        q = rgb.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")
        ap, qp = a.load(), q.load()
        flat = Image.new("RGB", (w, h), MAG)
        fp = flat.load()
        for yy in range(h):
            for xx in range(w):
                if ap[xx, yy]:
                    fp[xx, yy] = qp[xx, yy]
                elif any(0 <= xx + dx < w and 0 <= yy + dy < h and ap[xx + dx, yy + dy]
                         for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    fp[xx, yy] = OUTLINE_RGB          # 실루엣 바깥 1칸 외곽선 (도트 느낌)
        flat.resize((w * PIXEL, h * PIXEL), Image.NEAREST).save(os.path.join(OUTDIR, f"{clip}_{k:02d}.png"))


def main():
    if "--no-render" not in sys.argv:
        render()
    os.makedirs(OUTDIR, exist_ok=True)

    # 서있는 클립: idle 0번 프레임 기준 캐릭터 높이 CHAR_H, 발바닥 = 아래에서 FOOT_PAD
    ref = bbox_of([os.path.join(RENDER, "idle_00.png")])
    s = CHAR_H / (ref[3] - ref[1])
    frames = to_lowres(STAND, STAND_W, STAND_H, ref, s, (STAND_W / 2, STAND_H - FOOT_PAD))

    # 누운 클립: 숨쉬기 전체 범위가 캔버스에 들어가게
    ref = bbox_of(glob.glob(os.path.join(RENDER, "sleep_*.png")))
    s = min((SLEEP_W - 2 * SLEEP_PAD) / (ref[2] - ref[0]), (SLEEP_H - 2 * SLEEP_PAD) / (ref[3] - ref[1]))
    frames.update(to_lowres(["sleep"], SLEEP_W, SLEEP_H, ref, s, (SLEEP_W / 2, SLEEP_H - SLEEP_PAD)))
    pixelize(frames)
    for c in STAND + ["sleep"]:
        print(f"{c}: {N} frames")


if __name__ == "__main__":
    main()
