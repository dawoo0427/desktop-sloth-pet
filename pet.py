# -*- coding: utf-8 -*-
"""
데스크탑 펫 (Desktop Pet) - 나무늘보
- 캐릭터: 기분별 애니메이션 클립(frames/{clip}_*.png) — 눈 깜빡/통통/놀람/갸웃
- 평소: 화면(모든 모니터)을 랜덤으로 느긋하게 배회
- 키: Ctrl=마우스 따라오기 토글 / Ctrl+1=제자리 정지 토글 / Ctrl+9=현재 위치 날씨 알려주기
- Ctrl+0=거대 나무늘보 소환(독립 창, 우측하단 누운 모습, 여러 마리 가능) / Ctrl+00(더블탭)=눕힘<->일어서기
- 거대 나무늘보도 메인 펫들과 공존하며 같은 커맨드(따라오기/정지)로 움직임
- 여러 번 실행해도 서로 겹치지 않게 떨어져 배치/이동
- 힘이 나는 좋은 말만 말풍선으로 건넴(자동 줄바꿈으로 안 잘림)
- 클릭하면 배 아래 말풍선 검색창 -> 검색 결과를 머리 위 말풍선으로 / 드래그로 이동 / 우클릭 메뉴
  (검색: 구글 AI=Gemini 구글검색 그라운딩만 사용. 우클릭 'Gemini 키 설정'에서 무료 키 입력)
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
import threading

TRANSPARENT = "magenta"   # 이 색은 화면에서 투명 처리됨 (프레임 배경색)
FRAME_DIR = "frames"


def key_down(vk):
    """가상키코드 vk가 눌려있는지(창 포커스 무관 전역 감지). 윈도우 전용, 실패 시 False."""
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False


VK_CONTROL, VK_LCTRL, VK_RCTRL = 0x11, 0xA2, 0xA3
VK_0, VK_1, VK_9 = 0x30, 0x31, 0x39


# 날씨 (Open-Meteo) + 위치(ip-api.com), 둘 다 무료·API키 불필요.
# 위치 조회 실패 시 폴백 좌표(서울).
FALLBACK_CITY = "서울"
FALLBACK_LAT, FALLBACK_LON = 37.5665, 126.9780
# WMO 날씨 코드 -> 한글 설명 (Tkinter가 이모지를 흑백으로만 그려서 글자만 사용)
WEATHER_CODES = {
    0: "맑음", 1: "대체로 맑음", 2: "부분 흐림", 3: "흐림",
    45: "안개", 48: "서리 안개",
    51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
    56: "어는 이슬비", 57: "어는 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    66: "어는 비", 67: "어는 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈", 77: "싸락눈",
    80: "약한 소나기", 81: "소나기", 82: "강한 소나기",
    85: "소나기눈", 86: "강한 소나기눈",
    95: "뇌우", 96: "우박 뇌우", 99: "강한 우박 뇌우",
}


def _get_json(url, timeout=6):
    import urllib.request
    import json
    req = urllib.request.Request(url, headers={"User-Agent": "desktop-sloth-pet"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _korean_city(lat, lon):
    """위경도 -> 한글 도시명 (BigDataCloud 역지오코딩, 무료·키 불필요). 실패 시 None."""
    try:
        u = ("https://api.bigdatacloud.net/data/reverse-geocode-client"
             f"?latitude={lat}&longitude={lon}&localityLanguage=ko")
        d = _get_json(u)
        return d.get("city") or d.get("locality") or d.get("principalSubdivision") or None
    except Exception:
        return None


def _win_location(timeout=6):
    """Windows 위치 서비스(WiFi 기반)로 (위도, 경도) 반환 — IP보다 정확. 윈도우 전용.
    위치 서비스 꺼짐/권한 거부/미지원이면 None. (System.Device는 Windows PowerShell에 있음)"""
    import subprocess
    ps = (
        "Add-Type -AssemblyName System.Device;"
        "$w=New-Object System.Device.Location.GeoCoordinateWatcher;"
        f"[void]$w.TryStart($false,[TimeSpan]::FromSeconds({timeout}));"
        f"$n=0; while($w.Position.Location.IsUnknown -and $n -lt {timeout*5})"
        "{Start-Sleep -Milliseconds 200;$n++};"
        "$l=$w.Position.Location;"
        "if(-not $l.IsUnknown){[Console]::Out.Write(('{0},{1}' -f $l.Latitude,$l.Longitude))};"
        "$w.Stop()"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=timeout + 8,
                             creationflags=0x08000000)   # CREATE_NO_WINDOW
        s = (out.stdout or "").strip()
        if "," in s:
            lat, lon = s.split(",")[:2]
            return float(lat), float(lon)
    except Exception:
        pass
    return None


def _ip_location():
    """IP 기반 (위도, 경도). Windows 위치 실패 시 폴백 — 정확도 높은 제공자 우선."""
    def _ipinfo(d):
        loc = d.get("loc")
        if loc and "," in loc:
            a, b = loc.split(",")[:2]
            return float(a), float(b)
        return None
    providers = [
        ("https://ipinfo.io/json", _ipinfo),
        ("https://ipapi.co/json/",
         lambda d: (float(d["latitude"]), float(d["longitude"])) if d.get("latitude") is not None else None),
        ("http://ip-api.com/json/?fields=status,lat,lon",
         lambda d: (float(d["lat"]), float(d["lon"])) if d.get("status") == "success" else None),
    ]
    for url, parse in providers:
        try:
            r = parse(_get_json(url))
            if r:
                return r
        except Exception:
            continue
    return None


def fetch_location():
    """현재 실제 위치 (도시한글, 위도, 경도) 반환. 실패하면 None.
    1) Windows 위치 서비스(WiFi, 정확)  2) IP 기반 폴백. 한글 도시명=BigDataCloud 역지오코딩."""
    coord = _win_location() or _ip_location()
    if not coord:
        return None
    lat, lon = coord
    city = _korean_city(lat, lon) or "현재 위치"
    for suf in ("특별자치시", "특별자치도", "특별시", "광역시"):   # 서울특별시 -> 서울
        city = city.replace(suf, "")
    return city, lat, lon


def fetch_weather(loc=None):
    """현재 위치(loc=(도시,위도,경도))의 날씨 한 줄을 반환. loc 없으면 IP로 조회.
    실패하면 None. (stdlib urllib만 사용)"""
    import urllib.request
    import json
    if loc is None:
        loc = fetch_location()
    if loc:
        city, lat, lon = loc
    else:
        city, lat, lon = FALLBACK_CITY, FALLBACK_LAT, FALLBACK_LON   # 위치 못 찾으면 서울
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "desktop-sloth-pet"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.load(r)
        cw = data["current_weather"]
        temp = round(float(cw["temperature"]))
        desc = WEATHER_CODES.get(int(cw["weathercode"]), "흐림")
        wind = round(float(cw.get("windspeed", 0)))
        return f"{city} {desc} {temp}°C (바람 {wind}km/h)"
    except Exception:
        return None


# ---------- 구글 AI(Gemini) 검색 — 키 있으면 사용, 없으면 위키백과로 폴백 ----------
GEMINI_MODEL = "gemini-2.5-flash"   # 무료 등급 + 구글 검색 그라운딩 지원
GEMINI_SYSTEM = "너는 친절한 검색 비서야. 한국어로 군더더기 없이 2~3문장으로 핵심만 정확히 답해."


def _app_dir():
    """스크립트/exe가 있는 폴더(파워유저가 키 파일을 옆에 둘 때)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _config_dir():
    """항상 쓰기 가능한 사용자 설정 폴더(%APPDATA%\\DesktopSlothPet). 키 저장용."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "DesktopSlothPet")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def load_gemini_key():
    """Gemini 키: 환경변수(GEMINI_API_KEY/GOOGLE_API_KEY) 우선, 없으면 설정폴더/스크립트폴더의 키 파일."""
    for env in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(env)
        if v and v.strip():
            return v.strip()
    for d in (_config_dir(), _app_dir()):
        for name in ("gemini_key.txt", "google_key.txt"):
            p = os.path.join(d, name)
            try:
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        s = f.read().strip()
                    if s:
                        return s
            except Exception:
                pass
    return None


def save_gemini_key(key):
    """키를 설정폴더에 저장(빈 값이면 삭제). 성공 시 True."""
    p = os.path.join(_config_dir(), "gemini_key.txt")
    try:
        if key and key.strip():
            with open(p, "w", encoding="utf-8") as f:
                f.write(key.strip())
        elif os.path.exists(p):
            os.remove(p)
        return True
    except Exception:
        return False


def gemini_search(query, key):
    """Gemini(구글 AI) + 구글 검색 그라운딩으로 답변. 실패 시 None. (stdlib urllib만 사용)"""
    import urllib.request
    import json
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent")
    prompt = f"{GEMINI_SYSTEM}\n\n질문: {query}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "x-goog-api-key": key,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        cands = data.get("candidates") or []
        if not cands:
            return None
        parts = cands[0].get("content", {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
        return text or None
    except Exception:
        return None


def web_search(query):
    """검색: 구글 AI(Gemini, 구글 검색 그라운딩)만 사용. 키 없거나 실패 시 None.
    (stdlib urllib만 사용)"""
    q = (query or "").strip()
    if not q:
        return None
    key = load_gemini_key()
    if not key:
        return None
    return gemini_search(q, key)


GIANT_SCALE = 2            # Ctrl+0 거대 나무늘보 배율(기존 20에서 1/10로 축소)
GIANT_CAP = 6             # 한 프로세스에서 소환 가능한 거대 나무늘보 최대 수
DOUBLE_0_WINDOW = 0.40    # Ctrl+0 더블탭(=ctrl+00, 눕힘 토글) 인식 시간(초)


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

GIANT_LINES = ["나도 잘하고 있지?", "오늘도 화이팅!", "크지만 마음은 말랑~",
               "같이 쉬어가자~", "천천히 가도 괜찮아", "행복한 하루 보내!"]


def _round_rect(c, x0, y0, x1, y1, r, fill="", outline="", width=1):
    c.create_arc(x0, y0, x0 + 2 * r, y0 + 2 * r, start=90, extent=90, style="pieslice", fill=fill, outline=fill)
    c.create_arc(x1 - 2 * r, y0, x1, y0 + 2 * r, start=0, extent=90, style="pieslice", fill=fill, outline=fill)
    c.create_arc(x0, y1 - 2 * r, x0 + 2 * r, y1, start=180, extent=90, style="pieslice", fill=fill, outline=fill)
    c.create_arc(x1 - 2 * r, y1 - 2 * r, x1, y1, start=270, extent=90, style="pieslice", fill=fill, outline=fill)
    c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=fill)
    c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill, outline=fill)
    if outline:
        c.create_arc(x0, y0, x0 + 2 * r, y0 + 2 * r, start=90, extent=90, style="arc", outline=outline, width=width)
        c.create_arc(x1 - 2 * r, y0, x1, y0 + 2 * r, start=0, extent=90, style="arc", outline=outline, width=width)
        c.create_arc(x0, y1 - 2 * r, x0 + 2 * r, y1, start=180, extent=90, style="arc", outline=outline, width=width)
        c.create_arc(x1 - 2 * r, y1 - 2 * r, x1, y1, start=270, extent=90, style="arc", outline=outline, width=width)
        c.create_line(x0 + r, y0, x1 - r, y0, fill=outline, width=width)
        c.create_line(x0 + r, y1, x1 - r, y1, fill=outline, width=width)
        c.create_line(x0, y0 + r, x0, y1 - r, fill=outline, width=width)
        c.create_line(x1, y0 + r, x1, y1 - r, fill=outline, width=width)


def draw_speech_bubble(c, scx, y_anchor, text, win_w):
    """말풍선을 캔버스 c에 그림. 창 폭 안에서 자동 줄바꿈(긴 글도 안 잘림)."""
    maxw = max(110, win_w - 40)
    txt = c.create_text(scx, -100, text=text, anchor="center", width=maxw, justify="center",
                        font=("맑은 고딕", 11, "bold"), fill=DARK)
    bb = c.bbox(txt)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    pad = 9
    x0, x1 = scx - bw / 2 - pad, scx + bw / 2 + pad
    if x0 < 3:
        x1 += 3 - x0; x0 = 3
    if x1 > win_w - 3:
        x0 -= x1 - (win_w - 3); x1 = win_w - 3
    y1 = y_anchor
    y0 = y1 - bh - pad * 2
    if y0 < 3:
        d2 = 3 - y0; y0 += d2; y1 += d2
    cxm = (x0 + x1) / 2
    c.create_polygon(cxm - 8, y1, cxm + 8, y1, cxm, y1 + 11, fill="white", outline=DARK, width=2)
    _round_rect(c, x0, y0, x1, y1, 10, fill="white", outline=DARK, width=2)
    c.create_line(cxm - 8, y1, cxm + 8, y1, fill="white", width=3)
    c.coords(txt, cxm, (y0 + y1) / 2)
    c.tag_raise(txt)


class GiantSloth:
    """독립 창 거대 나무늘보. 메인 펫들과 공존, 같은 커맨드(Ctrl=따라오기/Ctrl+1=정지).
    - 누우면: 엎드려 팔베개 자는 모습(정지) + 'Zzz' 말풍선
    - 일어서면: 일반 나무늘보처럼 깜빡/이동 + 응원 말풍선"""

    BUBBLE_H = 60               # 말풍선용 위쪽 여백

    def __init__(self, app, idx):
        self.app = app
        self.lying = True               # 처음 등장: 누운 모습
        self.dragging = False
        self.grab_dx = self.grab_dy = 0
        self.vx = self.vy = 0.0
        self.wtx = self.wty = None
        self.wtimer = 0
        self.t = 0
        self.fphase = 0.0
        self.mood = "idle"          # 서있을 때 기분(idle/happy/startled/curious) — 일반 펫과 동일
        self.mood_timer = 0
        self.say_text = ""
        self.say_timer = 0
        self.say_cd = random.randint(60, 160)

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        try:
            self.win.wm_attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=TRANSPARENT, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", lambda e: app.remove_giant(self))

        # 처음 위치: 주 모니터 우측 하단 (여러 마리면 조금씩 어긋나게)
        cw, ch = self._content_size()
        off = (idx % GIANT_CAP) * 36
        self.x = float(app.pw - cw - 20 - off)
        self.y = float(app.ph - (ch + self.BUBBLE_H) - 20 - off)
        self._relayout()
        self._draw()

    # 현재 표시 이미지 (누움=숨쉬기, 서있음=기분별 모션: 깜빡/통통/놀람/갸웃)
    def _stand_clip(self):
        clips = self.app.giant_clips
        return clips.get(self.mood) or clips["idle"]

    def _cur_img(self):
        if self.lying:
            fr = self.app.giant_sleep_frames
            return fr[int(self.fphase) % len(fr)]
        fr = self._stand_clip()
        return fr[int(self.fphase) % len(fr)]

    def _content_size(self):
        # 누움=숨쉬기 프레임 크기 / 서있음=클립 프레임 크기(모든 기분 동일)
        img = self.app.giant_sleep_frames[0] if self.lying else self.app.giant_clips["idle"][0]
        return img.width(), img.height()

    def set_mood(self, mood, timer=0):
        changed = (mood != self.mood)
        self.mood = mood
        if changed and mood in ("happy", "startled"):
            self.fphase = 0.0          # 반응 클립은 처음부터 재생
        if timer:
            self.mood_timer = timer

    def _relayout(self):
        cw, ch = self._content_size()
        self.cw, self.ch = cw, ch
        self.win_w = cw
        self.win_h = ch + self.BUBBLE_H
        self.canvas.config(width=self.win_w, height=self.win_h)
        self.win.geometry(f"{self.win_w}x{self.win_h}+{int(self.x)}+{int(self.y)}")

    def _draw(self):
        c = self.canvas
        c.delete("all")
        img = self._cur_img()
        c.create_image(self.win_w / 2, self.BUBBLE_H, image=img, anchor="n")
        if self.say_timer > 0 and self.say_text:
            draw_speech_bubble(c, self.win_w / 2, self.BUBBLE_H + self.ch * 0.14,
                               self.say_text, self.win_w)

    def toggle_lie(self):
        """눕힘 <-> 일어서기. 바닥(발 위치) 기준 유지."""
        bx = self.x + self.win_w / 2          # 가로 중심
        by = self.y + self.win_h              # 바닥
        self.lying = not self.lying
        self.mood = "idle"
        self.mood_timer = 0
        self.say_text = ""
        self.say_timer = 0
        self.say_cd = random.randint(40, 120)
        cw, ch = self._content_size()
        self.x = bx - cw / 2
        self.y = by - (ch + self.BUBBLE_H)
        self._relayout()
        self._draw()

    def _press(self, e):
        self.dragging = True
        self.grab_dx = self.win.winfo_pointerx() - self.x
        self.grab_dy = self.win.winfo_pointery() - self.y
        if not self.lying:                  # 서 있을 때 클릭 -> 좋아서 통통(happy)
            self.set_mood("happy", 46)
            self.say_text = random.choice(("반가워!", "헤헤 좋아!", "고마워~"))
            self.say_timer = 80

    def _drag(self, e):
        self.x = self.win.winfo_pointerx() - self.grab_dx
        self.y = self.win.winfo_pointery() - self.grab_dy
        self.win.geometry(f"+{int(self.x)}+{int(self.y)}")

    def _release(self, e):
        self.dragging = False
        self.vx = self.vy = 0.0

    def _wander(self):
        app = self.app
        if self.wtimer <= 0:
            if random.random() < 0.3:
                self.wtx = self.wty = None
                self.wtimer = random.randint(40, 100)
            else:
                self.wtx = random.uniform(app.vsx + 10, app.vsx + app.vsw - self.win_w - 10)
                self.wty = random.uniform(app.vsy + 10, app.vsy + app.vsh - self.win_h - 10)
                self.wtimer = random.randint(80, 180)
        self.wtimer -= 1
        if self.wtx is None:
            if self.mood != "happy" and self.mood_timer == 0:
                self.set_mood("idle")           # 쉬는 중 -> 깜빡
            return
        dx, dy = self.wtx - self.x, self.wty - self.y
        d = math.hypot(dx, dy)
        if d < 8:
            self.wtimer = 0
            if self.mood != "happy" and self.mood_timer == 0:
                self.set_mood("idle")
        else:
            self.vx += dx / d * 0.28
            self.vy += dy / d * 0.28
            if self.mood != "happy" and self.mood_timer == 0:
                self.set_mood("curious")        # 이동 중 -> 갸웃

    def _talk(self):
        if self.lying:
            self.say_text = "Z" + "z" * ((self.t // 8) % 3)   # Zzz 천천히
            self.say_timer = 2
        elif self.say_timer > 0:
            self.say_timer -= 1
        else:
            self.say_cd -= 1
            if self.say_cd <= 0:
                self.say_text = random.choice(GIANT_LINES)
                self.say_timer = 90
                self.say_cd = random.randint(140, 300)

    def update(self, slow):
        app = self.app
        if slow:
            self.t += 1
            self._talk()
            if self.t % 90 == 0:          # 화면 밖 사라짐 방지(모니터 구성 변경/최상위 가로채기)
                try:
                    self.win.wm_attributes("-topmost", True)
                    self.win.lift()
                except Exception:
                    pass
                self.x = max(app.vsx - self.win_w * 0.25,
                             min(app.vsx + app.vsw - self.win_w * 0.75, self.x))
                self.y = max(app.vsy, min(app.vsy + app.vsh - self.win_h, self.y))
                self.win.geometry(f"+{int(self.x)}+{int(self.y)}")
            if self.mood_timer > 0:
                self.mood_timer -= 1
            if not self.dragging and not self.lying and not app.frozen:
                # 일어서 있을 때만 이동 + 일반 나무늘보와 똑같은 기분별 모션
                if app.follow_on:
                    px, py = app.root.winfo_pointerx(), app.root.winfo_pointery()
                    cx, cy = self.x + self.win_w / 2, self.y + self.win_h / 2
                    dx, dy = px - cx, py - cy
                    d = math.hypot(dx, dy)
                    personal, follow = 150, 240    # 거대하니 일반보다 넉넉히
                    if d < personal:
                        self.set_mood("startled")  # 너무 가까우면 움찔
                    elif d > follow:
                        self.set_mood("curious")   # 멀면 갸웃하며 다가옴
                        self.vx += dx / d * 0.5
                        self.vy += dy / d * 0.5
                    elif self.mood != "happy" and self.mood_timer == 0:
                        self.set_mood("idle")
                else:
                    self._wander()
                self.vx *= 0.85
                self.vy *= 0.85
                cap = 7.0 if app.follow_on else 2.6
                sp = math.hypot(self.vx, self.vy)
                if sp > cap:
                    self.vx, self.vy = self.vx / sp * cap, self.vy / sp * cap
                self.x += self.vx
                self.y += self.vy
                self.x = max(app.vsx - self.win_w * 0.25,
                             min(app.vsx + app.vsw - self.win_w * 0.75, self.x))
                self.y = max(app.vsy, min(app.vsy + app.vsh - self.win_h, self.y))
                self.win.geometry(f"+{int(self.x)}+{int(self.y)}")
        # 애니메이션은 매 틱(60fps) 진행
        if self.lying:
            self.fphase += 0.22          # 세근세근 숨쉬기
        else:
            self.fphase += 0.5           # 기분별 모션(깜빡/통통/놀람/갸웃)
        self._draw()


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

        # 거대 나무늘보(Ctrl+0)용 정적 소스 (서있는/누운). pet.py가 zoom으로 확대.
        def _load_png(p, fb):
            try:
                return tk.PhotoImage(file=p) if os.path.exists(p) else fb
            except Exception:
                return fb
        # 누운(세근세근 숨쉬는) 모션 소스 frames/sleep_*.png
        self._sleep_srcs = [tk.PhotoImage(file=f) for f in
                            sorted(glob.glob(os.path.join(here, FRAME_DIR, "sleep_*.png")))] or [any_frames[0]]
        self.giant_sleep_frames = None   # 누운 숨쉬기 zoom 캐시
        self.giant_clips = None          # 서있는 기분별 클립(idle/happy/startled/curious) zoom 캐시
        self.giants = []                 # 소환된 거대 나무늘보(독립 창)들

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
        self.t = 0                  # 30fps 카운터(둥실 등)
        self.tick = 0               # 60fps 루프 카운터
        self.vx = 0.0               # 속도(virtual screen vsx/vsy 와 다름!)
        self.vy = 0.0
        self.mood = "idle"          # idle / curious / startled / happy
        self.mood_timer = 0
        self.hop = 0.0              # 점프 높이(위로 갈수록 음수)
        self.hop_v = 0.0

        # 이동/키 상태
        self.follow_on = False      # Ctrl 탭: 마우스 따라오기 ON/OFF (기본 OFF=배회) — 거대 펫도 공유
        self.frozen = False         # Ctrl+1: 제자리 정지 ON/OFF — 거대 펫도 공유
        self.wtx = None             # 배회 목표점
        self.wty = None
        self.wtimer = 0
        # 키 엣지 감지용 이전 상태
        self._p_ctrl = False
        self._p_k1 = False
        self._p_k0 = False
        self._p_k9 = False
        self._combo = False         # Ctrl 누른 동안 다른 키도 눌렸는지(순수 탭 구분)
        self._zero_pending = False  # Ctrl+0 단일/더블 구분 대기
        self._zero_time = 0.0

        # 말풍선
        self.say_text = ""
        self.say_timer = 0
        self.say_cooldown = random.randint(150, 350)

        # 날씨 (Ctrl+9로 조회, 백그라운드 스레드에서 받아옴)
        self._weather_loading = False
        self._weather_result = None      # 스레드가 채우면 메인 루프가 말풍선으로 출력
        self.weather_cache = ""          # 최근 조회 결과(가끔 혼잣말로 알려줌)
        self.weather_cache_time = 0.0
        self._loc = None                 # 실제 위치 캐시(한 번만 조회)
        self._weather_greet = False      # 이번 조회가 시작 인사인지

        # 드래그 / 클릭 판정
        self.dragging = False
        self.grab_dx = 0
        self.grab_dy = 0
        self._press_x = 0
        self._press_y = 0
        self._moved = False

        # 검색 (클릭 -> 배에 말풍선 검색창, 결과는 머리 위 말풍선)
        self.searching = False
        self._search_win = None
        self._search_entry = None

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="검색하기", command=self.toggle_search)
        self.menu.add_command(label="Gemini 키 설정(구글 AI 검색)", command=self.set_gemini_key)
        self.menu.add_command(label="안녕! 종료하기", command=self.root.destroy)

        # 실행 직후 현재 위치 날씨를 한 번 인사처럼 알려줌(창 뜬 뒤 잠깐 후)
        self.root.after(1800, lambda: self.request_weather(greet=True))
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

    # ---------- 날씨 (Ctrl+9 / 시작 인사) ----------
    GREET_TAILS = ["좋은 하루 보내!", "오늘도 화이팅!", "행복한 하루 되길~", "천천히 가도 괜찮아~"]

    def request_weather(self, greet=False):
        """현재 위치 날씨를 백그라운드 스레드로 조회. tkinter 루프는 안 멈춤.
        greet=True면 시작 인사용(끝에 응원 한마디 덧붙임)."""
        if self._weather_loading:
            return
        self._weather_loading = True
        self._weather_greet = greet
        self.say(text="오늘 날씨 살펴보는 중..." if greet else "현재 위치 날씨 확인 중...")
        threading.Thread(target=self._weather_worker, daemon=True).start()

    def _weather_worker(self):
        if self._loc is None:                 # 실제 위치는 최초 1회만 조회 후 캐시
            self._loc = fetch_location()
        txt = fetch_weather(self._loc)
        if txt:
            self.weather_cache = txt
            self.weather_cache_time = time.time()
            self._weather_result = (txt + " — " + random.choice(self.GREET_TAILS)) if self._weather_greet else txt
        else:
            self._weather_result = None if self._weather_greet else "날씨를 못 가져왔어… 인터넷 확인해줄래?"
        self._weather_loading = False

    # ---------- 입력 ----------
    def on_press(self, e):
        self.dragging = True
        self.grab_dx = self.root.winfo_pointerx() - self.x
        self.grab_dy = self.root.winfo_pointery() - self.y
        self._press_x = self.root.winfo_pointerx()
        self._press_y = self.root.winfo_pointery()
        self._moved = False

    def on_drag(self, e):
        px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
        if abs(px - self._press_x) > 4 or abs(py - self._press_y) > 4:
            self._moved = True
        self.x = px - self.grab_dx
        self.y = py - self.grab_dy
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    def on_release(self, e):
        self.dragging = False
        self.vx = self.vy = 0.0
        if not self._moved:             # 끌지 않은 '클릭' -> 검색창 토글
            self.toggle_search()

    def on_right(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    # ---------- Gemini(구글 AI) 키 설정 ----------
    def set_gemini_key(self):
        win = tk.Toplevel(self.root)
        win.title("Gemini API 키 설정")
        win.configure(bg="white")
        win.geometry("470x180")
        win.wm_attributes("-topmost", True)
        tk.Label(win, bg="white", fg=DARK, justify="left", font=("맑은 고딕", 9),
                 text=("구글 AI(Gemini) 검색을 쓰려면 무료 API 키가 필요해요.\n"
                       "aistudio.google.com → 'Get API key'에서 무료 발급 후\n"
                       "아래에 붙여넣고 저장하세요. (키 없으면 위키백과로 동작)")
                 ).pack(anchor="w", padx=12, pady=(10, 6))
        e = tk.Entry(win, font=("맑은 고딕", 10), show="•")
        cur = load_gemini_key()
        if cur:
            e.insert(0, cur)
        e.pack(fill="x", padx=12)
        e.focus_set()
        msg = tk.Label(win, text="", bg="white", fg=DARK, font=("맑은 고딕", 9))
        msg.pack(pady=4)

        def save(_=None):
            k = e.get().strip()
            ok = save_gemini_key(k)
            if not ok:
                msg.config(text="저장 실패 — 폴더 권한을 확인해줘.")
            elif k:
                msg.config(text="저장됐어요! 이제 검색이 구글 AI로 동작해요.")
            else:
                msg.config(text="키를 비웠어요 — 위키백과로 동작해요.")

        e.bind("<Return>", save)
        tk.Button(win, text="저장", command=save, font=("맑은 고딕", 10)).pack(pady=(2, 10))

    # ---------- 검색 (배에 말풍선 검색창 / 결과는 머리 위 말풍선) ----------
    def toggle_search(self):
        if self._search_win is not None:
            self.close_search()
        else:
            self.open_search()

    def open_search(self):
        if self._search_win is not None:
            return
        self.searching = True               # 입력하는 동안 배회 정지(자리 고정)
        self.set_mood("happy", 30)
        self.vx = self.vy = 0.0
        sw, sh = 280, 76
        cx = self.x + self.W / 2
        anchor_y = self.y + self.base_top + self.fh * 0.74   # 배 아래쪽(꼬리가 위로 배를 가리킴)
        win = tk.Toplevel(self.root)
        self._search_win = win
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        try:
            win.wm_attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        win.geometry(f"{sw}x{sh}+{int(cx - sw / 2)}+{int(anchor_y)}")
        c = tk.Canvas(win, width=sw, height=sh, bg=TRANSPARENT, highlightthickness=0)
        c.pack()
        _round_rect(c, 6, 18, sw - 6, sh - 6, 14, fill="white", outline=DARK, width=2)
        c.create_polygon(sw / 2 - 9, 19, sw / 2 + 9, 19, sw / 2, 4,       # 위로 향한 꼬리
                         fill="white", outline=DARK, width=2)
        c.create_line(sw / 2 - 9, 19, sw / 2 + 9, 19, fill="white", width=3)
        entry = tk.Entry(win, font=("맑은 고딕", 12), relief="flat", justify="center",
                         bg="white", fg=DARK, highlightthickness=0, bd=0)
        c.create_window(sw / 2, (18 + sh) / 2 + 1, window=entry, width=sw - 40, height=28)
        entry.bind("<Return>", self._search_submit)
        entry.bind("<Escape>", lambda ev: self.close_search())
        entry.focus_force()
        self._search_entry = entry
        self.say(text="무엇이든 찾아줄게! 입력하고 Enter~")

    def close_search(self):
        if self._search_win is not None:
            try:
                self._search_win.destroy()
            except Exception:
                pass
        self._search_win = None
        self._search_entry = None
        self.searching = False

    def _search_submit(self, e=None):
        q = self._search_entry.get().strip() if self._search_entry else ""
        self.close_search()
        if not q:
            return
        if not load_gemini_key():           # 구글 AI만 사용 — 키 없으면 안내
            self.say(text="구글 AI 키가 필요해! 우클릭 → 'Gemini 키 설정'에서 무료 키를 넣어줘.")
            self.say_timer = 360
            return
        self.say(text=f"'{q}' 구글 AI로 찾는 중...")
        holder = {}

        def worker():
            holder["r"] = web_search(q)

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if "r" not in holder:
                self.root.after(150, poll)
                return
            r = holder["r"]
            if r:
                if len(r) > 220:
                    r = r[:217] + "…"
                self.say(text=r)
                self.say_timer = 360         # 결과는 오래 보여줌
            else:
                self.say(text="흐음, 답을 못 받았어. 키/한도를 확인하거나 다시 물어봐줄래?")
        self.root.after(150, poll)

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

    # ---------- 화면 밖 사라짐 방지 (모니터 절전/해제·해상도 변경·최상위 가로채기) ----------
    def _refresh_on_screen(self):
        """가상 화면을 다시 구해 보이는 영역으로 끌어오고, '항상 위'를 재설정한다.
        시작 시 한 번 구한 vsx/vsw가 모니터 구성 변경으로 낡으면 펫이 사라진 모니터/
        화면 밖에 남는데(=사라짐), 주기적으로 호출해 현재 화면 안으로 되돌린다."""
        vs = virtual_screen()
        if vs:
            self.vsx, self.vsy, self.vsw, self.vsh = vs
        self.x = max(self.vsx - 30, min(self.vsx + self.vsw - self.W + 30, self.x))
        self.y = max(self.vsy, min(self.vsy + self.vsh - self.H, self.y))
        try:
            self.root.wm_attributes("-topmost", True)   # 다른 앱이 가로챈 최상위 복구
            self.root.lift()
        except Exception:
            pass
        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")

    # ---------- 메인 루프 (60fps: 애니메이션은 매 틱, 이동/물리는 30fps로 게이트) ----------
    def loop(self):
        self.tick += 1
        slow = (self.tick % 2 == 0)   # 이동·물리·타이머는 30fps 유지(기존 감각 보존)
        self._handle_keys()

        if slow:
            self.t += 1
            if self.t % 90 == 0:      # 약 3초마다 화면 안으로 + 항상 위 재설정
                self._refresh_on_screen()
            # 정지/드래그/검색 중이면 (메인 펫) 이동 로직 건너뜀
            if not self.dragging and not self.frozen and not self.searching:
                if self.follow_on:
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
                    elif self.mood != "happy" and self.mood_timer == 0:
                        self.set_mood("idle")
                else:
                    self._wander()

                sx, sy = self._separation()
                self.vx += sx
                self.vy += sy
                self.vx *= 0.85
                self.vy *= 0.85
                cap = 9.0 if self.follow_on else 3.2
                sp = math.hypot(self.vx, self.vy)
                if sp > cap:
                    self.vx, self.vy = self.vx / sp * cap, self.vy / sp * cap
                self.x += self.vx
                self.y += self.vy
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

            # 날씨 조회 결과가 도착하면 말풍선으로(스레드 -> 메인 루프)
            if self._weather_result is not None:
                self.say(text=self._weather_result)
                self._weather_result = None

            # 말풍선 타이머 + 가끔 혼잣말(가끔은 최근 날씨를 알려줌)
            if self.say_timer > 0:
                self.say_timer -= 1
            else:
                self.say_cooldown -= 1
                if self.say_cooldown <= 0 and self.mood in ("idle", "curious"):
                    fresh = self.weather_cache and (time.time() - self.weather_cache_time) < 1800
                    if fresh and random.random() < 0.2:
                        self.say(text="지금 " + self.weather_cache)
                    else:
                        self.say("idle")
            self._write_share()

        # 클립 프레임 진행(매 틱, 절반 속도 -> 같은 속도지만 60fps로 부드럽게)
        speed = math.hypot(self.vx, self.vy)
        energy = min(1.0, speed / 6.0)
        if self.mood == "startled":
            energy = max(energy, 1.0)
        elif self.mood == "curious":
            energy = max(energy, 0.55)
        elif self.mood == "happy":
            energy = max(energy, 0.7)
        self.fphase += 0.125 + energy * 0.425

        # 거대 나무늘보(독립 창)들 — 애니메이션 매 틱, 이동은 slow
        for g in list(self.giants):
            g.update(slow)

        self.draw()
        self.root.after(16, self.loop)

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

    # ---------- 키 토글 (Ctrl / Ctrl+1 / Ctrl+0 / Ctrl+9) ----------
    def _handle_keys(self):
        ctrl = key_down(VK_CONTROL)
        k1 = key_down(VK_1)
        k0 = key_down(VK_0)
        k9 = key_down(VK_9)

        if ctrl and not self._p_ctrl:
            self._combo = False
        if ctrl:
            # Ctrl 누른 동안 다른 키(숫자·C·V 등)가 같이 눌리면 '조합'으로 보고 follow 토글 제외
            for vk in range(0x08, 0xFF):
                if vk in (VK_CONTROL, VK_LCTRL, VK_RCTRL):
                    continue
                if key_down(vk):
                    self._combo = True
                    break

        # Ctrl+1: 제자리 정지 ON/OFF (메인·거대 펫 모두)
        if ctrl and k1 and not self._p_k1:
            self.frozen = not self.frozen
            self.vx = self.vy = 0.0
            self.set_mood("idle")
            self.say(text="여기 가만히 있을게!" if self.frozen else "다시 움직일게~")
        # Ctrl+0: (단일 탭)=거대 나무늘보 소환 / (더블탭=ctrl+00)=눕힘<->일어서기 토글
        if ctrl and k0 and not self._p_k0:
            now = time.time()
            if self._zero_pending and (now - self._zero_time) <= DOUBLE_0_WINDOW:
                self._zero_pending = False           # 더블탭 -> 눕힘 토글(소환 취소)
                self.toggle_giants_lie()
            else:
                self._zero_pending = True            # 일단 대기(더블탭인지 지켜봄)
                self._zero_time = now
        # 대기 중인 단일 0이 시간 지나면 소환 확정
        if self._zero_pending and (time.time() - self._zero_time) > DOUBLE_0_WINDOW:
            self._zero_pending = False
            self.summon_giant()
        # Ctrl+9: 대한민국 날씨 조회 -> 말풍선
        if ctrl and k9 and not self._p_k9:
            self.request_weather()
        # 순수 Ctrl 탭(다른 키 없이 눌렀다 뗌): 따라오기 ON/OFF
        if (not ctrl) and self._p_ctrl and not self._combo:
            self.follow_on = not self.follow_on
            self.say(text="좋아, 따라갈게!" if self.follow_on else "여기서 놀고 있을게~")

        self._p_ctrl, self._p_k1, self._p_k0, self._p_k9 = ctrl, k1, k0, k9

    # ---------- 거대 나무늘보 (독립 창, 공존·중복 소환) ----------
    def _zoom_all(self, frames):
        out = []
        for f in frames:
            try:
                out.append(f.zoom(GIANT_SCALE))
            except Exception:
                out.append(f)
        return out

    def _ensure_giant_imgs(self):
        if self.giant_sleep_frames is None:
            self.giant_sleep_frames = self._zoom_all(self._sleep_srcs)
        if self.giant_clips is None:
            # 서있을 때 일반 펫과 똑같은 기분별 모션을 쓰도록 모든 클립을 확대 캐시
            self.giant_clips = {name: self._zoom_all(frames) for name, frames in self.clips.items()}

    def summon_giant(self):
        if len(self.giants) >= GIANT_CAP:
            self.say(text="이미 가득 찼어! 우클릭으로 보내줘~")
            return
        self._ensure_giant_imgs()
        self.giants.append(GiantSloth(self, len(self.giants)))
        self.say(text="우오오~ 거대 나무늘보 등장!")

    def remove_giant(self, g):
        try:
            g.win.destroy()
        except Exception:
            pass
        if g in self.giants:
            self.giants.remove(g)

    def toggle_giants_lie(self):
        for g in self.giants:
            g.toggle_lie()

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
        draw_speech_bubble(c, scx, y_anchor, self.say_text, self.W)


if __name__ == "__main__":
    print("데스크탑 펫 실행 중... 마우스를 움직여보세요! (우클릭 -> 종료)")
    Pet()
