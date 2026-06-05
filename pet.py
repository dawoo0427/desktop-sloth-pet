# -*- coding: utf-8 -*-
"""
데스크탑 펫 (Desktop Pet) - 나무늘보
- 캐릭터: 기분별 애니메이션 클립(frames/{clip}_*.png) — 눈 깜빡/통통/놀람/갸웃
- 평소: 화면(모든 모니터)을 랜덤으로 느긋하게 배회
- Ctrl 키를 누르고 있으면: 마우스를 따라옴 (모니터 2·3번까지)
- 여러 번 실행해도 서로 겹치지 않게 떨어져 배치/이동
- 힘이 나는 좋은 말만 말풍선으로 건넴(자동 줄바꿈으로 안 잘림)
- 클릭하면 좋아서 폴짝 / 드래그로 이동 / 우클릭으로 종료
- 실행 시 외부 패키지 불필요(프레임은 build_frames.py로 미리 생성).
"""
import tkinter as tk
import math
import random
import os
import sys
import glob
import time
import atexit
import tempfile

TRANSPARENT = "magenta"   # 이 색은 화면에서 투명 처리됨 (프레임 배경색)
FRAME_DIR = "frames"


def ctrl_pressed():
    """Ctrl 키가 눌려있는지(창 포커스 무관 전역 감지). 윈도우 전용, 실패 시 False."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)  # VK_CONTROL
    except Exception:
        return False


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

        # 창 크기: 말풍선이 안 잘리게 가로를 넉넉히(캐릭터는 가운데 정렬), 위쪽은 말풍선 공간
        self.W = max(self.fw, 360)
        self.H = self.fh + 58
        self.base_top = self.H - self.fh             # 프레임 상단 y(기본)

        # 충돌/반응 기준점: 얼굴 부근(창 가운데 = 캐릭터 가운데)
        self.cx_off = self.W / 2
        self.cy_off = self.base_top + self.fh * 0.33

        # 주 모니터(시작 참고) + 전체 가상 화면(모든 모니터) — vsx/vsy/vsw/vsh (속도 vx/vy와 이름 분리!)
        self.pw = self.root.winfo_screenwidth()
        self.ph = self.root.winfo_screenheight()
        vs = virtual_screen()
        if vs:
            self.vsx, self.vsy, self.vsw, self.vsh = vs
        else:
            self.vsx, self.vsy, self.vsw, self.vsh = 0, 0, self.pw, self.ph

        # 중복 실행 인스턴스끼리 위치를 공유(겹침 방지). temp 폴더에 pid별 파일.
        self.pid = os.getpid()
        self.share_dir = os.path.join(tempfile.gettempdir(), "desktop_sloth_pets")
        try:
            os.makedirs(self.share_dir, exist_ok=True)
        except Exception:
            self.share_dir = None
        atexit.register(self._unregister)

        # 시작 위치: 다른 펫과 안 겹치게 랜덤 배치
        self.x, self.y = self._pick_spawn()
        self.root.geometry(f"{self.W}x{self.H}+{int(self.x)}+{int(self.y)}")

        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack()

        # 상태값
        self.t = 0
        self.vx = 0.0               # 속도(virtual screen vsx/vsy 와 다름!)
        self.vy = 0.0
        self.mood = "idle"          # idle / curious / startled / happy
        self.mood_timer = 0
        self.hop = 0.0              # 점프 높이(위로 갈수록 음수)
        self.hop_v = 0.0

        # 이동 모드: Ctrl 누르면 마우스 따라오기, 평소엔 랜덤 배회
        self.follow_mode = False
        self.wtx = None             # 배회 목표점
        self.wty = None
        self.wtimer = 0

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
        self._unregister()          # 종료 시 위치 공유 파일 정리

    # ---------- 대사 (힘이 나는 좋은 말만!) ----------
    LINES = {
        "idle": ["오늘도 잘하고 있어!", "넌 충분히 멋져!", "조금씩 가면 돼",
                 "넌 할 수 있어!", "지금도 충분히 잘하고 있어", "거의 다 왔어!",
                 "네 속도대로 가면 돼", "실수해도 괜찮아", "넌 생각보다 강해",
                 "오늘 하루도 수고했어", "잠깐 쉬어도 괜찮아", "넌 소중한 사람이야",
                 "좋은 일이 생길 거야", "깊게 숨 한 번, 후~", "잘 견뎌왔어, 대단해"],
        "happy": ["야호! 신난다!", "너랑 있으면 좋아!", "우리 최고야!",
                  "헤헤 행복해~", "넌 정말 멋져!"],
        "startled": ["우와, 반가워!", "히히 깜짝, 좋아!", "너라서 더 좋아!",
                     "꺄 행복해~"],
        "curious": ["같이 가자!", "내가 함께할게!", "어디든 따라갈게!",
                    "곁에 있어 줄게~", "넌 혼자가 아니야!"],
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
        self.follow_mode = (not self.dragging) and ctrl_pressed()

        if not self.dragging:
            if self.follow_mode:
                # Ctrl 누름: 마우스를 따라옴 (가까우면 반가워서 폴짝, 멀면 쫓아감)
                px = self.root.winfo_pointerx()
                py = self.root.winfo_pointery()
                cx = self.x + self.cx_off
                cy = self.y + self.cy_off
                dx, dy = px - cx, py - cy
                dist = math.hypot(dx, dy)
                personal, follow = 90, 200
                if dist < personal:
                    self.set_mood("startled")
                    if self.hop == 0 and self.hop_v == 0:
                        self.hop_v = -6
                elif dist > follow:
                    self.set_mood("curious")
                    self.vx += dx / dist * 0.55
                    self.vy += dy / dist * 0.55
                elif self.mood not in ("happy",) and self.mood_timer == 0:
                    self.set_mood("idle")
            else:
                # 평소: 화면을 랜덤으로 느긋하게 배회
                self._wander()

            # 다른 펫과 안 겹치게 서로 밀어내기(두 모드 공통)
            sx, sy = self._separation()
            self.vx += sx
            self.vy += sy

            self.vx *= 0.85
            self.vy *= 0.85
            cap = 9.0 if self.follow_mode else 3.2   # 따라올 땐 빠르게, 배회는 느긋
            sp = math.hypot(self.vx, self.vy)
            if sp > cap:
                self.vx, self.vy = self.vx / sp * cap, self.vy / sp * cap

            self.x += self.vx
            self.y += self.vy

            # 전체 가상 화면(모든 모니터) 범위로 제한 — 모니터 2·3번까지 이동
            self.x = max(self.vsx - 30, min(self.vsx + self.vsw - self.W + 30, self.x))
            self.y = max(self.vsy, min(self.vsy + self.vsh - self.H, self.y))
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

        self._write_share()         # 내 위치를 다른 펫에게 알림(겹침 방지용)
        self.draw()
        self.root.after(33, self.loop)

    # ---------- 배회 / 겹침 방지 (중복 실행 인스턴스 간 위치 공유) ----------
    def _share_path(self):
        return os.path.join(self.share_dir, f"{self.pid}.txt")

    def _write_share(self):
        if not self.share_dir:
            return
        cx = self.x + self.cx_off
        cy = self.y + self.cy_off
        try:
            with open(self._share_path(), "w") as f:
                f.write(f"{cx} {cy} {self.W} {self.H}")
        except Exception:
            pass

    def _unregister(self):
        try:
            if self.share_dir:
                os.remove(self._share_path())
        except Exception:
            pass

    def _siblings(self):
        """다른 살아있는 펫들의 (중심x, 중심y, 폭, 높이) 목록."""
        out = []
        if not self.share_dir:
            return out
        now = time.time()
        try:
            files = os.listdir(self.share_dir)
        except Exception:
            return out
        for fn in files:
            if not fn.endswith(".txt") or fn == f"{self.pid}.txt":
                continue
            p = os.path.join(self.share_dir, fn)
            try:
                if now - os.path.getmtime(p) > 2.5:   # 멈춘(죽은) 인스턴스는 무시+정리
                    try:
                        os.remove(p)
                    except Exception:
                        pass
                    continue
                with open(p) as f:
                    a = f.read().split()
                out.append((float(a[0]), float(a[1]), float(a[2]), float(a[3])))
            except Exception:
                continue
        return out

    def _separation(self):
        """겹치거나 너무 가까운 다른 펫에게서 멀어지는 힘."""
        ax = ay = 0.0
        mcx = self.x + self.cx_off
        mcy = self.y + self.cy_off
        for (sx, sy, sw, sh) in self._siblings():
            dx, dy = mcx - sx, mcy - sy
            d = math.hypot(dx, dy)
            rng = (self.fw + sw * 0.4) * 0.7        # 몸이 겹칠 만한 거리
            if d < 0.5:
                ax += random.uniform(-1.0, 1.0); ay += random.uniform(-1.0, 1.0)
            elif d < rng:
                f = (rng - d) / rng * 1.8
                ax += dx / d * f; ay += dy / d * f
        return ax, ay

    def _pick_spawn(self):
        """다른 펫과 안 겹치는 랜덤 시작 위치."""
        pad = 24
        x0, x1 = self.vsx + pad, self.vsx + self.vsw - self.W - pad
        y0, y1 = self.vsy + pad, self.vsy + self.vsh - self.H - pad
        if x1 < x0:
            x1 = x0
        if y1 < y0:
            y1 = y0
        sibs = self._siblings()
        best, bestmin = (x0, y0), -1.0
        for _ in range(80):
            x = random.uniform(x0, x1)
            y = random.uniform(y0, y1)
            if not sibs:
                return x, y
            cx, cy = x + self.cx_off, y + self.cy_off
            mind = min(math.hypot(cx - sx, cy - sy) for (sx, sy, sw, sh) in sibs)
            if mind > self.fw * 1.1:                # 충분히 떨어졌으면 채택
                return x, y
            if mind > bestmin:
                bestmin, best = mind, (x, y)
        return best

    def _wander(self):
        """화면을 느긋하게 랜덤 배회(가끔 멈춰 쉼)."""
        if self.wtimer <= 0:
            if random.random() < 0.25:
                self.wtx = self.wty = None          # 잠깐 쉼
                self.wtimer = random.randint(40, 90)
            else:
                pad = 24
                self.wtx = random.uniform(self.vsx + pad, self.vsx + self.vsw - self.W - pad)
                self.wty = random.uniform(self.vsy + pad, self.vsy + self.vsh - self.H - pad)
                self.wtimer = random.randint(80, 170)
        self.wtimer -= 1

        if self.wtx is None:
            if self.mood not in ("happy",) and self.mood_timer == 0:
                self.set_mood("idle")
            return
        dx, dy = self.wtx - self.x, self.wty - self.y
        d = math.hypot(dx, dy)
        if d < 8:
            self.wtimer = 0                          # 도착 -> 다음 목표
            if self.mood not in ("happy",) and self.mood_timer == 0:
                self.set_mood("idle")
        else:
            self.vx += dx / d * 0.30
            self.vy += dy / d * 0.30
            if self.mood not in ("happy",) and self.mood_timer == 0:
                self.set_mood("curious")

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
        # 창 폭 안에서 자동 줄바꿈 -> 긴 글도 안 잘림
        maxw = max(120, self.W - 40)
        txt = c.create_text(scx, -100, text=self.say_text, anchor="center",
                            width=maxw, justify="center",
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
