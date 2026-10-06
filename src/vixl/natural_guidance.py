"""On-demand visual craft guidance and advisory checks on explicitly supplied scene measurements.

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
GUIDANCE = {
"natural-color-light": """Natural color and lighting: working reference
Color is reflected illumination, not a fixed label. A foliage palette includes cool occlusion, muted local green, warm transmitted leaf edges and sky-reflecting highlights. Skin varies continuously in value, chroma and undertone; choose from observation and never infer identity from a swatch. Stone/wood/water depend on roughness, view angle and surrounding light. Use natural_palette or vixl_color natural with subject skin/foliage/sky/earth/water/stone and day/dawn/dusk/night. These are illustrative sRGB starting points, not measured material reflectances.
Plan one dominant light direction. A directional source gives approximately parallel cast shadows; point-light shadows diverge from the source; a large area light broadens penumbrae. Ambient and bounced light lift shadows; they do not erase contact occlusion. Keep a lit matte patch usually lighter than its own unlit counterpart under the same exposure; luminous objects, fill lights, local-color differences and specular reflection are exceptions. Low sun casts long shadows; noon short shadows; overcast creates broad soft modeling. Color temperature describes the illuminant, not how every painted object must look. Warm direct light can accompany cooler sky-filled shadows, but colored surroundings can reverse that relation. Simultaneous contrast means the same gray appears different on light/dark or warm/cool neighbors; inspect in context. For depth, move distant values/chroma toward the atmosphere and reduce edge contrast.
Recipes: single-source scene: choose a five-value palette, gradient background, local-color shape, clipped gradient shading, and shadow style directed away from the source. Key/fill: keep the fill weaker and broader; render both separately before blending. Rim light: duplicate the silhouette behind the subject, expand/highlight its light-facing edge, use screen/add-style compositing sparingly; avoid an even halo unless backlit. Glow: duplicate the emissive shape, blur it on its own layer, screen-blend, retain a bright small core and illuminate nearby surfaces. Keep cast shadows separate so direction and softness stay editable.
Verification: use guide-check with kind lighting, light [x,y], objects [{position:[x,y],shadow:[dx,dy],lit:'#...',shade:'#...'}]. It flags shadows pointing toward a point source and darker lit patches. These are scene-metadata heuristics; explain exceptions. Inspect grayscale and cropped final-size previews.
References: CIE International Lighting Vocabulary https://cie.co.at/e-ilv ; PBRT 4e, Light Sources and Color and Radiometry https://pbr-book.org/4ed/Light_Sources ; Josef Albers, Interaction of Color (1963), contextual color exercises. These sources establish principles, not numeric promises for the palettes.
""",
"anatomy-proportions": """Anatomy and appearance: construction reference
Use a gesture line and balance over support before contour. Torso masses are rib cage and pelvis linked by a flexible spine; shoulder girdle can move independently from the pelvis. Upper/lower arm and thigh/shin are similar but not identical lengths. Elbows and knees hinge, forearms pronate/supinate, and ball joints allow multiple axes: a 2D rig angle is not a complete anatomical joint orientation. Broad adult art convention: 7–8 heads tall; teen about 6.5–7.5; child about 5–6.5; toddler about 4–5. These overlapping ranges are construction aids, not health or appearance standards. Stylized figures can intentionally depart from them. Adult shoulder width often about 2–3 head widths. Pubic region is roughly halfway down standing height; elbow near waist, wrist near hip, fingertips near mid-thigh. Variation, pose and perspective dominate exact ratios.
Face: in a neutral front view eyes lie near half skull height (hair excluded); nose base between eyes/chin, mouth between nose/chin. The eye-to-eye gap is roughly one eye width as a starting convention, never a rule for every face. Establish cranium/jaw planes, place a centerline that wraps the form, then adapt actual asymmetry and feature spacing. Hands: palm mass plus thumb wedge and four finger arcs; knuckles and fingertips follow staggered arcs, not a straight rake. Hair is grouped volumes over the skull with parting and gravity. Clothing folds start at tension/compression/support, with thickness changing edge softness.
Represent diverse ages, body sizes, facial structure, skin tones, hair textures, mobility and clothing. Do not equate one default template with normality. Animals: use species-specific spine/ribcage/pelvis masses, limb joint direction, digitigrade/plantigrade stance and reference. Wings, fins, exoskeletons and plants require different construction; do not reuse human joint limits blindly.
Approximate adult illustration range reference (degrees, flexion coordinate conventions): elbow flexion 0–150, knee flexion 0–140, shoulder flexion 0–180, hip flexion 0–120, wrist flexion 0–80. Human variation and active/passive measurement protocols matter; these are loose illustration sanity bands, not clinical norms or medical judgments. The cited CDC study reports measured passive ranges and confidence intervals by age and sex. Check only labeled anatomical flexion measures, not arbitrary sprite rotation.
Workflow: figure-plan returns named editable head, torso, pelvis, arm and leg parts from head units and body width, plus a parts map. Apply its operations, adjust proportions from references, establish pivot locations, then use character rigging. guide-check kind anatomy accepts head_units, style realistic/stylized, joints [{name,angle}], and limbs [{name,upper,lower}]. It reports only egregious ratios and labeled flexion violations.
References: OpenStax Anatomy and Physiology 2e, chapters 7–9 (skeleton/joints) https://openstax.org/books/anatomy-and-physiology-2e/pages/9-5-types-of-body-movements ; CDC joint range-of-motion reference tables https://archive.cdc.gov/www_cdc_gov/ncbddd/jointrom/index_1715172647.html ; Andrew Loomis, Figure Drawing for All It's Worth (1943), art proportion conventions.
""",
"illustration-perspective": """Illustration style and perspective reference
Choose shape language and value hierarchy before texture. Large readable silhouettes, grouped dark/light masses, overlap and a deliberate focal contrast work across styles. Check the subject as a black silhouette at thumbnail size; avoid important appendages merging with the torso. Three grouped values usually communicate better than many unrelated midtones. Eye flow follows contrast, edges, faces and implied lines; secondary accents should lead back to the focal point.
Style recipes mapped to Vixl operations: flat = shape/pen, 3–5 palette roles, minimal gradients; line-and-wash = pen or paint with ink plus translucent watercolor/ink-wash drawn-texture; cutout = irregular shapes + paper pattern-fill and small directional shadows; painterly = paint with dry-brush/charcoal, broad masses before edges; ink = brush-pen outlines + hatching or stipple texture; pencil/crayon = paint preset plus drawn-texture and pressure/jitter, kept as separate overlays. pattern-stroke paints tiled material along a path. Inspect texture against the plain original and at intended delivery scale.
Perspective: horizon is eye level, including outside the crop. One point: front-facing planes retain parallel edges; receding edges share one vanishing point. Two point: two horizontal edge families converge to two points on one horizon. Three point: verticals also converge above/below the horizon. Wide field of view exaggerates near/far size; moving camera and changing focal length are different actions. Foreshortened limbs must shorten in projection; overlapping cross-contours and joint landmarks explain depth. Use overlap, relative size, edge softness and atmospheric contrast together. A long lens can compress depth; orthographic/isometric art deliberately avoids convergence.
Workflow: perspective-guides spec {width,height,horizon,points:1|2|3,depths:[positive distances],reference_size,reference_depth} returns a perspective grid operation and scale-by-depth sizes: size = reference_size * reference_depth / depth. Apply guide operations; place objects with a common ground plane and camera. guide-check kind perspective accepts horizon and vanishing points (only horizontal families), and objects {depth,size}; normalized size*depth should agree for equally sized objects. kind illustration accepts values [0..1] and silhouette_contrast [0..1] measured against the background. Checks are advisory and conditional, not automatic aesthetic judgments.
References: James Gurney, Imaginative Realism (2009), composition/value construction; Ernest R. Norling, Perspective Made Easy (1939), vanishing points/horizon; PBRT 4e, Cameras and Film https://pbr-book.org/4ed/Cameras_and_Film .
""",
"drawn-textures": """Drawn textures: compare before committing
Use drawn-texture target Shape preset pencil|charcoal|crayon|ink-wash|stipple|hatch. It adds a separate transparent raster overlay clipped to the rendered silhouette and retains the original vector. Set seed for reproducibility, strength 0..1, scale .1..20, jitter 0..1, pressure 0..1 and grain 0..1. Pencil/hatch jitter the line path and vary coverage per stroke; charcoal/wash use low-frequency pooled coverage; stipple scatters marks; crayon/pencil/charcoal interact with paper tooth. Render plain, textured and 200% detail views side by side, then verify at final size: visible tooth at 200% alone is insufficient. For editable hand-drawn outlines use paint pencil/charcoal/crayon/watercolor brush presets with pressure points; a fill overlay does not change the vector's outline geometry. Combine paper pattern-fill under a low-opacity ink wash; use clone-stamp to repeat sampled handmade marks and pattern-define to save a repeat. Inspect a 3x3 tile repeat for seams.
""",
"film-review": """Film review and performance
Before every full export, use film-preview PNG at each shot start/middle/end, at every crossfade midpoint and at extreme camera poses. time/start/end are milliseconds, matching film and timeline specs. PNG seeks directly to its requested frame, including camera crop, transitions and captions. Use shot (zero-based), or start/end, with GIF for a bounded loop (at most 300 frames/80M pixels), MP4/WebM/ZIP for a selected interval; add region [x,y,width,height] in original film pixels for a narrow crop. Do not render an entire film to check one framing change.
film-preview defaults to quality draft; explicit final uses delivery resolution. Draft caps the longest side at 640 and lowers video encoding quality. Static document shots avoid cloning/hashing timeline state each frame. Existing content-addressed disk layer caching preserves unchanged content between runs and shots; changing one layer invalidates its cache dependencies. Render only the changed shot/interval after a local change, then export the full film after approvals. Frame-parallel rendering is not enabled: memory growth and deterministic ordering must be profiled before adding it. The speedup depends on how much work is static, rasterization cost and codec; benchmark a representative draft and final interval, never assume a fixed full-film duration.
Use video-sample with explicit times or interval to produce visible labeled contact sheets; use audio-analyze for unweighted RMS dBFS, clipping, silence, spectral-flux onsets, a heuristic beat estimate and a spectrogram. Pass video event timestamps to events to measure onset timing errors. Numeric checks and spectrograms do not judge musical quality; audition exported audio with an audio-capable model/player if available.
""",
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
