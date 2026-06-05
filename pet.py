# -*- coding: utf-8 -*-
"""
데스크탑 펫 (Desktop Pet) - 마우스에 반응하는 나무늘보
- 캐릭터: 바탕화면 그림을 가공한 애니메이션 프레임(frames/pet_*.png) 사용
  · 팔다리가 팔랑팔랑 흔들림(미리 렌더한 프레임을 번갈아 표시)
- 마우스가 멀면 호기심에 다가오고, 너무 가까우면 깜짝 놀라 도망감
- 둥실둥실 / 클릭하면 좋아서 폴짝 / 드래그로 이동 / 우클릭으로 종료
- 가끔 혼잣말 말풍선. 실행 시 외부 패키지 불필요(프레임은 build_frames.py로 미리 생성).
"""
import tkinter as tk
import math
import random
import os
import sys
import glob

TRANSPARENT = "magenta"   # 이 색은 화면에서 투명 처리됨 (프레임 배경색)
FRAME_DIR = "frames"


def resource_dir():
    """리소스(frames) 위치. PyInstaller exe로 묶이면 임시 추출폴더(_MEIPASS), 아니면 스크립트 폴더."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def virtual_screen():
    """모든 모니터를 합친 '가상 화면' 영역 (left, top, width, height).
    윈도우 멀티모니터 지원 — 보조 모니터가 오른쪽/왼쪽/위/아래 어디든(좌표 음수 가능) 포함.
    실패하면(다른 OS 등) None."""
    try:
        import ctypes
        u = ctypes.windll.user32
        x = u.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        y = u.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        w = u.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        h = u.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    return None

DARK   = "#46301F"   # 말풍선 테두리/글자
SHADOW = "#4E3826"   # 바닥 그림자


class Pet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)             # 창 테두리 없음
        self.root.wm_attributes("-topmost", True)    # 항상 위
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass  # Windows 외 환경 대비

        # 애니메이션 클립 로드 (기분별 60프레임). 각 프레임은 완성된 한 장.
        here = resource_dir()
        self.clips = {}
        for name in ("idle", "happy", "startled", "curious"):
            cf = sorted(glob.glob(os.path.join(here, FRAME_DIR, f"{name}_*.png")))
            if cf:
                self.clips[name] = [tk.PhotoImage(file=f) for f in cf]
        if not self.clips:
            # 구버전 호환: pet_*.png 가 있으면 idle 로 사용
            cf = sorted(glob.glob(os.path.join(here, FRAME_DIR, "pet_*.png")))
            if cf:
                self.clips["idle"] = [tk.PhotoImage(file=f) for f in cf]
        if not self.clips:
            raise SystemExit("프레임이 없습니다. 먼저 build_frames.py 를 실행하세요.")
        any_frames = next(iter(self.clips.values()))
        self.fw = any_frames[0].width()
        self.fh = any_frames[0].height()
        self.fphase = 0.0

        # 창 크기: 프레임 + 위쪽 말풍선 공간
        self.W = self.fw
        self.H = self.fh + 44
        self.base_top = self.H - self.fh             # 프레임 상단 y(기본)

        # 충돌/반응 기준점: 얼굴 부근
        self.cx_off = self.W / 2
        self.cy_off = self.base_top + self.fh * 0.33

        # 주 모니터 크기(시작 위치용) + 전체 가상 화면(모든 모니터, 이동 범위용)
        self.pw = self.root.winfo_screenwidth()
        self.ph = self.root.winfo_screenheight()
        vs = virtual_screen()
        if vs:
            self.vx, self.vy, self.vw, self.vh = vs
        else:
            self.vx, self.vy, self.vw, self.vh = 0, 0, self.pw, self.ph

        # 시작 위치: 주 모니터 우하단
        self.x = float(self.pw - self.W - 120)
        self.y = float(self.ph - self.H - 120)
        self.root.geometry(f"{self.W}x{self.H}+{int(self.x)}+{int(self.y)}")

        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack()

        # 상태값
        self.t = 0
        self.vx = 0.0
        self.vy = 0.0
        self.mood = "idle"          # idle / curious / startled / happy
        self.mood_timer = 0
        self.hop = 0.0              # 점프 높이(위로 갈수록 음수)
        self.hop_v = 0.0

        # 말풍선
        self.say_text = ""
        self.say_timer = 0
        self.say_cooldown = random.randint(150, 350)

        # 드래그
        self.dragging = False
        self.grab_dx = 0
        self.grab_dy = 0

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="안녕! 종료하기", command=self.root.destroy)

        self.loop()
        self.root.mainloop()

    # ---------- 대사 ----------
    LINES = {
        "idle": ["심심해~", "오늘 날씨 좋다", "흠흠~", "뭐 하고 있어?",
                 "졸려...", "같이 놀자!", "히히", "딴짓 그만! ...농담이야",
                 "물 마셨어?", "잠깐 쉬어가자~"],
        "happy": ["헤헤 좋아!", "또 해줘!", "신난다!", "야호~"],
        "startled": ["으악!", "깜짝이야!", "너무 가까워!", "헉!"],
        "curious": ["어디 가?", "기다려~", "같이 가!", "응?"],
    }

    def say(self, mood=None, text=None):
        if text is None:
            text = random.choice(self.LINES.get(mood or self.mood, self.LINES["idle"]))
        self.say_text = text
        self.say_timer = 90
        self.say_cooldown = random.randint(180, 420)

    # ---------- 입력 ----------
    def on_press(self, e):
        self.dragging = True
        self.grab_dx = self.root.winfo_pointerx() - self.x
        self.grab_dy = self.root.winfo_pointery() - self.y
        self.set_mood("happy", 30)
        self.hop_v = -7
        self.say("happy")

    def on_drag(self, e):
        self.x = self.root.winfo_pointerx() - self.grab_dx
        self.y = self.root.winfo_pointery() - self.grab_dy
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    def on_release(self, e):
        self.dragging = False
        self.vx = self.vy = 0.0

    def on_right(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    # ---------- 무드 ----------
    def set_mood(self, mood, timer=0):
        changed = (mood != self.mood)
        self.mood = mood
        if changed and mood in ("happy", "startled") and mood in self.clips:
            self.fphase = 0.0          # 반응 클립은 처음부터 재생
        if timer:
            self.mood_timer = timer
        if changed and self.say_timer == 0 and self.say_cooldown <= 0:
            if mood == "startled" and random.random() < 0.7:
                self.say("startled")
            elif mood == "curious" and random.random() < 0.4:
                self.say("curious")

    # ---------- 메인 루프 ----------
    def loop(self):
        self.t += 1
        px = self.root.winfo_pointerx()
        py = self.root.winfo_pointery()

        cx = self.x + self.cx_off
        cy = self.y + self.cy_off
        dx = px - cx
        dy = py - cy
        dist = math.hypot(dx, dy)

        if not self.dragging:
            personal = 95
            follow = 280

            if dist < personal:
                self.set_mood("startled")
                if dist > 1:
                    self.vx += -dx / dist * 1.4
                    self.vy += -dy / dist * 1.4
                if self.hop == 0 and self.hop_v == 0:
                    self.hop_v = -6
            elif dist > follow:
                self.set_mood("curious")
                self.vx += dx / dist * 0.45
                self.vy += dy / dist * 0.45
            elif self.mood not in ("happy",) and self.mood_timer == 0:
                self.set_mood("idle")

            self.vx *= 0.85
            self.vy *= 0.85
            sp = math.hypot(self.vx, self.vy)
            if sp > 9:
                self.vx, self.vy = self.vx / sp * 9, self.vy / sp * 9

            self.x += self.vx
            self.y += self.vy

            # 전체 가상 화면(모든 모니터) 범위로 제한 — 모니터 2·3번까지 따라감
            self.x = max(self.vx - 30, min(self.vx + self.vw - self.W + 30, self.x))
            self.y = max(self.vy, min(self.vy + self.vh - self.H, self.y))
            self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

        # 점프 물리
        if self.hop_v != 0 or self.hop != 0:
            self.hop += self.hop_v
            self.hop_v += 1.1
            if self.hop >= 0:
                self.hop = 0.0
                self.hop_v = 0.0

        if self.mood_timer > 0:
            self.mood_timer -= 1

        # 말풍선 타이머 + 가끔 혼잣말
        if self.say_timer > 0:
            self.say_timer -= 1
        else:
            self.say_cooldown -= 1
            if self.say_cooldown <= 0 and self.mood in ("idle", "curious"):
                self.say("idle")

        # 팔다리 흔들림 속도(에너지에 비례) -> 프레임 진행
        speed = math.hypot(self.vx, self.vy)
        energy = min(1.0, speed / 6.0)
        if self.mood == "startled":
            energy = max(energy, 1.0)
        elif self.mood == "curious":
            energy = max(energy, 0.55)
        elif self.mood == "happy":
            energy = max(energy, 0.7)
        self.fphase += 0.25 + energy * 0.85

        self.draw()
        self.root.after(33, self.loop)

    # ---------- 그리기 ----------
    def draw(self):
        c = self.canvas
        c.delete("all")
        scx = self.W / 2

        bob = math.sin(self.t * 0.12) * 1.5          # 둥실
        top = self.base_top + self.hop + bob

        # 바닥 그림자 (점프하면 작아짐)
        s = max(0.4, 1 - (-self.hop) / 90)
        sy = self.H - 8
        c.create_oval(scx - self.fw * 0.26 * s, sy - 4,
                      scx + self.fw * 0.26 * s, sy + 6,
                      fill=SHADOW, outline="")

        # 현재 기분에 맞는 클립의 프레임
        clip = self.mood if self.mood in self.clips else "idle"
        frames = self.clips[clip]
        idx = int(self.fphase) % len(frames)
        c.create_image(scx, top, image=frames[idx], anchor="n")

        # 말풍선
        if self.say_timer > 0 and self.say_text:
            self.draw_bubble(c, scx, top + self.fh * 0.16)

    def draw_bubble(self, c, scx, y_anchor):
        txt = c.create_text(scx, -100, text=self.say_text, anchor="center",
                            font=("맑은 고딕", 11, "bold"), fill=DARK)
        bb = c.bbox(txt)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        pad = 9
        x0, x1 = scx - bw / 2 - pad, scx + bw / 2 + pad
        if x0 < 3:
            x1 += 3 - x0; x0 = 3
        if x1 > self.W - 3:
            x0 -= x1 - (self.W - 3); x1 = self.W - 3
        y1 = y_anchor
        y0 = y1 - bh - pad * 2
        if y0 < 3:
            d2 = 3 - y0; y0 += d2; y1 += d2
        cxm = (x0 + x1) / 2
        c.create_polygon(cxm - 8, y1, cxm + 8, y1, cxm, y1 + 11,
                         fill="white", outline=DARK, width=2)
        self.round_rect(x0, y0, x1, y1, 10, fill="white", outline=DARK, width=2)
        c.create_line(cxm - 8, y1, cxm + 8, y1, fill="white", width=3)
        c.coords(txt, cxm, (y0 + y1) / 2)
        c.tag_raise(txt)

    def round_rect(self, x0, y0, x1, y1, r, fill="", outline="", width=1):
        c = self.canvas
        c.create_arc(x0, y0, x0 + 2 * r, y0 + 2 * r, start=90, extent=90,
                     style="pieslice", fill=fill, outline=fill)
        c.create_arc(x1 - 2 * r, y0, x1, y0 + 2 * r, start=0, extent=90,
                     style="pieslice", fill=fill, outline=fill)
        c.create_arc(x0, y1 - 2 * r, x0 + 2 * r, y1, start=180, extent=90,
                     style="pieslice", fill=fill, outline=fill)
        c.create_arc(x1 - 2 * r, y1 - 2 * r, x1, y1, start=270, extent=90,
                     style="pieslice", fill=fill, outline=fill)
        c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=fill)
        c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill, outline=fill)
        if outline:
            c.create_arc(x0, y0, x0 + 2 * r, y0 + 2 * r, start=90, extent=90,
                         style="arc", outline=outline, width=width)
            c.create_arc(x1 - 2 * r, y0, x1, y0 + 2 * r, start=0, extent=90,
                         style="arc", outline=outline, width=width)
            c.create_arc(x0, y1 - 2 * r, x0 + 2 * r, y1, start=180, extent=90,
                         style="arc", outline=outline, width=width)
            c.create_arc(x1 - 2 * r, y1 - 2 * r, x1, y1, start=270, extent=90,
                         style="arc", outline=outline, width=width)
            c.create_line(x0 + r, y0, x1 - r, y0, fill=outline, width=width)
            c.create_line(x0 + r, y1, x1 - r, y1, fill=outline, width=width)
            c.create_line(x0, y0 + r, x0, y1 - r, fill=outline, width=width)
            c.create_line(x1, y0 + r, x1, y1 - r, fill=outline, width=width)


if __name__ == "__main__":
    print("데스크탑 펫 실행 중... 마우스를 움직여보세요! (우클릭 -> 종료)")
    Pet()
