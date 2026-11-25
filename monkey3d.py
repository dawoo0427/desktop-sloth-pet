"""귀여운 3D 원숭이 친구 모델 + 클립 렌더 (Blender 전용 스크립트, sloth3d.py 와 같은 방식).

실행은 build_frames_3d.py 가 대신 해 준다:
  blender -b --factory-startup -P monkey3d.py -- <출력폴더> [클립,클립,...] [프레임수]

포인트: 하트 모양 살구색 얼굴 / 큰 동그란 귀 / 머리 위 속이 빈 하트 앞머리(털 두 가닥) / 말린 꼬리 / 긴 팔 / 만화풍 외곽선.
각 프레임은 투명 배경 RGBA PNG 로 렌더 -> build_frames_3d.py 가 축소·마젠타 평탄화.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.join(os.path.dirname(bpy.data.filepath or __file__), "render3d")
CLIPS = argv[1].split(",") if len(argv) > 1 else ["idle", "happy", "startled", "curious", "sleep"]
N = int(argv[2]) if len(argv) > 2 else 60
RES = 768
TOON_GAIN = 0.75   # 셀 셰이딩 입력 배율 (밝은/중간/그림자 경계 위치 조절)

# ---------------- 팔레트 (원본 픽셀아트 색) ----------------
def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (1.0,)

PAL = {
    "fur": "#8A5634", "mask": "#F7D3AE", "belly": "#F3C9A0", "earin": "#F2B39A",
    "eye": "#1B1411", "nose": "#6B3F26", "leaf": "#7CC243",
    "stem": "#5EA332", "line": "#5A3A1E", "leafline": "#2E6B1E", "white": "#FFFFFF",
    "iris": "#5A3522", "blush": "#F59C9C", "mouthin": "#6B2A22", "tongue": "#F28C8C",
}

# ---------------- 씬 초기화 ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = RES
scene.render.resolution_y = RES
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
try:
    scene.eevee.taa_render_samples = 32
except AttributeError:
    pass

world = bpy.data.worlds.new("W")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.85, 0.85, 0.9, 1)
bg.inputs[1].default_value = 0.55


def _sock(node, ident, out=False):
    return next(x for x in (node.outputs if out else node.inputs) if x.identifier == ident)


def material(name, color, rough=0.75, emit=0.0, outline=False, plush=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = lin(color)
    p.inputs["Roughness"].default_value = rough
    if plush:  # 가장자리로 갈수록 밝아지는 보송한 인형 털 + 미세 털결
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.25
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MIX"
        h = color.lstrip("#")
        light = "#" + "".join(f"{round(int(h[i:i + 2], 16) * 0.6 + c * 0.4):02X}"
                              for i, c in zip((0, 2, 4), (255, 244, 226)))
        _sock(mx, "A_Color").default_value = lin(color)
        _sock(mx, "B_Color").default_value = lin(light)
        nt.links.new(lw.outputs["Facing"], _sock(mx, "Factor_Float"))
        nt.links.new(_sock(mx, "Result_Color", out=True), p.inputs["Base Color"])
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 70
        nz.inputs["Detail"].default_value = 6
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = 0.12
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], p.inputs["Normal"])
        p.inputs["Sheen Weight"].default_value = 0.4
    if emit:
        p.inputs["Emission Color"].default_value = lin(color)
        p.inputs["Emission Strength"].default_value = emit
    if not outline and not emit:  # 픽셀아트 느낌의 셀 셰이딩: 명암 3단계로 뚝뚝 끊기
        for n in list(nt.nodes):
            if n.type != "OUTPUT_MATERIAL":
                nt.nodes.remove(n)
        out = nt.nodes["Material Output"]
        dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
        s2r = nt.nodes.new("ShaderNodeShaderToRGB")
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = TOON_GAIN
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        cr.interpolation = "CONSTANT"
        cr.elements[0].position, cr.elements[0].color = 0.0, (0.64, 0.63, 0.66, 1)
        cr.elements[1].position, cr.elements[1].color = 0.33, (0.8, 0.8, 0.8, 1)
        e3 = cr.elements.new(0.72)
        e3.color = (1.0, 1.0, 1.0, 1)
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MULTIPLY"
        _sock(mx, "Factor_Float").default_value = 1.0
        _sock(mx, "A_Color").default_value = lin(color)
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(dif.outputs[0], s2r.inputs[0])
        nt.links.new(s2r.outputs["Color"], bw.inputs[0])
        nt.links.new(bw.outputs[0], mul.inputs[0])
        nt.links.new(mul.outputs[0], ramp.inputs[0])
        nt.links.new(ramp.outputs["Color"], _sock(mx, "B_Color"))
        nt.links.new(_sock(mx, "Result_Color", out=True), em.inputs[0])
        nt.links.new(em.outputs[0], out.inputs[0])
        return m
    if outline:  # 뒤집힌 껍데기 외곽선: 앞면 컬링 대신 뒷면 컬링 + 단색 발광
        nt.nodes.remove(p)
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs[0].default_value = lin(color)
        # 외곽선 껍데기가 그림자를 드리우면 머리에 얼룩이 생김 -> 그림자 광선엔 투명
        lp = nt.nodes.new("ShaderNodeLightPath")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Shadow Ray"], mx.inputs[0])
        nt.links.new(e.outputs[0], mx.inputs[1])
        nt.links.new(tr.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], nt.nodes["Material Output"].inputs[0])
        m.use_backface_culling = True
        m.use_backface_culling_shadow = True
        m.use_transparent_shadow = True
    return m

M = {k: material(k, v) for k, v in PAL.items()}
M["eye"] = material("eye_gloss", PAL["eye"], rough=0.2)
M["iris"] = material("iris_gloss", PAL["iris"], rough=0.2)
M["blush"] = material("blush_soft", PAL["blush"])
for k in ("fur", "mask", "belly"):
    M[k] = material(k + "_plush", PAL[k], plush=True)
M["white"] = material("hi", PAL["white"], emit=2.0)
M["leaf"] = material("leaf_m", PAL["leaf"], rough=0.55)
OUTLINE = material("ol", PAL["line"], outline=True)
OUTLINE_G = material("olg", PAL["leafline"], outline=True)


def upd():
    bpy.context.view_layer.update()


def empty(name, loc, parent=None):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    upd()
    if parent:
        attach(o, parent)
    return o


def attach(o, parent):
    upd()
    o.parent = parent
    o.matrix_parent_inverse = parent.matrix_world.inverted()


def finish(o, mat, parent, outline=None, thick=0.03, subsurf=1):
    o.data.materials.append(mat)
    for poly in o.data.polygons:
        poly.use_smooth = True
    if subsurf:
        s = o.modifiers.new("sub", "SUBSURF")
        s.levels = s.render_levels = subsurf
    if outline:
        o.data.materials.append(outline)
        so = o.modifiers.new("outline", "SOLIDIFY")
        so.thickness = thick
        so.offset = 1.0
        so.use_flip_normals = True
        so.use_rim = False
        so.material_offset = 1
    if parent:
        attach(o, parent)
    return o


def sphere(name, loc, scale, mat, parent, outline=OUTLINE, thick=0.03, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    o.rotation_euler = rot
    return finish(o, mat, parent, outline, thick)


def claw(name, base, direction, length, radius, parent):
    """뭉툭한 크림색 손/발톱 (원뿔)."""
    return cone(name, base, direction, length, radius, parent, M["claw"], 0.012)


def cone(name, base, direction, length, radius, parent, mat, thick=0.016):
    d = Vector(direction).normalized()
    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=radius, radius2=radius * 0.25,
                                    depth=length, location=Vector(base) + d * length / 2)
    o = bpy.context.active_object
    o.name = name
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d)
    return finish(o, mat, parent, OUTLINE, thick)


def curve(name, pts, bevel, mat, parent):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    ctr = sum((Vector(c) for c in pts), Vector()) / len(pts)
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*(Vector(c) - ctr), 1)
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.location = ctr
    o.data.materials.append(mat)
    if parent:
        attach(o, parent)
    return o


def arc(cx, cz, y_of, half_w, depth, n=14):
    """x∈[cx-half_w, cx+half_w] 포물선. depth>0 이면 가운데가 아래(웃는 입/감은 눈)."""
    pts = []
    for i in range(n):
        u = -1 + 2 * i / (n - 1)
        x = cx + u * half_w
        z = cz - depth * (1 - u * u)
        pts.append((x, y_of(x, z), z))
    return pts

# ---------------- 모델링 (정면 = -Y) ----------------
# 늘보와 같은 2등신 인형 비율 + 긴 팔·하트 얼굴·큰 귀·말린 꼬리
root = empty("root", (0, 0, 0))


def on_ell(c, a, x, z, lift=0.0):
    """타원체(중심 c, 반지름 a) 앞면(-Y) 표면의 y + lift 만큼 앞으로."""
    v = 1 - ((x - c.x) / a.x) ** 2 - ((z - c.z) / a.z) ** 2
    return c.y - a.y * math.sqrt(max(v, 0.0)) - lift


sphere("body", (0, 0, 0.72), (0.44, 0.38, 0.54), M["fur"], root)
sphere("belly", (0, -0.215, 0.68), (0.3, 0.2, 0.4), M["belly"], root, outline=None)

legs = {}
for side, sx in (("L", 1), ("R", -1)):
    hip = empty(f"hip_{side}", (0.18 * sx, 0, 0.34), root)
    sphere(f"leg_{side}", (0.18 * sx, -0.02, 0.19), (0.14, 0.15, 0.19), M["fur"], hip)
    sphere(f"foot_{side}", (0.19 * sx, -0.1, 0.05), (0.13, 0.15, 0.06), M["mask"], hip)   # 살구색 발
    legs[side] = hip

shoulders = {}
for side, sx in (("L", 1), ("R", -1)):
    sh = empty(f"shoulder_{side}", (0.36 * sx, -0.02, 1.04), root)
    sphere(f"arm_{side}", (0.45 * sx, -0.04, 0.72), (0.1, 0.11, 0.38), M["fur"], sh,
           rot=(0, math.radians(-10 * sx), 0))                                   # 원숭이라 팔이 길어요
    tilt = math.radians(10)
    sphere(f"hand_{side}", ((0.45 + 0.36 * math.sin(tilt)) * sx, -0.05, 0.72 - 0.36 * math.cos(tilt)),
           (0.1, 0.1, 0.09), M["mask"], sh)                                       # 살구색 손
    shoulders[side] = sh

# 말린 꼬리 (몸 뒤 오른쪽에서 나와 옆으로 동그랗게 말림)
tail = empty("tail", (-0.3, 0.25, 0.42), root)
pts = []
for i in range(40):
    u = i / 39
    if u < 0.45:                                   # 옆으로 뻗어 올라가는 줄기
        v = u / 0.45
        pts.append((-0.3 - 0.42 * v, 0.25 + 0.05 * v, 0.42 + 0.3 * v * v))
    else:                                          # 끝은 동그랗게 말림
        a = (u - 0.45) / 0.55 * 1.6 * math.pi
        r = 0.15 * (1 - 0.45 * (u - 0.45) / 0.55)
        pts.append((-0.72 - r * math.sin(a), 0.3, 0.72 + 0.15 - r * math.cos(a) - 0.0))
curve("tail_c", pts, 0.042, M["fur"], tail)

head = empty("head", (0, 0, 1.08), root)
HC, HS = Vector((0, 0, 1.64)), Vector((0.6, 0.52, 0.55))
sphere("headball", HC, HS, M["fur"], head)

# 큰 동그란 귀 (안쪽 살구색)
ears = {}
for side, sx in (("L", 1), ("R", -1)):
    ep = empty(f"earpiv_{side}", (0.55 * sx, 0, 1.66), head)
    sphere(f"ear_{side}", (0.7 * sx, 0.02, 1.66), (0.2, 0.08, 0.2), M["fur"], ep)
    sphere(f"earin_{side}", (0.72 * sx, -0.04, 1.66), (0.13, 0.04, 0.13), M["earin"], ep, outline=None)
    ears[side] = ep

# 하트 모양 살구색 얼굴: 눈 쪽 두 봉우리 + 아래 주둥이
LOBES = [(Vector((0.19 * sx, -0.3, 1.71)), Vector((0.25, 0.26, 0.24))) for sx in (1, -1)]
for i, (c, a) in enumerate(LOBES):
    sphere(f"mask_lobe{i}", c, a, M["mask"], head, outline=None)
MC, MS = Vector((0, -0.34, 1.49)), Vector((0.38, 0.26, 0.24))
sphere("mask", MC, MS, M["mask"], head, outline=None)


def on_mask(x, z, lift=0.0):
    return on_ell(MC, MS, x, z, lift)


def on_lobe(x, z, lift=0.0):
    c, a = LOBES[0] if x >= 0 else LOBES[1]
    return on_ell(c, a, x, z, lift)


# 머리 위 하트 앞머리: 머리에서 나온 털 두 가닥이 양옆으로 말려 올라가 위에서 만나는 속이 빈 하트
TOP = HC.z + HS.z - 0.04
HK = 0.012                                    # 하트 크기 (폭 약 0.38)


def heart_pt(t):
    x = 16 * math.sin(t) ** 3
    z = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
    return (x * HK, -0.04, TOP + 0.01 + (z + 17) * HK)     # 하트 아래 끝(z=-17)이 정수리에 닿음


for j, (t0, t1) in enumerate(((math.pi, 0.0), (math.pi, 2 * math.pi))):   # 아래 끝 -> 위 오목점, 왼/오른 가닥
    pts = [heart_pt(t0 + (t1 - t0) * i / 23) for i in range(24)]
    curve(f"hair_strand{j}", pts, 0.032, M["fur"], head).visible_shadow = False

EYE_Z = 1.7
face = {"open": [], "happy": [], "sleep": [], "blink": []}
for side, sx in (("L", 1), ("R", -1)):
    ex = 0.19 * sx
    sf = on_lobe(ex, EYE_Z)
    piv = empty(f"eyepiv_{side}", (ex, sf - 0.02, EYE_Z), head)
    parts = [
        sphere(f"pupil_{side}", (ex, sf - 0.01, EYE_Z), (0.092, 0.05, 0.106), M["eye"], piv, outline=None),
        sphere(f"hi_{side}", (ex + 0.032, sf - 0.06, EYE_Z + 0.038), (0.037, 0.014, 0.037), M["white"], piv, outline=None),
    ]
    face["open"] += parts
    face["blink"].append(piv)
    yo = lambda x, z: on_lobe(x, z, 0.035)
    face["happy"].append(curve(f"happy_{side}", arc(ex, EYE_Z - 0.03, yo, 0.07, -0.05), 0.015, M["eye"], head))
    face["sleep"].append(curve(f"sleep_{side}", arc(ex, EYE_Z, yo, 0.07, 0.04), 0.013, M["eye"], head))
    bx_, bz_ = 0.32 * sx, 1.52
    sphere(f"blush_{side}", (bx_, on_ell(LOBES[0][0] if sx > 0 else LOBES[1][0], LOBES[0][1], bx_, 1.58) + 0.02, bz_),
           (0.09, 0.03, 0.055), M["blush"], head, outline=None)
    nx = 0.045 * sx
    sphere(f"nostril_{side}", (nx, on_mask(nx, 1.55) + 0.006, 1.55), (0.028, 0.02, 0.022), M["nose"], head, outline=None)

ym = lambda x, z: on_mask(x, z, 0.01)
mouth = curve("mouth", arc(0, 1.45, ym, 0.1, 0.04), 0.011, M["line"], head)     # 미소
face["happy"].append(sphere("mouth_open", (0, on_mask(0, 1.45) + 0.012, 1.45), (0.09, 0.03, 0.065),
                            M["mouthin"], head, outline=None))
face["happy"].append(sphere("tongue", (0, on_mask(0, 1.42) - 0.004, 1.42), (0.055, 0.02, 0.03),
                            M["tongue"], head, outline=None))
upd()


def ear_wiggle(deg):
    """꼬리 살랑 + 귀 까딱 (늘보의 새싹 살랑 대신)."""
    rot(tail, "y", deg * 1.2)
    for side, sx in (("L", 1), ("R", -1)):
        rot(ears[side], "y", -sx * deg * 0.4)


# 바닥(홀드아웃): z=0 아래를 투명하게 잘라냄 -> 누운 늘보의 배가 바닥에 평평하게 닿아 보임
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
GROUND = bpy.context.active_object
GROUND.name = "ground_holdout"
_gm = bpy.data.materials.new("holdout")
_gm.use_nodes = True
_gm.node_tree.nodes.remove(_gm.node_tree.nodes["Principled BSDF"])
_gm.node_tree.links.new(_gm.node_tree.nodes.new("ShaderNodeHoldout").outputs[0],
                        _gm.node_tree.nodes["Material Output"].inputs[0])
GROUND.data.materials.append(_gm)
GROUND.visible_shadow = False
GROUND.hide_render = True

# ---------------- 조명/카메라 ----------------
def sun(name, rot, energy, color=(1, 1, 1)):
    d = bpy.data.lights.new(name, "SUN")
    d.energy = energy
    d.color = color
    d.angle = math.radians(15)
    o = bpy.data.objects.new(name, d)
    bpy.context.collection.objects.link(o)
    o.rotation_euler = [math.radians(a) for a in rot]
    return o

sun("key", (50, 0, -30), 1.7, (1.0, 0.97, 0.92))
sun("fill", (70, 0, 50), 0.5, (0.9, 0.95, 1.0))
sun("rim", (-60, 0, 160), 1.5)

target = empty("target", (0, 0, 1.3))
cam_d = bpy.data.cameras.new("cam")
cam_d.type = "ORTHO"
cam_d.ortho_scale = 3.7
cam = bpy.data.objects.new("cam", cam_d)
bpy.context.collection.objects.link(cam)
YAW, EL, DIST = math.radians(0), math.radians(7), 12
cam.location = (DIST * math.sin(YAW) * math.cos(EL) * -1, -DIST * math.cos(YAW) * math.cos(EL), 1.3 + DIST * math.sin(EL))
tc = cam.constraints.new("TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"
scene.camera = cam

# ---------------- 포즈 ----------------
REST = {o.name: (o.location.copy(), o.rotation_euler.copy(), o.scale.copy())
        for o in bpy.data.objects if o.type == "EMPTY" or o in face["blink"] or o == mouth}


def reset():
    for name, (l, r, s) in REST.items():
        o = bpy.data.objects[name]
        o.location, o.rotation_euler, o.scale = l.copy(), r.copy(), s.copy()
    root.matrix_basis = Matrix.Identity(4)
    show("open")
    GROUND.hide_render = True


def show(state):
    for k, objs in face.items():
        if k == "blink":
            continue
        for o in objs:
            o.hide_render = (k != state)
    mouth.hide_render = (state == "happy")


def blink_amt(k, start, length=6):
    """start 프레임부터 length 동안 감았다 뜸. 1=뜸, ~0.1=감음."""
    if start <= k < start + length:
        u = (k - start) / (length - 1)
        return 1 - 0.9 * math.sin(math.pi * u)
    return 1.0


def set_blink(a):
    for e in face["blink"]:
        e.scale.z = REST[e.name][2].z * a
    for o in face["open"]:
        if o.name.startswith("hi_"):
            o.hide_render = a < 0.5


def rot(o, axis, deg):
    o.rotation_euler["xyz".index(axis)] += math.radians(deg)


def squash(sy):
    root.scale = (1 / math.sqrt(sy), 1 / math.sqrt(sy), sy)


def pose(clip, k):
    reset()
    t = k / N
    w = 2 * math.pi * t
    if clip == "idle":
        squash(1 + 0.018 * math.sin(w * 2))
        rot(head, "y", 2.5 * math.sin(w))
        ear_wiggle(7 * math.sin(w * 2))
        for side, sx in (("L", 1), ("R", -1)):
            rot(shoulders[side], "y", -sx * (3 + 2 * math.sin(w * 2)))
        set_blink(blink_amt(k, 40))
    elif clip == "happy":
        show("happy")
        b = abs(math.sin(w * 2))                       # 통통 2회
        squash(1 - 0.07 * math.cos(w * 4))
        root.location.z = 0.08 * b
        for side, sx in (("L", 1), ("R", -1)):
            rot(shoulders[side], "y", -sx * (120 + 20 * math.sin(w * 4)))   # 만세 흔들기
        ear_wiggle(15 * math.sin(w * 4))
    elif clip == "startled":
        decay = math.exp(-4 * t)
        root.location.x = 0.025 * math.sin(w * 9) * decay
        squash(1 - 0.1 * math.exp(-10 * t) + 0.04 * decay * math.sin(w * 6))
        for side, sx in (("L", 1), ("R", -1)):
            rot(shoulders[side], "y", -sx * (168 * (1 - math.exp(-14 * t)) * (0.6 + 0.4 * decay)))
        for e in face["blink"]:
            e.scale = REST[e.name][2] * 1.25
        ear_wiggle(25 * math.sin(w * 9) * decay)
    elif clip == "curious":
        tilt = 13 * math.sin(w)
        rot(head, "y", tilt)
        root.rotation_euler.y = math.radians(-3 * math.sin(w))
        ear_wiggle(-tilt * 0.8)
        rot(shoulders["L"], "y", -(10 + 8 * max(0, math.sin(w))))
        set_blink(blink_amt(k, 22))
    elif clip == "sleep":
        sleep_pose(w)


def _aim(pos, direction, thick=1.0):
    """피벗을 pos 에 두고 팔/다리의 아래쪽(로컬 -Z)이 direction 을 향하게 하는 월드 행렬."""
    q = Vector((0, 0, -1)).rotation_difference(Vector(direction).normalized())
    return Matrix.Translation(pos) @ q.to_matrix().to_4x4() @ Matrix.Diagonal((thick, thick, 1, 1))


def _aim_flat(pos, direction, wide, tall):
    """바닥에 수평으로 눕힌 팔: 로컬 -Z -> direction(수평), 로컬 Y -> 위, 로컬 X -> 수평 옆.
    wide=옆 두께 배율, tall=위아래 두께 배율 (tall<wide 이면 바닥에 눌린 듯 납작)."""
    d = Vector(direction).normalized()
    z = -d
    x = Vector((0, 0, 1)).cross(z).normalized()
    y = z.cross(x)
    rotm = Matrix((x, y, z)).transposed().to_4x4()
    return Matrix.Translation(pos) @ rotm @ Matrix.Diagonal((wide, tall, 1, 1))


def sleep_pose(w):
    """엎드려 팔베개 (원본 누운늘보.png 구도).
    - 배: 몸통을 바닥(z=0)에 살짝 묻고 GROUND(홀드아웃)로 잘라 배 아랫면이 평평하게 바닥에 닿음
    - 팔: 머리 뒤 어깨에서 V자로 앞 가운데로 모여 턱 밑에서 두 손이 포개짐
    - 다리: 몸통 뒤쪽 바닥에 수평으로 놓이고 발톱은 뒤(+X)를 향함"""
    show("sleep")
    GROUND.hide_render = False
    breath = 1 + 0.03 * math.sin(w)
    R = Matrix(((0, 0, -1), (-1, 0, 0), (0, 1, 0))).to_4x4()   # 로컬Z->-X, 로컬-Y->-Z
    LONG, THICK, WIDE = 1.3, 0.95, 1.15                         # 바닥에 눌려 납작하고 넓게 퍼진 몸통
    root.matrix_basis = (Matrix.Translation((1.34, 0.12, 0.24)) @ R
                         @ Matrix.Diagonal((WIDE, THICK * breath, LONG, 1)))
    upd()
    # 앞팔(아주 통통): 배처럼 바닥에 납작하게 눌려 수평. 턱 앞을 좌우에서 가로질러 가운데서 만남
    ARM_Z = 0.17                                              # 두 팔 같은 높이 -> 수평, 아래는 GROUND가 잘라 평평
    shoulders["L"].matrix_world = _aim_flat((-1.13, -0.3, ARM_Z), (1.0, -0.12, 0.0), 2.05, 1.6)
    shoulders["R"].matrix_world = _aim_flat((0.11, -0.3, ARM_Z), (-1.0, -0.12, 0.0), 2.05, 1.6)
    # 뒷다리: 몸통 하단(배 아래)에서 바닥을 따라 뒤로 뻗음, 발끝(로컬 -Y)이 뒤(+X)를 향함
    for side, y in (("L", -0.3), ("R", 0.3)):
        legs[side].matrix_world = (Matrix.Translation((1.0, y, 0.27 + 0.004 * math.sin(w)))
                                   @ Matrix.Rotation(math.radians(90), 4, "Z")
                                   @ Matrix.Diagonal((1, 1.4, 0.85, 1)))   # 뒤로 길쭉, 바닥에 납작
    # 머리: 포갠 손 위에 턱을 얹음 (정면 바라봄, 살짝 기울임)
    head.matrix_world = (Matrix.Translation((-0.5, 0.06, 0.21 + 0.012 * math.sin(w)))
                         @ Matrix.Rotation(math.radians(-6), 4, "Y"))
    ear_wiggle(4 * math.sin(w))


os.makedirs(OUT, exist_ok=True)
for clip in CLIPS:
    for k in range(N):
        pose(clip, k)
        upd()
        scene.render.filepath = os.path.join(OUT, f"{clip}_{k:02d}.png")
        bpy.ops.render.render(write_still=True)
    print(f"[monkey3d] {clip}: {N} frames")
print("[monkey3d] done")
