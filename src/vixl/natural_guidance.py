"""Advisory checks on explicitly supplied scene measurements (the craft texts they follow live in guidance.py).

Checks are conditional sanity checks, never an inference of anatomy or lighting from pixels.
"""

from .automation import bounded_object
from .errors import require
from .model import finite

PALETTES = {
    "skin": ["#321b17", "#61382c", "#96654b", "#c18e70", "#e3b69b", "#f3d6bd"],
    "foliage": ["#172b20", "#34482c", "#536b39", "#78964b", "#bac678"],
    "sky": ["#355a85", "#5984b2", "#91b4d2", "#cad9df", "#edf0e9"],
    "earth": ["#342d26", "#62503a", "#8b7051", "#b09570", "#d0bea0"],
    "water": ["#142f42", "#285165", "#4e7882", "#8fafaf", "#d4e0d8"],
    "stone": ["#33353b", "#5a5a60", "#838184", "#ada9a3", "#d8d0c2"],
}

JOINTS = {"elbow": (0, 155), "knee": (0, 145), "shoulder": (0, 185), "hip": (0, 130), "wrist": (0, 90)}
ACTIONS = {"guide-check": ({"spec"}, {"spec"}), "perspective-guides": ({"spec"}, {"spec"}),
           "figure-plan": ({"spec"}, {"spec"}), "pattern-list": (set(), set()), "pattern-check": ({"name"}, {"name"})}
FIELD_TYPES = {"spec": {"type": "object", "description": "Explicit measured scene metadata or construction settings; read matching guidance."},
               "name": {"type": "string", "description": "Document custom pattern name to inspect for boundary seams."}}


def natural_palette(subject="foliage", time="day"):
    from .colors import parse
    require(subject in PALETTES, "Unknown natural subject", allowed=sorted(PALETTES))
    require(time in ("day", "dawn", "dusk", "night"), "Time must be day, dawn, dusk or night")
    # Simple artistic illumination adaptation; no claim of spectral/material correctness.
    multipliers = {"day": (1,1,1), "dawn": (1.08,.85,.73), "dusk": (.91,.76,.91), "night": (.36,.46,.68)}[time]
    values = []
    for value in PALETTES[subject]:
        rgb = parse(value)[:3]
        values.append("#" + "".join(f"{min(255,max(0,round(c*m*255))):02x}" for c,m in zip(rgb,multipliers)))
    return {"subject":subject,"time":time,"colors":values,"basis":"Illustrative sRGB palette; adapt to observed illumination"}


def _point(value, name):
    require(isinstance(value,list) and len(value)==2,f"{name} must be [x,y]")
    return [finite(v,name,-1e9,1e9) for v in value]


def check(spec):
    require(isinstance(spec,dict),"Check spec must be an object")
    kind = spec.get("kind")
    require(kind in ("lighting","anatomy","perspective","illustration"),"Unknown guidance check kind")
    findings = []
    def warn(code, message, index=None):
        findings.append({"code":code,"message":message,**({"index":index} if index is not None else {})})
    if kind == "lighting":
        from .colors import parse, to_linear
        light = _point(spec.get("light"),"light")
        objects = spec.get("objects",[])
        require(isinstance(objects,list) and len(objects)<=512,"At most 512 lighting objects")
        for i,obj in enumerate(objects):
            position = _point(obj.get("position"),"position")
            if "shadow" in obj:
                direction = _point(obj["shadow"],"shadow")
                toward = [light[j]-position[j] for j in (0,1)]
                if sum(a*b for a,b in zip(toward,direction))>0:
                    warn("shadow-toward-light","Cast shadow points toward the nominated point source",i)
            if "lit" in obj and "shade" in obj:
                def luminance(value):
                    return sum(w*to_linear(c) for w,c in zip((.2126,.7152,.0722),parse(value)[:3]))
                if luminance(obj["lit"])+.02 < luminance(obj["shade"]):
                    warn("inverted-light-value","Lit patch is darker than its corresponding shadow; verify material/fill assumptions",i)
    elif kind == "anatomy":
        heads = finite(spec.get("head_units",7.5),"head_units",1,30)
        style = spec.get("style","realistic")
        require(style in ("realistic","stylized"),"Unknown anatomy style")
        if style == "realistic" and not 3.5 <= heads <= 9:
            warn("head-proportion","Outside broad child/adult construction ranges; check age and intended stylization")
        joints,limbs = spec.get("joints",[]),spec.get("limbs",[])
        require(isinstance(joints,list) and len(joints)<=256 and isinstance(limbs,list) and len(limbs)<=256,"Too many anatomy measurements")
        for i,joint in enumerate(joints):
            name = joint.get("name")
            require(name in JOINTS,"Joint must name an anatomical flexion measurement",allowed=sorted(JOINTS))
            angle = finite(joint.get("angle"),"joint angle",-360,360)
            if not JOINTS[name][0] <= angle <= JOINTS[name][1]:
                warn("joint-range",f"{name} flexion lies outside loose reference band {JOINTS[name]}",i)
        for i,limb in enumerate(limbs):
            ratio = finite(limb.get("upper"),"upper length",.001,1e6)/finite(limb.get("lower"),"lower length",.001,1e6)
            if style == "realistic" and not .55 <= ratio <= 1.8:
                warn("limb-ratio","Upper/lower limb ratio is unusual; check foreshortening and intended body plan",i)
    elif kind == "perspective":
        horizon = finite(spec.get("horizon"),"horizon",-1e6,1e6)
        tolerance = finite(spec.get("tolerance",2),"tolerance",0,1000)
        vanishing,objects = spec.get("vanishing",[]),spec.get("objects",[])
        require(isinstance(vanishing,list) and len(vanishing)<=3 and isinstance(objects,list) and len(objects)<=512,"Too many perspective samples")
        for i,point in enumerate(vanishing):
            if abs(_point(point,"vanishing point")[1]-horizon)>tolerance:
                warn("inconsistent-horizon","Horizontal edge-family vanishing point is off the nominated horizon",i)
        products = [finite(o.get("depth"),"depth",.001,1e9)*finite(o.get("size"),"size",.001,1e9) for o in objects]
        if products:
            reference = sorted(products)[len(products)//2]
            for i,value in enumerate(products):
                if abs(value/reference-1)>.2:
                    warn("inconsistent-depth-scale","Equal-world-size objects should have approximately constant projected size × depth",i)
    else:
        values = spec.get("values",[])
        require(isinstance(values,list) and 2 <= len(values)<=256,"Provide 2–256 value samples")
        values = [finite(v,"value",0,1) for v in values]
        if max(values)-min(values)<.2:
            warn("flat-values","Narrow value range; inspect focal contrast and intended low-contrast style")
        if finite(spec.get("silhouette_contrast",1),"silhouette_contrast",0,1)<.15:
            warn("weak-silhouette","Silhouette contrast is low against the background")
    return {"kind":kind,"findings":findings,"passed":not findings,"advisory":True,
            "scope":"Checks supplied measurements only; visual inspection and intended stylization remain necessary"}


def perspective_guides(spec):
    bounded_object(spec,{"width","height","horizon","points","vanishing","depths","reference_size","reference_depth"},"Unknown perspective setting")
    w,h = finite(spec.get("width",1000),"width",1,16384),finite(spec.get("height",1000),"height",1,16384)
    horizon = finite(spec.get("horizon",h/2),"horizon",-1e6,1e6)
    points = spec.get("points",2)
    require(points in (1,2,3),"Perspective points must be 1, 2 or 3")
    op = {"type":"grid","name":"perspective","kind":"perspective","points":points,"horizon":horizon,"region":[0,0,w,h]}
    if "vanishing" in spec:
        require(isinstance(spec["vanishing"],list) and 1 <= len(spec["vanishing"]) <= 3,"Choose 1–3 vanishing points")
        op["vanishing"] = [_point(v,"vanishing") for v in spec["vanishing"]]
    reference = finite(spec.get("reference_size",100),"reference_size",.001,1e6)
    depth = finite(spec.get("reference_depth",1),"reference_depth",.001,1e6)
    depths = spec.get("depths",[1,2,4])
    require(isinstance(depths,list) and len(depths)<=256,"At most 256 depths")
    return {"operations":[op],"sizes":[{"depth":d,"size":reference*depth/finite(d,"depth",.001,1e6)} for d in depths]}


def figure_plan(spec):
    bounded_object(spec,{"name","height","head_units","width_ratio","x","y","color"},"Unknown figure setting")
    name = spec.get("name","figure")
    require(isinstance(name,str) and name and len(name)<=64,"Invalid figure name")
    height = finite(spec.get("height",600),"height",40,10000)
    heads = finite(spec.get("head_units",7.5),"head_units",3,12)
    width = finite(spec.get("width_ratio",1),"width_ratio",.5,2)
    x,y = finite(spec.get("x",0),"x",-1e6,1e6),finite(spec.get("y",0),"y",-1e6,1e6)
    head = height/heads
    # Side-separated limbs keep silhouette legible; all parts remain ordinary editable shapes.
    parts = {"head":(.95,.0,.9,1,"ellipse"),"torso":(.45,1.1,1.9,1.65,"rectangle"),
             "pelvis":(.6,2.8,1.6,.8,"rectangle"),"left-arm":(.05,1.25,.35,2.7,"rectangle"),
             "right-arm":(2.4,1.25,.35,2.7,"rectangle"),"left-leg":(.62,3.65,.65,heads-3.65,"rectangle"),
             "right-leg":(1.55,3.65,.65,heads-3.65,"rectangle")}
    require(heads>3.65,"Head units must exceed 3.65 for this separated-limb template")
    operations = []
    for part,(px,py,pw,ph,shape) in parts.items():
        operations.append({"type":"shape","name":f"{name}-{part}","shape":shape,"x":x+px*head*width,"y":y+py*head,
                           "width":max(1,round(pw*head*width)),"height":max(1,round(ph*head)),"fill":spec.get("color","#916b56")})
    operations.append({"type":"group","name":name,"targets":[o["name"] for o in operations]})
    return {"operations":operations,"parts":{part:f"{name}-{part}" for part in parts},"head_units":heads,
            "next_steps":"Adjust gesture/proportions from references, split articulated limbs, then define the character rig pivots."}


def dispatch(session, action, request, document=None):
    if action == "guide-check":
        return check(request["spec"])
    if action == "perspective-guides":
        return perspective_guides(request["spec"])
    if action == "figure-plan":
        return figure_plan(request["spec"])
    from .textures import catalog,seamless_check
    if action == "pattern-list" and document is None:
        return catalog()
    with session.project(document=document) as project:
        if action == "pattern-list":
            return catalog(project)
        patterns = project.state.get("patterns",{})
        require(request["name"] in patterns,"Unknown custom pattern")
        return seamless_check(project.image(patterns[request["name"]]["asset"]))
